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
        default="note",
        help="разделы через запятую (пока поддержан note; остальные — фазы M3/M4)",
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

    total_notes = 0
    try:
        for model in models:
            for section in [s.strip() for s in args.sections.split(",") if s.strip()]:
                if section not in sections:
                    print(f"! раздел {section} не описан в config/models.yaml — пропуск")
                    continue
                if section != "note":
                    print(f"! {model.key}/{section}: обход каталога будет в фазе M3/M4 — пропуск")
                    continue

                print(f"\n== {model.brand}/{model.key}/{section} ==")
                page_no = 1
                while True:
                    url = urls.canonical(
                        urls.listing_url(settings.base_url, model.brand, model.key, section, page_no)
                    )
                    info = urls.classify(url)
                    html = fetcher.text(url)
                    items = parse.parse_listing(html)
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
                        note_url = urls.canonical(urls.absolute(settings.base_url, item["url"]))
                        note_info = urls.classify(note_url)
                        if note_info["kind"] != "note":
                            continue
                        store.upsert_page(
                            note_url,
                            kind="note",
                            brand=model.brand,
                            model=model.key,
                            section="note",
                            uid=note_info["uid"],
                            car=note_info["car"],
                            note=note_info["note"],
                            title=item["title"],
                        )
                        if int(note_info["car"]) == 0:
                            # Заметка не привязана к конкретной машине —
                            # профиль качать некуда, поколение останется неизвестным.
                            continue
                        store.upsert_car(
                            int(note_info["car"]),
                            url=profile_url(settings, int(note_info["uid"]), int(note_info["car"])),
                            uid=int(note_info["uid"]),
                            brand=model.brand,
                            model=model.key,
                            state="new",
                        )
                    total_notes += len(items)
                    print(f"  стр. {page_no}: +{len(items)} (всего {total_notes})")
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
    print(f"  заметок найдено за запуск: {total_notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
