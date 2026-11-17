#!/usr/bin/env python3
"""Этап 5: сборка глоссария терминов через DeepL.

Берёт тексты из text_units, выделяет частотные термины (катакана, кандзи,
составные «термин + 交換/取付/…»), переводит их пакетно через DeepL и пишет
config/glossary.generated.yaml. Ручной config/glossary.yaml имеет приоритет.

Примеры:
    python3 scripts/05_glossary.py --check-usage
    python3 scripts/05_glossary.py --min-freq 2 --limit 200
    python3 scripts/05_glossary.py --dry-run --limit 40
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import deepl as deepl_api  # noqa: E402
from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402

CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

PATTERNS = [
    re.compile(r"[ァ-ヶー]{2,12}"),
    re.compile(r"[一-龯]{2,6}"),
    re.compile(r"[ァ-ヶー]{2,}[一-龯]{1,4}"),
    re.compile(r"[一-龯]{1,4}[ァ-ヶー]{2,}"),
    re.compile(r"[一-龯ァ-ヶー]{2,10}(?:交換|取付|点検|整備|修理|清掃|塗装|増設|移設|配線|加工|調整|取外し|取付け)"),
]

STOPWORDS = {
    "こと", "もの", "ため", "よう", "場合", "今回", "自分", "作業", "画像", "内容",
    "以上", "以下", "前回", "次回", "最近", "普通", "必要", "可能", "予定", "実施",
    "確認", "状態", "部分", "場所", "時間", "方法", "感じ", "気持ち", "問題", "結果",
    "交換", "取付", "点検", "整備", "修理", "清掃", "塗装", "増設", "移設", "配線",
    "加工", "調整", "取外し", "取付け", "使用", "購入", "装着", "取り付け", "取り外し",
    "本日", "今日", "昨日", "皆さん", "情報", "記事", "写真", "動画", "商品",
    # обрывки слов и вежливые формулы, а не термины
    "素晴", "ありがと", "ありがとう", "お世話", "よろしく", "はじめ", "すみません",
    "おはよう", "こんにちは", "こんばんは", "気持", "感じる", "思います", "ました",
}

CONTEXT = "「{term}」は自動車の部品です。"


def extract_term(output: str) -> str:
    """Достаёт термин из «Сиденье» — это деталь автомобиля."""
    match = re.search(r"[«\"“](.+?)[»\"”]", output)
    if match:
        return match.group(1).strip()
    return output.split("—")[0].strip().strip("«»\"“”")


def candidates(texts: list[str]) -> Counter:
    freq: Counter = Counter()
    for text in texts:
        found = set()
        for pattern in PATTERNS:
            for match in pattern.findall(text):
                term = match.strip()
                if len(term) < 2 or term in STOPWORDS:
                    continue
                if not CJK_RE.search(term):
                    continue
                found.add(term)
        freq.update(found)
    return freq


def valid(term: str, translation: str) -> bool:
    if not translation or not translation.strip():
        return False
    if translation.strip() == term.strip():
        return False
    if not CYRILLIC_RE.search(translation):
        return False
    if CJK_RE.search(translation):
        return False
    if len(translation) > 90:
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Глоссарий терминов через DeepL")
    parser.add_argument("--limit", type=int, default=0, help="сколько терминов обработать")
    parser.add_argument("--min-freq", type=int, default=2, help="минимальная частота")
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--write", default="config/glossary.generated.yaml")
    parser.add_argument("--report", default="work/glossary-report.md")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-usage", action="store_true")
    parser.add_argument("--plain", action="store_true", help="переводить без контекстного шаблона")
    args = parser.parse_args()

    settings = load_settings()
    store = Store(settings.db_path)
    store.init()
    key = os.environ.get("MINKARA_TRANSLATE_API_KEY") or os.environ.get("DEEPL_API_KEY", "")

    if args.check_usage:
        if not key:
            print("Ключ DeepL не задан")
            return 1
        info = deepl_api.usage(key)
        print(f"DeepL: использовано {info['used']} из {info['limit']}, остаток {info['remaining']}")
        return 0

    if not key:
        print("Нужен ключ DeepL (MINKARA_TRANSLATE_API_KEY / DEEPL_API_KEY)")
        return 1

    texts = [row["ja"] for row in store.conn.execute("SELECT ja FROM text_units")]
    freq = candidates(texts)
    terms = [
        term
        for term, count in sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0])))
        if count >= args.min_freq
    ]
    if args.limit:
        terms = terms[: args.limit]

    def source_text(term: str) -> str:
        return CONTEXT.format(term=term) if not args.plain else term

    info = deepl_api.usage(key)
    need = sum(len(source_text(term)) for term in terms)
    if need > info["remaining"]:
        kept, total = [], 0
        for term in terms:
            size = len(source_text(term))
            if total + size > info["remaining"]:
                break
            kept.append(term)
            total += size
        print(f"! Квоты не хватает: нужно {need}, осталось {info['remaining']}; берём {len(kept)}")
        terms = kept

    print(f"Терминов к переводу: {len(terms)} (символов ~{sum(len(source_text(t)) for t in terms)})")
    if args.dry_run:
        for term in terms[:40]:
            print(f"  {freq[term]:3d}  {term}")
        return 0

    translated: dict[str, str] = {}
    rows: list[tuple[int, str, str]] = []
    for start in range(0, len(terms), args.batch_size):
        batch = terms[start : start + args.batch_size]
        try:
            results = deepl_api.translate(key, [source_text(term) for term in batch])
        except Exception as exc:
            print(f"  ! батч {start // args.batch_size}: {exc}")
            continue
        for term, raw in zip(batch, results, strict=False):
            value = extract_term(raw).strip().strip("。")
            if not valid(term, value):
                continue
            translated[term] = value
            rows.append((freq[term], term, value))
        print(f"  переведено: {len(translated)}/{len(terms)}")

    target = ROOT / args.write
    lines = [
        "# Сгенерировано scripts/05_glossary.py через DeepL.",
        "# Ручной config/glossary.yaml имеет приоритет и подмешивается поверх.",
        "# Формат: японский термин -> русский вариант.",
        "",
    ]
    for term in sorted(translated, key=lambda t: (-freq[t], t)):
        lines.append(f'"{term}": "{translated[term]}"')
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = ROOT / args.report
    report.parent.mkdir(parents=True, exist_ok=True)
    report_lines = ["# Глоссарий (DeepL)", "", "| Частота | JA | RU |", "|---|---|---|"]
    for count, term, value in sorted(rows, reverse=True):
        report_lines.append(f"| {count} | {term} | {value} |")
    report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"\nЗаписано: {target} ({len(translated)} терминов)")
    print(f"Отчёт: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
