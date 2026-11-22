#!/usr/bin/env python3
"""Пост-редактирование терминов в переводах Google.

Google систематически переводит 交換 как «обмен», а 取付 как «прикрепить».
Скрипт заменяет эти варианты на «замена» и «установка» с учётом частых
падежей/рода и не трогает остальной текст.

    python3 scripts/06_fix_terms.py --dry-run
    python3 scripts/06_fix_terms.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402


def _case(source: str, replacement: str) -> str:
    """Сохраняет регистр первой буквы и CAPS."""
    if not source:
        return replacement
    if source.isupper():
        return replacement.upper()
    if source[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def _rule(pattern: str, replacement: str) -> tuple[re.Pattern[str], str]:
    return re.compile(pattern, re.IGNORECASE), replacement


# Порядок важен: сначала словосочетания и длинные формы, потом короткие.
EXCHANGE_RULES = [
    # предлог «об» + замена
    _rule(r"\bоб\s+обмене\b", "о замене"),
    _rule(r"\bоб\s+обмен\b", "о замене"),
    # устойчивые предикаты
    _rule(r"\bобмен\s+был\s+завершен\b", "замена была завершена"),
    _rule(r"\bобмен\s+был\s+завершён\b", "замена была завершена"),
    _rule(r"\bобмен\s+завершен\b", "замена завершена"),
    _rule(r"\bобмен\s+завершён\b", "замена завершена"),
    _rule(r"\bобмен\s+произведен\b", "замена произведена"),
    _rule(r"\bобмен\s+произведён\b", "замена произведена"),
    _rule(r"\bобмен\s+выполнен\b", "замена выполнена"),
    _rule(r"\bобмен\s+сделан\b", "замена сделана"),
    _rule(r"\bобмен\s+состоялся\b", "замена состоялась"),
    _rule(r"\bобмен\s+прошел\b", "замена прошла"),
    _rule(r"\bобмен\s+прошёл\b", "замена прошла"),
    _rule(r"\bобмен\s+идет\b", "замена идет"),
    _rule(r"\bобмен\s+идёт\b", "замена идет"),
    _rule(r"\bобмен\s+будет\b", "замена будет"),
    _rule(r"\bобмен\s+был\b", "замена была"),
    # частые прилагательные (nominative + genitive)
    _rule(r"\bпоследний\s+обмен\b", "последняя замена"),
    _rule(r"\bпоследнего\s+обмена\b", "последней замены"),
    _rule(r"\bбыстрый\s+обмен\b", "быстрая замена"),
    _rule(r"\bбыстрого\s+обмена\b", "быстрой замены"),
    _rule(r"\bследующий\s+обмен\b", "следующая замена"),
    _rule(r"\bследующего\s+обмена\b", "следующей замены"),
    _rule(r"\bпервый\s+обмен\b", "первая замена"),
    _rule(r"\bпервого\s+обмена\b", "первой замены"),
    _rule(r"\bповторный\s+обмен\b", "повторная замена"),
    _rule(r"\bповторного\s+обмена\b", "повторной замены"),
    _rule(r"\bполный\s+обмен\b", "полная замена"),
    _rule(r"\bполного\s+обмена\b", "полной замены"),
    _rule(r"\bчастичный\s+обмен\b", "частичная замена"),
    _rule(r"\bчастичного\s+обмена\b", "частичной замены"),
    _rule(r"\bсамостоятельный\s+обмен\b", "самостоятельная замена"),
    _rule(r"\bсамостоятельного\s+обмена\b", "самостоятельной замены"),
    _rule(r"\bнавигационный\s+обмен\b", "навигационная замена"),
    _rule(r"\bнавигационного\s+обмена\b", "навигационной замены"),
    # существительное
    _rule(r"\bобмена\b", "замены"),
    _rule(r"\bобмену\b", "замене"),
    _rule(r"\bобменом\b", "заменой"),
    _rule(r"\bобмене\b", "замене"),
    _rule(r"\bобмен\b", "замена"),
    # глаголы
    _rule(r"\bобмениваться\b", "заменяться"),
    _rule(r"\bобмениваются\b", "заменяются"),
    _rule(r"\bобменивается\b", "заменяется"),
    _rule(r"\bобменивался\b", "заменялся"),
    _rule(r"\bобменивалась\b", "заменялась"),
    _rule(r"\bобменивались\b", "заменялись"),
    _rule(r"\bобменивать\b", "заменять"),
    _rule(r"\bобменивал\b", "заменял"),
    _rule(r"\bобменивала\b", "заменяла"),
    _rule(r"\bобменивали\b", "заменяли"),
    _rule(r"\bобмениваю\b", "заменяю"),
    _rule(r"\bобмениваешь\b", "заменяешь"),
    _rule(r"\bобменивает\b", "заменяет"),
    _rule(r"\bобмениваем\b", "заменяем"),
    _rule(r"\bобмениваете\b", "заменяете"),
    _rule(r"\bобменивают\b", "заменяют"),
    _rule(r"\bобменять\b", "заменить"),
    _rule(r"\bобменял\b", "заменил"),
    _rule(r"\bобменяла\b", "заменила"),
    _rule(r"\bобменяло\b", "заменило"),
    _rule(r"\bобменяли\b", "заменили"),
    _rule(r"\bобменяю\b", "заменю"),
    _rule(r"\bобменяешь\b", "заменишь"),
    _rule(r"\bобменяет\b", "заменит"),
    _rule(r"\bобменяем\b", "заменим"),
    _rule(r"\bобменяете\b", "замените"),
    _rule(r"\bобменяют\b", "заменят"),
    _rule(r"\bобменяй\b", "замени"),
    _rule(r"\bобменяйте\b", "замените"),
    _rule(r"\bобменялся\b", "заменился"),
    _rule(r"\bобменялась\b", "заменилась"),
    _rule(r"\bобменялись\b", "заменились"),
]

MOUNT_RULES = [
    _rule(r"\bприкрепление\b", "установка"),
    _rule(r"\bприкрепления\b", "установки"),
    _rule(r"\bприкреплению\b", "установке"),
    _rule(r"\bприкреплением\b", "установкой"),
    _rule(r"\bприкреплении\b", "установке"),
    _rule(r"\bприкрепить\b", "установить"),
    _rule(r"\bприкрепил\b", "установил"),
    _rule(r"\bприкрепила\b", "установила"),
    _rule(r"\bприкрепило\b", "установило"),
    _rule(r"\bприкрепили\b", "установили"),
    _rule(r"\bприкреплять\b", "устанавливать"),
    _rule(r"\bприкреплял\b", "устанавливал"),
    _rule(r"\bприкрепляла\b", "устанавливала"),
    _rule(r"\bприкрепляли\b", "устанавливали"),
    _rule(r"\bприкрепляется\b", "устанавливается"),
    _rule(r"\bприкрепляются\b", "устанавливаются"),
    _rule(r"\bприкреплённый\b", "установленный"),
    _rule(r"\bприкрепленный\b", "установленный"),
    _rule(r"\bприкреплённая\b", "установленная"),
    _rule(r"\bприкрепленная\b", "установленная"),
    _rule(r"\bприкреплённые\b", "установленные"),
    _rule(r"\bприкрепленные\b", "установленные"),
    _rule(r"\bприкреплён\b", "установлен"),
    _rule(r"\bприкреплен\b", "установлен"),
    _rule(r"\bприкреплена\b", "установлена"),
    _rule(r"\bприкреплено\b", "установлено"),
    _rule(r"\bприкреплены\b", "установлены"),
    # «установлен к …» → «установлен на …»
    _rule(r"\bустановленный\s+к\b", "установленный на"),
    _rule(r"\bустановленная\s+к\b", "установленная на"),
    _rule(r"\bустановленные\s+к\b", "установленные на"),
    _rule(r"\bустановлен\s+к\b", "установлен на"),
    _rule(r"\bустановлена\s+к\b", "установлена на"),
    _rule(r"\bустановлено\s+к\b", "установлено на"),
    _rule(r"\bустановлены\s+к\b", "установлены на"),
    _rule(r"\bустановить\s+к\b", "установить на"),
    _rule(r"\bустанавливается\s+к\b", "устанавливается на"),
    _rule(r"\bустанавливаются\s+к\b", "устанавливаются на"),
    _rule(r"\bустановка\s+к\b", "установка на"),
]


def apply_rules(text: str, rules) -> tuple[str, int]:
    changed = 0
    for pattern, replacement in rules:
        def repl(match: re.Match[str], replacement: str = replacement) -> str:
            nonlocal changed
            changed += 1
            return _case(match.group(0), replacement)

        text = pattern.sub(repl, text)
    return text, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Пост-редактирование терминов")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    settings = load_settings()
    store = Store(settings.db_path)
    store.init()

    rows = store.conn.execute(
        "SELECT id, ja, ru FROM text_units "
        "WHERE engine = 'google' AND ru IS NOT NULL "
        "AND (ja LIKE '%交換%' OR ja LIKE '%取付%')"
    ).fetchall()
    if args.limit:
        rows = rows[: args.limit]

    changed_units = 0
    changed_hits = 0
    samples: list[tuple[str, str]] = []
    for row in rows:
        text = row["ru"]
        hits = 0
        if "交換" in row["ja"]:
            text, hits = apply_rules(text, EXCHANGE_RULES)
        if "取付" in row["ja"]:
            text, more = apply_rules(text, MOUNT_RULES)
            hits += more
        if hits and text != row["ru"]:
            changed_units += 1
            changed_hits += hits
            if len(samples) < 20:
                samples.append((row["ru"], text))
            if not args.dry_run:
                store.conn.execute(
                    "UPDATE text_units SET ru = ? WHERE id = ?",
                    (text, row["id"]),
                )

    if not args.dry_run:
        store.conn.commit()

    print(f"Проверено единиц: {len(rows)}")
    print(f"Изменено единиц: {changed_units}, замен: {changed_hits}")
    if samples:
        print("\nПримеры:")
        for before, after in samples[:10]:
            print("  БЫЛО:  ", before[:140].replace("\n", " "))
            print("  СТАЛО:", after[:140].replace("\n", " "))
            print()
    if args.dry_run:
        print("Это был dry-run, база не изменена.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
