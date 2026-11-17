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
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import parse  # noqa: E402
from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402

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


class GoogleWebTranslator:
    """Неофициальный эндпоинт, который использует Google Translate в браузере.

    Ключ не нужен, но это не гарантированный SLA-сервис. Для больших объёмов
    лучше google_cloud или LLM.
    """

    name = "google"
    endpoint = "https://translate.googleapis.com/translate_a/single"

    def _one(self, text: str) -> str:
        query = urllib.parse.urlencode(
            {"client": "gtx", "sl": "ja", "tl": "ru", "dt": "t", "q": text}
        )
        request = urllib.request.Request(
            f"{self.endpoint}?{query}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        chunks = [part[0] for part in data[0] if part and part[0]]
        return "".join(chunks)

    def translate(self, texts: list[str]) -> list[str]:
        result = []
        for text in texts:
            if not text.strip():
                result.append("")
                continue
            result.append(self._one(text))
            time.sleep(0.3)
        return result


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


def build_translator(provider: str, glossary: dict[str, str]):
    model = os.environ.get("MINKARA_TRANSLATE_MODEL", "")
    base_url = os.environ.get("MINKARA_TRANSLATE_BASE_URL", "https://api.openai.com/v1")
    api_key = os.environ.get("MINKARA_TRANSLATE_API_KEY", "")
    if provider == "echo":
        return EchoTranslator()
    if provider == "google":
        return GoogleWebTranslator()
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
    if yaml is None or not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return {str(k): str(v) for k, v in data.items() if k and v}


# --------------------------------------------------------------------------
# Основной цикл
# --------------------------------------------------------------------------


def sync_units(store: Store) -> int:
    """Переносит тексты из meta_json в text_units (идемпотентно)."""
    total = 0
    for kind in ("note", "parts", "review", "product"):
        for page in store.parsed_pages(kind):
            meta = json.loads(page["meta_json"])
            for unit in parse.extract_text_units(meta, kind):
                if unit.get("ja"):
                    store.upsert_text_unit(page["id"], unit["kind"], unit["idx"], unit["ja"])
                    total += 1
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Перевод текстов minkara")
    parser.add_argument(
        "--provider",
        default=os.environ.get("MINKARA_TRANSLATE_PROVIDER", "echo"),
        choices=["echo", "google", "google_cloud", "openai", "ollama"],
    )
    parser.add_argument("--limit", type=int, default=0, help="сколько единиц перевести")
    parser.add_argument("--batch-size", type=int, default=8, help="размер батча для LLM")
    parser.add_argument("--dry-run", action="store_true", help="только показать, что будет переведено")
    parser.add_argument("--no-sync", action="store_true", help="не обновлять text_units из meta_json")
    args = parser.parse_args()

    settings = load_settings()
    store = Store(settings.db_path)
    store.init()
    if not args.no_sync:
        print(f"Синхронизировано единиц: {sync_units(store)}")
    glossary = load_glossary(settings.glossary_file)
    translator = build_translator(args.provider, glossary)

    units = store.pending_units(limit=args.limit or None)
    print(f"Провайдер: {translator.name}; единиц к переводу: {len(units)}")
    if args.dry_run:
        for unit in units[:20]:
            print(f"  [{unit['kind']}:{unit['idx']}] {unit['ja'][:80]}")
        return 0

    translated = 0
    failed = 0
    for start in range(0, len(units), args.batch_size):
        batch = units[start : start + args.batch_size]
        texts = [unit["ja"] for unit in batch]
        # Кэш: одинаковый японский текст переводим один раз.
        to_translate: list[int] = []
        results: list[str | None] = [None] * len(batch)
        for i, unit in enumerate(batch):
            cached = store.cached_translation(unit["hash"])
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
            store.set_translation(unit["id"], value, translator.name)
            translated += 1
        print(f"  переведено: {translated}/{len(units)}")

    print(f"\nГотово. Переведено: {translated}, ошибок: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
