#!/usr/bin/env python3
"""Этап 1: обход листингов и регистрация URL страниц в SQLite.

Примеры:
    python3 scripts/01_discover.py --brand honda --models freed,freed_hybrid
    python3 scripts/01_discover.py --models freed --max-pages 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import parse, urls  # noqa: E402
from minkara.config import load_models, load_sections, load_settings, selected_models  # noqa: E402
from minkara.db import Store  # noqa: E402
from minkara.http import BlockedError, Fetcher, FetchError  # noqa: E402


def save_raw(settings, info: dict, html: str) -> str:
    rel = urls.raw_relpath(info)
    path = settings.raw_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return rel


def profile_url(settings, uid: int, car: int) -> str:
    return f"{settings.base_url}/userid/{uid}/car/{car}/profile.aspx"


def main() -> int:
    parser = argparse.ArgumentParser(description="Обход листингов minkara")
    parser.add_argument("--brand", help="марка, например honda (по умолчанию все)")
    parser.add_argument("--models", help="список ключей моделей через запятую")
    parser.add_argument(
        "--match",
        help="подстрока в ключе/имени модели (например freed) — взять все совпадения",
    )
    parser.add_argument(
        "--sections",
        help="разделы через запятую (по умолчанию — включённые в config/models.yaml)",
    )
    parser.add_argument("--max-pages", type=int, default=0, help="ограничить число страниц листинга")
    parser.add_argument("--delay", type=float, help="пауза между запросами, сек")
    parser.add_argument("--fresh", action="store_true", help="игнорировать сохранённые листинги")
    args = parser.parse_args()

    overrides = {"delay": args.delay} if args.delay else {}
    settings = load_settings(**overrides)
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
    sections = load_sections(settings)
    if not models:
        print("Нет моделей под указанные фильтры. Проверьте config/models.yaml")
        return 1

    if args.sections:
        section_names = [s.strip() for s in args.sections.split(",") if s.strip()]
    else:
        section_names = [
            name for name, cfg in sections.items() if (cfg or {}).get("enabled")
        ]

    total_items = 0
    try:
        for model in models:
            for section in section_names:
                if section not in sections:
                    print(f"! раздел {section} не описан в config/models.yaml — пропуск")
                    continue
                if section not in ("note", "partsreview", "review"):
                    print(f"! {model.key}/{section}: раздел пока не поддержан — пропуск")
                    continue

                print(f"\n== {model.brand}/{model.key}/{section} ==")
                page_no = 1
                while True:
                    url = urls.canonical(
                        urls.listing_url(settings.base_url, model.brand, model.key, section, page_no)
                    )
                    info = urls.classify(url)
                    html = None
                    existing = store.conn.execute(
                        "SELECT state, file FROM pages WHERE url = ?", (url,)
                    ).fetchone()
                    if (
                        existing
                        and existing["state"] == "parsed"
                        and existing["file"]
                        and not args.fresh
                    ):
                        cached = settings.raw_dir / existing["file"]
                        if cached.exists():
                            html = cached.read_text(encoding="utf-8")
                    if html is None:
                        try:
                            html = fetcher.text(url)
                        except FetchError as exc:
                            # У части моделей страница за концом списка отдаёт 404,
                            # у других — пустую 200. И то, и другое значит «конец».
                            if "HTTP 404" in str(exc):
                                print(f"  стр. {page_no}: 404 — конец списка")
                                break
                            raise
                    if section == "note":
                        items = parse.parse_listing(html)
                    elif section == "partsreview":
                        items = parse.parse_product_listing(html)
                    else:
                        items = parse.parse_review_listing(html)
                    rel = save_raw(settings, info, html)
                    store.upsert_page(
                        url,
                        kind="listing",
                        brand=model.brand,
                        model=model.key,
                        section=section,
                        listing_page=page_no,
                        state="parsed",
                        file=rel,
                    )
                    if not items:
                        print(f"  стр. {page_no}: конец списка")
                        break

                    for item in items:
                        item_url = urls.canonical(
                            urls.absolute(settings.base_url, item["url"])
                        )
                        item_info = urls.classify(item_url)
                        if section == "note" and item_info["kind"] == "note":
                            store.upsert_page(
                                item_url,
                                kind="note",
                                brand=model.brand,
                                model=model.key,
                                section="note",
                                uid=item_info["uid"],
                                car=item_info["car"],
                                note=item_info["note"],
                                title=item["title"],
                            )
                            if int(item_info["car"]) == 0:
                                # Заметка не привязана к машине — профиль качать некуда.
                                continue
                            store.upsert_car(
                                int(item_info["car"]),
                                url=profile_url(
                                    settings, int(item_info["uid"]), int(item_info["car"])
                                ),
                                uid=int(item_info["uid"]),
                                brand=model.brand,
                                model=model.key,
                                state="new",
                            )
                        elif section == "partsreview" and item_info["kind"] == "product":
                            store.upsert_page(
                                item_url,
                                kind="product",
                                brand=model.brand,
                                model=model.key,
                                section="partsreview",
                                title=item["title"],
                            )
                        elif section == "review" and item_info["kind"] == "review":
                            store.upsert_page(
                                item_url,
                                kind="review",
                                brand=model.brand,
                                model=model.key,
                                section="review",
                                title=item["title"],
                            )
                    total_items += len(items)
                    print(f"  стр. {page_no}: +{len(items)} (всего {total_items})")
                    page_no += 1
                    if args.max_pages and page_no > args.max_pages:
                        print(f"  остановка по --max-pages={args.max_pages}")
                        break
    except BlockedError as exc:
        print(f"\nОШИБКА: {exc}")
        return 2
    except FetchError as exc:
        print(f"\nОШИБКА сети: {exc}")
        return 2

    stats = store.stats()
    print("\nГотово.")
    print(f"  страниц всего: {stats['pages']} ({stats['pages_by_kind']})")
    print(f"  машин в очереди: {stats['cars']}")
    print(f"  элементов найдено за запуск: {total_items}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
