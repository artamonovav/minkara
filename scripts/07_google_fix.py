#!/usr/bin/env python3
"""Точечное улучшение переводов Google.

Google систематически ошибается на нескольких терминах:
  交換      -> «обмен» вместо «замена»
  納車      -> «роды» вместо «получение автомобиля»
  整備手帳  -> «ноутбук» вместо «заметки по обслуживанию»
  取付      -> «прикрепить» вместо «установка»

Скрипт находит такие единицы, подменяет термин в японском исходнике на
однозначный синоним, заново переводит через Google и сохраняет результат,
только если он стал лучше по оценке quality.

    python3 scripts/07_google_fix.py --dry-run
    python3 scripts/07_google_fix.py
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import quality  # noqa: E402
from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "minkara_translate", ROOT / "scripts" / "03_translate.py"
)
translate_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(translate_mod)

# (японский термин, плохой вариант в переводе, замена в исходнике)
CASES = [
    ("交換", "обмен", "入れ替え"),
    ("納車", "родов", "車の納車"),
    ("納車", "роды", "車の納車"),
    ("整備手帳", "ноутбук", "整備記録"),
    ("取付", "прикреп", "設置"),
]


def load_glossary() -> dict[str, str]:
    settings = load_settings()
    result: dict[str, str] = {}
    for path in (
        settings.glossary_file.with_name("glossary.generated.yaml"),
        settings.glossary_file,
    ):
        if not path.exists():
            continue
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        result.update({str(k): str(v) for k, v in data.items() if k and v})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Точечное улучшение Google-переводов")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.4)
    args = parser.parse_args()

    settings = load_settings()
    store = Store(settings.db_path)
    store.init()
    glossary = load_glossary()
    translator = translate_mod.GoogleWebTranslator()

    selected: dict[int, dict] = {}
    for ja_term, bad_word, replacement in CASES:
        rows = store.conn.execute(
            "SELECT id, ja, ru FROM text_units "
            "WHERE engine = 'google' AND ru IS NOT NULL "
            "AND ja LIKE ? AND lower(ru) LIKE ?",
            (f"%{ja_term}%", f"%{bad_word}%"),
        ).fetchall()
        for row in rows:
            item = selected.setdefault(
                row["id"],
                {"id": row["id"], "ja": row["ja"], "ru": row["ru"], "fixes": []},
            )
            item["fixes"].append((ja_term, bad_word, replacement))

    items = list(selected.values())
    if args.limit:
        items = items[: args.limit]
    print(f"Кандидатов: {len(items)}")
    if args.dry_run:
        for item in items[:20]:
            terms = ", ".join(f"{t}->{r}" for t, _b, r in item["fixes"])
            print(f"  [{terms}] {item['ja'][:80]!r}")
        return 0

    improved = 0
    failed = 0
    for index, item in enumerate(items, 1):
        source = item["ja"]
        bad_words = []
        for term, bad_word, replacement in item["fixes"]:
            source = source.replace(term, replacement)
            bad_words.append(bad_word)
        try:
            fresh = translator._one(source)
        except Exception as exc:
            failed += 1
            print(f"  ! {index}/{len(items)}: {exc}")
            time.sleep(2)
            continue
        old_score, _ = quality.score_translation(item["ja"], item["ru"], glossary)
        new_score, _ = quality.score_translation(item["ja"], fresh, glossary)
        bad_left = any(word in fresh.lower() for word in bad_words)
        if not fresh.strip() or fresh.strip() == item["ja"].strip():
            failed += 1
            continue
        if new_score < old_score or (not bad_left and new_score <= old_score):
            store.conn.execute(
                "UPDATE text_units SET ru = ? WHERE id = ?",
                (fresh, item["id"]),
            )
            improved += 1
        else:
            failed += 1
        if index % 20 == 0:
            store.conn.commit()
            print(f"  {index}/{len(items)}: улучшено {improved}, без улучшения {failed}")
        time.sleep(args.delay)

    store.conn.commit()
    print(f"\nГотово. Улучшено: {improved}, без улучшения/ошибок: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
