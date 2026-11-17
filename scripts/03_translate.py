#!/usr/bin/env python3
"""Этап 3: перевод текстовых единиц на русский.

Провайдеры:
    echo          — заглушка (без сети), для проверки пайплайна
    google        — бесплатный веб-эндпоинт Google Translate (без ключа)
    google_cloud  — официальный Cloud Translation API (нужен ключ)
    openai        — любой OpenAI-совместимый API (ключ/модель)
    ollama        — локальная модель через Ollama

Примеры:
    python3 scripts/03_translate.py --limit 20
    python3 scripts/03_translate.py --provider google --limit 100
    MINKARA_TRANSLATE_PROVIDER=openai python3 scripts/03_translate.py
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import deepl as deepl_api  # noqa: E402
from minkara import parse, quality  # noqa: E402
from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402
from minkara.progress import Progress  # noqa: E402

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


# --------------------------------------------------------------------------
# Провайдеры
# --------------------------------------------------------------------------


class EchoTranslator:
    name = "echo"

    def translate(self, texts: list[str]) -> list[str]:
        return [f"[ru] {text}" for text in texts]


def _chunks(text: str, limit: int = 4000) -> list[str]:
    """Режет длинный текст по строкам, чтобы не превысить лимит эндпоинта."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return chunks


class GoogleWebTranslator:
    """Неофициальный эндпоинт, который использует Google Translate в браузере.

    Ключ не нужен, но это не гарантированный SLA-сервис. Для больших объёмов
    лучше google_cloud, DeepL или LLM.
    """

    name = "google"
    endpoint = "https://translate.googleapis.com/translate_a/single"

    def _request(self, text: str) -> str:
        query = urllib.parse.urlencode(
            {"client": "gtx", "sl": "ja", "tl": "ru", "dt": "t", "q": text}
        )
        request = urllib.request.Request(
            f"{self.endpoint}?{query}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        return "".join(part[0] for part in data[0] if part and part[0])

    def _one(self, text: str) -> str:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return "".join(self._request(chunk) for chunk in _chunks(text))
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
                last_error = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"Google Translate: {last_error}")

    def translate(self, texts: list[str]) -> list[str]:
        result = []
        for text in texts:
            if not text.strip():
                result.append("")
                continue
            result.append(self._one(text))
            time.sleep(0.25)
        return result


class DeepLTranslator:
    """DeepL API (free или pro — по суффиксу ключа ':fx')."""

    name = "deepl"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise SystemExit("Нужен MINKARA_TRANSLATE_API_KEY (или DEEPL_API_KEY) для deepl")
        self.api_key = api_key

    def translate(self, texts: list[str]) -> list[str]:
        return deepl_api.translate(self.api_key, texts)


class GoogleCloudTranslator:
    name = "google_cloud"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def translate(self, texts: list[str]) -> list[str]:
        if not self.api_key:
            raise SystemExit("Нужен MINKARA_TRANSLATE_API_KEY для google_cloud")
        url = (
            "https://translation.googleapis.com/language/translate/v2"
            f"?key={urllib.parse.quote(self.api_key)}"
        )
        payload = json.dumps({"q": texts, "source": "ja", "target": "ru", "format": "text"}).encode()
        request = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        return [
            html_lib.unescape(item["translatedText"])
            for item in data["data"]["translations"]
        ]


class OpenAITranslator:
    name = "openai"

    def __init__(self, base_url: str, api_key: str, model: str, glossary: dict[str, str]) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.glossary = glossary

    def _prompt(self, texts: list[str]) -> list[dict[str, str]]:
        terms = "\n".join(f"- {ja} -> {ru}" for ja, ru in self.glossary.items())
        system = (
            "Ты переводишь японские автомобильные тексты на русский язык. "
            "Переводи смысл, а не слова. Сохраняй технические обозначения "
            "(GB7, GT6, AFS, DCT, OEM и т.п.) без изменений. Не добавляй "
            "пояснений и не сокращай текст. Верни строго JSON-массив строк "
            "той же длины, что и входной.\n\n"
            f"Обязательные термины:\n{terms}"
        )
        user = json.dumps(texts, ensure_ascii=False)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def translate(self, texts: list[str]) -> list[str]:
        payload = json.dumps(
            {"model": self.model, "messages": self._prompt(texts), "temperature": 0.2}
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(content)
        if not isinstance(result, list) or len(result) != len(texts):
            raise ValueError("Провайдер вернул неверное число переводов")
        return [str(item) for item in result]


class OllamaTranslator(OpenAITranslator):
    name = "ollama"

    def __init__(self, model: str, glossary: dict[str, str], host: str = "http://127.0.0.1:11434") -> None:
        self.base_url = host.rstrip("/")
        self.api_key = ""
        self.model = model
        self.glossary = glossary

    def translate(self, texts: list[str]) -> list[str]:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": self._prompt(texts),
                "stream": False,
                "options": {"temperature": 0.2},
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["message"]["content"].strip()
        content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(content)
        if not isinstance(result, list) or len(result) != len(texts):
            raise ValueError("Ollama вернула неверное число переводов")
        return [str(item) for item in result]


CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def looks_untranslated(ja: str, ru: str) -> bool:
    """Отсеивает пустые ответы и текст, оставшийся на японском."""
    if not CJK_RE.search(ja):
        return False
    if not ru or not ru.strip():
        return True
    if ru.strip() == ja.strip():
        return True
    cjk = len(CJK_RE.findall(ru))
    letters = len(re.findall(r"[^\W\d_]", ru, re.UNICODE)) or 1
    return cjk / letters > 0.25


def reset_engine(store: Store, engine: str, limit: int | None) -> int:
    if engine == "all":
        rows = store.conn.execute(
            "SELECT id FROM text_units WHERE ru IS NOT NULL LIMIT ?",
            (limit if limit else -1,),
        ).fetchall()
    else:
        rows = store.conn.execute(
            "SELECT id FROM text_units WHERE engine = ? LIMIT ?",
            (engine, limit if limit else -1),
        ).fetchall()
    ids = [(row["id"],) for row in rows]
    if ids:
        store.conn.executemany(
            "UPDATE text_units SET ru = NULL, engine = NULL WHERE id = ?", ids
        )
        store.conn.commit()
    return len(ids)


def build_translator(provider: str, glossary: dict[str, str]):
    model = os.environ.get("MINKARA_TRANSLATE_MODEL", "")
    base_url = os.environ.get("MINKARA_TRANSLATE_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("MINKARA_TRANSLATE_API_KEY") or os.environ.get(
        "DEEPL_API_KEY", ""
    )
    if provider == "echo":
        return EchoTranslator()
    if provider == "google":
        return GoogleWebTranslator()
    if provider == "deepl":
        return DeepLTranslator(api_key)
    if provider == "google_cloud":
        return GoogleCloudTranslator(api_key)
    if provider == "openai":
        if not model:
            raise SystemExit("Нужен MINKARA_TRANSLATE_MODEL для openai")
        return OpenAITranslator(base_url, api_key, model, glossary)
    if provider == "ollama":
        return OllamaTranslator(model or "qwen2.5:14b-instruct", glossary)
    raise SystemExit(f"Неизвестный провайдер: {provider}")


def load_glossary(path: Path) -> dict[str, str]:
    """Ручной глоссарий + сгенерированный DeepL (ручной важнее)."""
    if yaml is None:
        return {}
    result: dict[str, str] = {}
    for candidate in (path.with_name("glossary.generated.yaml"), path):
        if not candidate.exists():
            continue
        with candidate.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        result.update({str(k): str(v) for k, v in data.items() if k and v})
    return result


# --------------------------------------------------------------------------
# Основной цикл
# --------------------------------------------------------------------------


def sync_units(store: Store) -> int:
    """Переносит тексты из meta_json в text_units (идемпотентно)."""
    store.purge_non_japanese()
    total = 0
    for kind in ("note", "parts", "review", "product"):
        for page in store.parsed_pages(kind):
            meta = json.loads(page["meta_json"])
            for unit in parse.extract_text_units(meta, kind):
                if unit.get("ja"):
                    store.upsert_text_unit(
                        page["id"], unit["kind"], unit["idx"], unit["ja"], commit=False
                    )
                    total += 1
    store.conn.commit()
    return total


def write_report(path: str, engine: str, rows: list[tuple[str, str]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Сэмпл перевода: {engine}",
        "",
        f"Единиц: {len(rows)}",
        "",
        "| JA | RU |",
        "|---|---|",
    ]
    for ja, ru in rows:
        lines.append(
            "| "
            + ja.replace("|", "\\|").replace("\n", " ")
            + " | "
            + ru.replace("|", "\\|").replace("\n", " ")
            + " |"
        )
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Отчёт: {target}")


def fix_bad(store: Store, glossary: dict[str, str], args, deepl_key: str) -> int:
    """Пост-редактирование плохих переводов через DeepL."""
    if not deepl_key:
        print("Нужен ключ DeepL (MINKARA_TRANSLATE_API_KEY / DEEPL_API_KEY)")
        return 1
    rows = store.conn.execute(
        "SELECT * FROM text_units WHERE engine = ? AND ru IS NOT NULL",
        (args.fix_engine,),
    ).fetchall()
    scored = []
    for unit in rows:
        score, reasons = quality.score_translation(unit["ja"], unit["ru"], glossary)
        if score >= args.fix_threshold:
            scored.append((score, reasons, unit))
    # Сначала самые объёмные: они дают наибольший выигрыш.
    scored.sort(key=lambda item: len(item[2]["ja"]), reverse=True)
    if args.limit:
        scored = scored[: args.limit]

    print(f"Движок {args.fix_engine}: проверено {len(rows)}, кандидатов {len(scored)}")
    if args.dry_run:
        for score, reasons, unit in scored[:15]:
            print(f"  [{score}] {unit['ja'][:70]!r} -> {unit['ru'][:70]!r} | {', '.join(reasons)}")
        return 0

    info = deepl_api.usage(deepl_key)
    need = sum(len(item[2]["ja"]) for item in scored)
    if need > info["remaining"]:
        kept, total = [], 0
        for item in scored:
            size = len(item[2]["ja"])
            if total + size > info["remaining"]:
                break
            kept.append(item)
            total += size
        print(
            f"! Квоты DeepL не хватает: нужно {need}, осталось {info['remaining']}; "
            f"берём {len(kept)} сегментов"
        )
        scored = kept

    fixed = 0
    failed = 0
    report_rows: list[tuple[str, str]] = []
    progress = Progress(len(scored), "deepl-fix")
    for start in range(0, len(scored), args.batch_size):
        batch = scored[start : start + args.batch_size]
        texts = [item[2]["ja"] for item in batch]
        try:
            fresh = deepl_api.translate(deepl_key, texts)
        except Exception as exc:  # сеть/квота — не роняем весь прогон
            failed += len(batch)
            print(f"  ! батч {start // args.batch_size}: {exc}")
            continue
        for (_score, _reasons, unit), value in zip(batch, fresh, strict=False):
            if quality.is_bad(unit["ja"], value, glossary):
                failed += 1
                print(f"  ! DeepL тоже плохо: {unit['ja'][:50]!r}")
                continue
            store.set_translation(unit["id"], value, "deepl")
            fixed += 1
            report_rows.append((unit["ja"], value))
        progress.update(fixed + failed, f"ok {fixed}, ошибок {failed}")

    progress.close(fixed + failed)

    if args.report:
        write_report(args.report, "deepl-fix", report_rows)
    print(f"\nГотово. Исправлено: {fixed}, не удалось: {failed}")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Перевод текстов minkara")
    parser.add_argument(
        "--provider",
        default=os.environ.get("MINKARA_TRANSLATE_PROVIDER", "echo"),
        choices=["echo", "google", "google_cloud", "deepl", "openai", "ollama"],
    )
    parser.add_argument("--limit", type=int, default=0, help="сколько единиц перевести")
    parser.add_argument("--batch-size", type=int, default=8, help="размер батча для LLM")
    parser.add_argument("--dry-run", action="store_true", help="только показать, что будет переведено")
    parser.add_argument("--no-sync", action="store_true", help="не обновлять text_units из meta_json")
    parser.add_argument("--sync-only", action="store_true", help="только синхронизировать единицы")
    parser.add_argument(
        "--redo-engine",
        help="сбросить переводы указанного движка (например, echo) и перевести заново",
    )
    parser.add_argument("--report", help="сохранить сэмпл переводов в markdown-файл")
    parser.add_argument(
        "--kinds",
        help="только страницы указанных типов (note,review,qa,model,product,parts)",
    )
    parser.add_argument("--min-chars", type=int, default=0, help="только тексты длиннее N символов")
    parser.add_argument("--max-chars", type=int, default=0, help="только тексты короче N символов")
    parser.add_argument("--check-usage", action="store_true", help="показать остаток квоты DeepL")
    parser.add_argument(
        "--fix-bad",
        action="store_true",
        help="найти плохие переводы указанного движка и перевести их через DeepL",
    )
    parser.add_argument("--fix-engine", default="google", help="какой движок проверять (google)")
    parser.add_argument("--fix-threshold", type=int, default=2, help="порог штрафа для перевода")
    args = parser.parse_args()

    settings = load_settings()
    store = Store(settings.db_path)
    store.init()

    deepl_key = os.environ.get("MINKARA_TRANSLATE_API_KEY") or os.environ.get("DEEPL_API_KEY", "")
    if args.check_usage:
        if not deepl_key:
            print("Ключ DeepL не задан (MINKARA_TRANSLATE_API_KEY / DEEPL_API_KEY)")
            return 1
        info = deepl_api.usage(deepl_key)
        print(f"DeepL: использовано {info['used']} из {info['limit']}, остаток {info['remaining']}")
        return 0

    if not args.no_sync:
        print(f"Синхронизировано единиц: {sync_units(store)}")
    if args.sync_only:
        return 0
    if args.redo_engine:
        reset = reset_engine(store, args.redo_engine, args.limit or None)
        print(f"Сброшено переводов '{args.redo_engine}': {reset}")
    glossary = load_glossary(settings.glossary_file)
    if args.fix_bad:
        return fix_bad(store, glossary, args, deepl_key)

    translator = build_translator(args.provider, glossary)

    kinds = [k.strip() for k in (args.kinds or "").split(",") if k.strip()]
    units = store.pending_units(limit=args.limit or None, kinds=kinds or None)
    if args.min_chars:
        units = [unit for unit in units if len(unit["ja"]) >= args.min_chars]
    if args.max_chars:
        units = [unit for unit in units if len(unit["ja"]) <= args.max_chars]

    if translator.name == "deepl" and units:
        info = deepl_api.usage(deepl_key)
        need = sum(len(unit["ja"]) for unit in units)
        if need > info["remaining"]:
            kept, total = [], 0
            for unit in units:
                size = len(unit["ja"])
                if total + size > info["remaining"]:
                    break
                kept.append(unit)
                total += size
            print(
                f"! Квоты DeepL не хватает: нужно {need}, осталось {info['remaining']}; "
                f"берём {len(kept)} единиц"
            )
            units = kept
    print(f"Провайдер: {translator.name}; единиц к переводу: {len(units)}")
    if args.dry_run:
        for unit in units[:20]:
            print(f"  [{unit['kind']}:{unit['idx']}] {unit['ja'][:80]}")
        return 0

    translated = 0
    failed = 0
    report_rows: list[tuple[str, str]] = []
    progress = Progress(len(units), translator.name)
    for start in range(0, len(units), args.batch_size):
        batch = units[start : start + args.batch_size]
        texts = [unit["ja"] for unit in batch]
        # Кэш: одинаковый японский текст переводим один раз.
        to_translate: list[int] = []
        results: list[str | None] = [None] * len(batch)
        for i, unit in enumerate(batch):
            cached = store.cached_translation(unit["hash"], translator.name)
            if cached:
                results[i] = cached
            else:
                to_translate.append(i)
        if to_translate:
            try:
                fresh = translator.translate([texts[i] for i in to_translate])
            except Exception as exc:
                failed += len(to_translate)
                print(f"  ! батч {start // args.batch_size}: {exc}")
                continue
            for position, value in zip(to_translate, fresh, strict=False):
                results[position] = value
        for unit, value in zip(batch, results, strict=False):
            if value is None:
                continue
            if looks_untranslated(unit["ja"], value):
                failed += 1
                print(f"  ! сомнительный перевод [{unit['kind']}:{unit['idx']}]: {value[:70]}")
                continue
            store.set_translation(unit["id"], value, translator.name, commit=False)
            translated += 1
            report_rows.append((unit["ja"], value))
        store.conn.commit()
        progress.update(translated + failed, f"ok {translated}, ошибок {failed}")

    progress.close(translated + failed)

    if args.report:
        write_report(args.report, translator.name, report_rows)

    print(f"\nГотово. Переведено: {translated}, ошибок: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
