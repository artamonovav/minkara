#!/usr/bin/env python3
"""Этап 0: автообнаружение моделей марки по подстроке.

Сканирует страницу-образец (по умолчанию /car/<brand>/<seed>/) и собирает
ссылки вида /car/<brand>/<model>/, отбрасывая служебные разделы. Полезно,
когда нужно взять «все модели со словом freed» или добавить новую марку.

Примеры:
    python3 scripts/00_models.py --brand honda --match freed
    python3 scripts/00_models.py --brand honda --match freed --write

С --write результат пишется в config/models.discovered.yaml, который
подмешивается к config/models.yaml (ручные записи имеют приоритет).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara.config import load_settings  # noqa: E402
from minkara.http import BlockedError, Fetcher, FetchError  # noqa: E402

SERVICE_SEGMENTS = {
    "note",
    "partsreview",
    "review",
    "photo",
    "qa",
    "ranking",
    "spec",
    "custom",
    "nenpi",
    "usercar",
    "grade",
    "price",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Поиск моделей марки на minkara")
    parser.add_argument("--brand", required=True, help="марка, например honda")
    parser.add_argument("--match", default="", help="подстрока в ключе модели, например freed")
    parser.add_argument("--seed", help="модель-образец для сканирования (по умолчанию = --match)")
    parser.add_argument("--write", action="store_true", help="записать models.discovered.yaml")
    args = parser.parse_args()

    settings = load_settings()
    fetcher = Fetcher(settings)
    seed = args.seed or args.match
    if not seed:
        parser.error("нужен --seed или --match")

    url = f"{settings.base_url}/car/{args.brand}/{seed}/"
    try:
        html = fetcher.text(url)
    except BlockedError as exc:
        print(f"ОШИБКА: {exc}")
        return 2
    except FetchError as exc:
        print(f"ОШИБКА: {exc}")
        return 2

    pattern = re.compile(rf'href="(?:https://minkara\.carview\.co\.jp)?/car/{re.escape(args.brand)}/([a-z0-9_]+)/"')
    keys = sorted(
        {
            match.group(1)
            for match in pattern.finditer(html)
            if match.group(1) not in SERVICE_SEGMENTS
        }
    )
    match_lower = args.match.lower()
    candidates = [key for key in keys if match_lower in key.lower()] if match_lower else keys

    if not candidates:
        print(f"Моделей с подстрокой '{args.match}' не найдено на {url}")
        return 1

    print(f"Найдено моделей: {len(candidates)}")
    for key in candidates:
        print(f"  {key}")

    if args.write:
        target = settings.models_file.with_name("models.discovered.yaml")
        lines = [
            "# Сгенерировано scripts/00_models.py — не редактировать вручную.",
            "# Подмешивается к config/models.yaml; ручные записи имеют приоритет.",
            "brands:",
            f"  {args.brand}:",
            "    models:",
        ]
        for key in candidates:
            lines.append(f"      - key: {key}")
            lines.append(f"        name: {args.brand.title()} {key.replace('_', ' ').title()}")
            lines.append("        generations: []")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nЗаписано: {target}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
