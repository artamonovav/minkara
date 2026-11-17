#!/usr/bin/env python3
"""Отчёт о покрытии архива: модели, поколения, категории, перевод."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402


def main() -> int:
    settings = load_settings()
    store = Store(settings.db_path)
    store.init()

    print("# Покрытие архива\n")

    print("## Страницы\n")
    print("| Тип | Всего | Готово |")
    print("|---|---:|---:|")
    for row in store.conn.execute(
        """SELECT kind,
                  COUNT(*) AS total,
                  SUM(CASE WHEN state IN ('parsed','skipped') THEN 1 ELSE 0 END) AS done
           FROM pages GROUP BY kind ORDER BY kind"""
    ):
        print(f"| {row['kind']} | {row['total']} | {row['done']} |")

    print("\n## Заметки по моделям и поколениям\n")
    print("| Модель | Поколение | Заметок |")
    print("|---|---:|---:|")
    for row in store.conn.execute(
        """SELECT model, generation, COUNT(*) AS n
           FROM pages WHERE kind = 'note' AND state = 'parsed'
           GROUP BY model, generation ORDER BY model, generation"""
    ):
        generation = row["generation"] if row["generation"] is not None else "?"
        print(f"| {row['model']} | {generation} | {row['n']} |")

    categories: Counter = Counter()
    for row in store.conn.execute(
        "SELECT meta_json FROM pages WHERE kind = 'note' AND meta_json IS NOT NULL"
    ):
        try:
            meta = json.loads(row["meta_json"])
        except Exception:
            continue
        for category in meta.get("categories") or []:
            categories[category] += 1
    if categories:
        print("\n## Топ категорий заметок\n")
        print("| Категория | Заметок |")
        print("|---|---:|")
        for category, count in categories.most_common(20):
            print(f"| {category} | {count} |")

    print("\n## Перевод\n")
    print("| Движок | Единиц |")
    print("|---|---:|")
    for row in store.conn.execute(
        """SELECT COALESCE(engine, '—') AS engine, COUNT(*) AS n
           FROM text_units WHERE ru IS NOT NULL GROUP BY engine ORDER BY n DESC"""
    ):
        print(f"| {row['engine']} | {row['n']} |")
    total = store.conn.execute("SELECT COUNT(*) FROM text_units").fetchone()[0]
    done = store.conn.execute(
        "SELECT COUNT(*) FROM text_units WHERE ru IS NOT NULL"
    ).fetchone()[0]
    print(f"\nИтого: {done} из {total} единиц переведено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
