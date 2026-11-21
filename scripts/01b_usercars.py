#!/usr/bin/env python3
"""Этап 1b: обход списков машин (愛車紹介) по каждой модели.

Модельные листинги заметок отдают только последние ~2000 записей.
Полный список машин модели доступен в /car/<brand>/<model>/usercar/:
там перечислены все владельцы (включая прошлые машины), по ~15 на страницу.

Скрипт регистрирует машины в таблице cars, чтобы затем обойти полные
списки заметок каждой машины (01c_car_notes.py).
"""
from __future__ import annotations

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara.config import load_models, load_settings, selected_models  # noqa: E402
from minkara.db import Store  # noqa: E402
from minkara.http import BlockedError, Fetcher, FetchError  # noqa: E402

CAR_LINK = re.compile(r'href="/userid/(\d+)/car/(\d+)/profile\.aspx"')


def page_url(base: str, brand: str, model: str, pn: int, srt: int) -> str:
    url = f"{base}/car/{brand}/{model}/usercar/?srt={srt}"
    return url if pn <= 1 else f"{url}&pn={pn}"


def parse_cars(html: str) -> list[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    for uid, car in CAR_LINK.findall(html):
        seen.add((int(uid), int(car)))
    return sorted(seen)


def fetch_page(fetcher: Fetcher, url: str) -> str | None:
    """Возвращает HTML или None, если страница за концом списка (404)."""
    try:
        return fetcher.text(url)
    except FetchError as exc:
        if "HTTP 404" in str(exc):
            return None
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Обход списков машин по моделям")
    parser.add_argument("--brand", default="honda")
    parser.add_argument("--models", help="ключи моделей через запятую (по умолчанию все)")
    parser.add_argument(
        "--match", help="подстрока в ключе/имени модели (например freed)"
    )
    parser.add_argument("--max-pages", type=int, default=300)
    parser.add_argument(
        "--sorts",
        default="8,1",
        help="порядки сортировки списка через запятую (разные окна по 200 страниц)",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    settings = load_settings(delay=args.delay)
    store = Store(settings.db_path)
    store.init()
    fetcher = Fetcher(settings)

    models = selected_models(
        load_models(settings),
        args.brand,
        args.models.split(",") if args.models else None,
    )
    if args.match:
        needle = args.match.lower()
        models = [
            m for m in models if needle in m.key.lower() or needle in m.name.lower()
        ]
    if not models:
        print("Нет моделей под указанные фильтры")
        return 1

    total_new = 0
    sorts = [int(s.strip()) for s in args.sorts.split(",") if s.strip()]
    for model in models:
        print(f"\n=== {model.brand}/{model.key} ===", flush=True)
        found: set[tuple[int, int]] = set()
        before = store.conn.execute(
            "SELECT COUNT(*) FROM cars WHERE model = ?", (model.key,)
        ).fetchone()[0]
        for srt in sorts:
            print(f"  -- сортировка srt={srt} --", flush=True)
            found_sort: set[tuple[int, int]] = set()
            pn = 1
            empty = False
            while pn <= args.max_pages and not empty:
                batch = list(range(pn, min(pn + args.workers, args.max_pages + 1)))
                batch_urls = [
                    page_url(settings.base_url, model.brand, model.key, p, srt)
                    for p in batch
                ]
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    results = list(
                        pool.map(partial(fetch_page, fetcher), batch_urls)
                    )
                for p, html in zip(batch, results, strict=True):
                    if html is None or 'class="page-num current"' not in html:
                        empty = True
                        print(f"  стр. {p}: конец списка", flush=True)
                        break
                    cars = parse_cars(html)
                    for uid, car_id in cars:
                        found_sort.add((uid, car_id))
                        if (uid, car_id) in found:
                            continue
                        found.add((uid, car_id))
                        store.upsert_car(
                            car_id,
                            url=(
                                f"{settings.base_url}/userid/{uid}/car/{car_id}/profile.aspx"
                            ),
                            uid=uid,
                            brand=model.brand,
                            model=model.key,
                        )
                    if p % 20 == 0 or p == 1:
                        print(
                            f"  стр. {p}: в этом порядке {len(found_sort)}, "
                            f"всего {len(found)}",
                            flush=True,
                        )
                pn += args.workers
        after = store.conn.execute(
            "SELECT COUNT(*) FROM cars WHERE model = ?", (model.key,)
        ).fetchone()[0]
        total_new += after - before
        print(
            f"  итог: найдено {len(found)}, в базе по модели {after} "
            f"(+{after - before})",
            flush=True,
        )

    total = store.conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
    print(f"\nВсего машин в базе: {total}, добавлено за запуск: {total_new}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlockedError, FetchError) as exc:
        print(f"\nОШИБКА: {exc}")
        raise SystemExit(2) from exc
