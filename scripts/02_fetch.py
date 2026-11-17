#!/usr/bin/env python3
"""Этап 2: скачивание страниц, профилей машин и медиа.

Примеры:
    python3 scripts/02_fetch.py --limit 20
    python3 scripts/02_fetch.py --kind note --no-assets
    python3 scripts/02_fetch.py --retry-errors
    python3 scripts/02_fetch.py --reparse
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import parse, urls  # noqa: E402
from minkara.config import (  # noqa: E402
    generation_for,
    load_generation_rules,
    load_settings,
)
from minkara.db import Store  # noqa: E402
from minkara.http import BlockedError, Fetcher, FetchError  # noqa: E402

PARSERS = {
    "note": parse.parse_note,
    "parts": parse.parse_parts,
    "review": parse.parse_review,
    "product": parse.parse_product,
    "car": parse.parse_profile,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def save_raw(settings, info: dict, html: str) -> str:
    rel = urls.raw_relpath(info)
    path = settings.raw_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return rel


def register_assets(store: Store, settings, page_url: str, parsed: dict, with_thumbs: bool) -> None:
    images: list[str] = []
    for item in parsed.get("gallery") or []:
        if item.get("image"):
            images.append(item["image"])
    if parsed.get("image"):
        images.append(parsed["image"])
    images.extend(parsed.get("images") or [])
    for src in images:
        if not src:
            continue
        absolute = urls.canonical(urls.absolute(settings.base_url, src))
        store.add_asset(absolute, page_url=page_url, kind="image")


def parse_page(kind: str, html: str, url: str) -> dict:
    parser = PARSERS.get(kind)
    if parser is None:
        return {"url": url}
    return parser(html, url)


def fetch_cars(store: Store, settings, fetcher: Fetcher, rules: dict, limit: int | None) -> int:
    done = 0
    for car in store.pending_cars(limit=limit):
        car_id = int(car["car_id"])
        if car_id == 0:
            store.upsert_car(0, state="skipped")
            continue
        url = car["url"] or (
            f"{settings.base_url}/userid/{car['uid']}/car/{car_id}/profile.aspx"
        )
        try:
            html = fetcher.text(url)
        except FetchError as exc:
            store.upsert_car(car_id, state="error", error=str(exc))
            print(f"  ! car {car_id}: {exc}")
            continue
        info = urls.classify(url)
        save_raw(settings, info, html)
        parsed = parse.parse_profile(html, url)
        generation = generation_for(
            rules,
            car["brand"],
            car["model"],
            parsed.get("code"),
            parsed.get("grade"),
        )
        store.upsert_car(
            car_id,
            state="parsed",
            url=url,
            grade=parsed.get("grade"),
            code=parsed.get("code"),
            generation=generation,
            meta_json=json.dumps(parsed, ensure_ascii=False),
            fetched_at=now(),
            error=None,
        )
        store.apply_generation(car_id, generation)
        done += 1
        print(f"  car {car_id}: {parsed.get('code') or '?'} -> поколение {generation}")
    return done


def fetch_pages(
    store: Store,
    settings,
    fetcher: Fetcher,
    rules: dict,
    kinds: list[str],
    limit: int | None,
    with_thumbs: bool,
) -> int:
    done = 0
    for page in store.pending_pages(kinds=kinds, limit=limit):
        url = page["url"]
        kind = page["kind"]
        try:
            html = fetcher.text(url)
        except FetchError as exc:
            store.set_page(page["id"], state="error", error=str(exc))
            print(f"  ! {kind} {url}: {exc}")
            continue
        info = urls.classify(url)
        rel = save_raw(settings, info, html)
        parsed = parse_page(kind, html, url)
        generation = page["generation"]
        if generation is None and kind == "review" and parsed.get("grade"):
            generation = generation_for(
                rules, page["brand"], page["model"], None, parsed.get("grade")
            )
        store.set_page(
            page["id"],
            state="parsed",
            http_code=200,
            file=rel,
            title=parsed.get("title") or page["title"],
            generation=generation,
            meta_json=json.dumps(parsed, ensure_ascii=False),
            fetched_at=now(),
            error=None,
        )
        register_assets(store, settings, url, parsed, with_thumbs)
        if kind == "product":
            # Страница товара содержит ссылки на отзывы — регистрируем их.
            for href in (parsed.get("reviews") or []):
                review_url = urls.canonical(urls.absolute(settings.base_url, href))
                review_info = urls.classify(review_url)
                if review_info["kind"] != "parts":
                    continue
                store.upsert_page(
                    review_url,
                    kind="parts",
                    brand=page["brand"],
                    model=page["model"],
                    section="partsreview",
                    uid=review_info["uid"],
                    car=review_info["car"],
                    note=review_info["note"],
                )
        done += 1
        print(f"  {kind} {page['id']}: {parsed.get('title') or url}")
    return done


def fetch_assets(store: Store, settings, fetcher: Fetcher, limit: int | None) -> int:
    done = 0
    for asset in store.pending_assets(limit=limit):
        url = asset["url"]
        rel = urls.asset_relpath(url)
        dest = settings.assets_dir / rel
        if dest.exists():
            store.set_asset(asset["id"], state="done", file=rel, bytes=dest.stat().st_size)
            continue
        try:
            size = fetcher.download(url, dest)
        except FetchError as exc:
            store.set_asset(asset["id"], state="error", error=str(exc))
            print(f"  ! asset {url}: {exc}")
            continue
        store.set_asset(asset["id"], state="done", file=rel, bytes=size, http_code=200)
        done += 1
        if done % 25 == 0:
            print(f"  ... картинок скачано: {done}")
    return done


def reparse(store: Store, settings) -> int:
    """Повторный разбор сохранённого HTML без обращения к сети."""
    done = 0
    rows = store.conn.execute(
        "SELECT * FROM pages WHERE state = 'parsed' AND file IS NOT NULL AND meta_json IS NOT NULL"
    ).fetchall()
    for page in rows:
        path = settings.raw_dir / page["file"]
        if not path.exists():
            continue
        html = path.read_text(encoding="utf-8")
        parsed = parse_page(page["kind"], html, page["url"])
        store.set_page(
            page["id"],
            title=parsed.get("title") or page["title"],
            meta_json=json.dumps(parsed, ensure_ascii=False),
        )
        register_assets(store, settings, page["url"], parsed, True)
        done += 1
    return done


def main() -> int:
    parser = argparse.ArgumentParser(description="Скачивание страниц minkara")
    parser.add_argument("--limit", type=int, default=0, help="сколько страниц обработать")
    parser.add_argument("--cars-limit", type=int, default=0, help="сколько профилей машин обработать")
    parser.add_argument("--assets-limit", type=int, default=0, help="сколько медиа скачать")
    parser.add_argument(
        "--kind",
        default="note,product,parts,review,qa,model",
        help="типы страниц через запятую",
    )
    parser.add_argument(
        "--only-assets", action="store_true", help="только докачать медиа, без страниц"
    )
    parser.add_argument("--no-assets", action="store_true", help="не скачивать медиа")
    parser.add_argument("--with-thumbs", action="store_true", help="качать и миниатюры")
    parser.add_argument("--retry-errors", action="store_true", help="повторить страницы с ошибками")
    parser.add_argument("--reparse", action="store_true", help="только переразобрать сохранённый HTML")
    parser.add_argument("--delay", type=float, help="пауза между запросами, сек")
    args = parser.parse_args()

    overrides = {"delay": args.delay} if args.delay else {}
    settings = load_settings(**overrides)
    store = Store(settings.db_path)
    store.init()

    if args.reparse:
        count = reparse(store, settings)
        print(f"Переразобрано страниц: {count}")
        return 0

    if args.retry_errors:
        count = store.retry_errors()
        print(f"Сброшено в очередь после ошибок: {count}")

    fetcher = Fetcher(settings)
    rules = load_generation_rules(settings)
    limit = args.limit or None
    cars_limit = args.cars_limit or None
    assets_limit = args.assets_limit or None
    kinds = [k.strip() for k in args.kind.split(",") if k.strip()]

    try:
        cars = pages = assets = 0
        if not args.only_assets:
            print("== профили машин ==")
            cars = fetch_cars(store, settings, fetcher, rules, cars_limit)
            print("== страницы ==")
            pages = fetch_pages(
                store, settings, fetcher, rules, kinds, limit, args.with_thumbs
            )
        if not args.no_assets:
            print("== медиа ==")
            assets = fetch_assets(store, settings, fetcher, assets_limit)
    except BlockedError as exc:
        print(f"\nОШИБКА: {exc}")
        return 2
    except FetchError as exc:
        print(f"\nОШИБКА сети: {exc}")
        return 2

    stats = store.stats()
    print("\nГотово.")
    print(f"  профилей машин: {cars}")
    print(f"  страниц: {pages}")
    print(f"  медиа: {assets}")
    print(f"  состояние страниц: {stats['pages_by_state']}")
    print(f"  состояние медиа: {stats['assets_by_state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
