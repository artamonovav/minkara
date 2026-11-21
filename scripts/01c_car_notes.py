#!/usr/bin/env python3
"""Обход полных списков заметок по каждой машине.

Модельные листинги показывают не все старые заметки. Этот этап идёт по
/userid/<uid>/car/<car>/note.aspx?page=N для всех машин из таблицы cars
и регистрирует пропущенные заметки.
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import urls  # noqa: E402
from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402
from minkara.http import BlockedError, Fetcher, FetchError  # noqa: E402
from minkara.progress import Progress  # noqa: E402


def car_notes(settings, fetcher: Fetcher, car, max_pages: int) -> tuple:
    uid = int(car["uid"])
    car_id = int(car["car_id"])
    found: list[str] = []
    seen: set[str] = set()
    pages_done = 0
    for page in range(1, max_pages + 1):
        url = f"{settings.base_url}/userid/{uid}/car/{car_id}/note.aspx"
        if page > 1:
            url += f"?page={page}"
        try:
            html = fetcher.text(url)
        except FetchError:
            break
        links = re.findall(
            rf'href="(?:https://minkara\.carview\.co\.jp)?(/userid/{uid}/car/{car_id}/\d+/note\.aspx)"',
            html,
        )
        if not links:
            break
        new = [link for link in dict.fromkeys(links) if link not in seen]
        if page > 1 and not new:
            break
        pages_done = page
        for link in new:
            seen.add(link)
            found.append(urls.canonical(urls.absolute(settings.base_url, link)))
    return car, found, pages_done


def main() -> int:
    parser = argparse.ArgumentParser(description="Обход заметок всех машин")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--models", help="ключи моделей через запятую")
    parser.add_argument(
        "--refresh", action="store_true", help="обходить и уже обработанные машины"
    )
    args = parser.parse_args()

    settings = load_settings(delay=args.delay)
    store = Store(settings.db_path)
    store.init()
    fetcher = Fetcher(settings)

    sql = "SELECT * FROM cars WHERE uid IS NOT NULL AND car_id > 0"
    params: list[object] = []
    if args.models:
        keys = [k.strip() for k in args.models.split(",") if k.strip()]
        sql += f" AND model IN ({','.join('?' for _ in keys)})"
        params.extend(keys)
    if not args.refresh:
        sql += " AND car_id NOT IN (SELECT car_id FROM car_notes_done)"
    sql += " ORDER BY car_id"
    cars = store.conn.execute(sql, params).fetchall()
    if args.limit:
        cars = cars[: args.limit]
    before = store.conn.execute("SELECT COUNT(*) FROM pages WHERE kind='note'").fetchone()[0]
    progress = Progress(len(cars), "машины")
    done = 0

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(car_notes, settings, fetcher, car, args.max_pages)
                for car in cars
            ]
            for future in as_completed(futures):
                car, found, pages_done = future.result()
                for url in found:
                    info = urls.classify(url)
                    if info["kind"] != "note":
                        continue
                    store.upsert_page(
                        url,
                        kind="note",
                        brand=car["brand"],
                        model=car["model"],
                        section="note",
                        uid=int(car["uid"]),
                        car=int(car["car_id"]),
                        note=int(info["note"]),
                    )
                store.conn.execute(
                    "INSERT OR REPLACE INTO car_notes_done(car_id, pages, found) "
                    "VALUES (?, ?, ?)",
                    (int(car["car_id"]), pages_done, len(found)),
                )
                store.conn.commit()
                done += 1
                progress.update(done, f"car {car['car_id']}: {len(found)} заметок")
    except BlockedError as exc:
        print(f"\nОШИБКА: {exc}")
        return 2
    except FetchError as exc:
        print(f"\nОШИБКА сети: {exc}")
        return 2

    progress.close(done)
    after = store.conn.execute("SELECT COUNT(*) FROM pages WHERE kind='note'").fetchone()[0]
    print(f"\nМашин: {len(cars)}, заметок было {before}, стало {after}, добавлено {after - before}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
