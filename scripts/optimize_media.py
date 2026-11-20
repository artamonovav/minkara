#!/usr/bin/env python3
"""Конвертация медиа в WebP с уменьшением до max-size.

    python3 scripts/optimize_media.py --workers 8 --limit 20
    python3 scripts/optimize_media.py

Оригинал удаляется только если WebP меньше оригинала минимум на 5%.
Сборка умеет находить .webp, если исходного .jpg/.png уже нет.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara.config import load_settings  # noqa: E402


def convert_one(path_str: str, quality: int, max_size: int):
    from PIL import Image

    path = Path(path_str)
    try:
        with Image.open(path) as image:
            if getattr(image, "n_frames", 1) > 1:
                return None
            mode = "RGBA" if "A" in image.getbands() else "RGB"
            image = image.convert(mode)
            image.thumbnail((max_size, max_size), Image.LANCZOS)
            output = path.with_suffix(".webp")
            if output.exists():
                return None
            temp = output.with_suffix(".webp.tmp")
            image.save(temp, "WEBP", quality=quality, method=2)
        old_size = path.stat().st_size
        new_size = temp.stat().st_size
        if new_size >= old_size * 0.95:
            temp.unlink(missing_ok=True)
            return None
        path.unlink()
        temp.replace(output)
        return str(path), str(output), old_size, new_size
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="WebP-конвертация медиа")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--quality", type=int, default=75)
    parser.add_argument("--max-size", type=int, default=1280)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    files = [
        path
        for path in settings.assets_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in (".jpg", ".jpeg", ".png")
    ]
    if args.limit:
        files = files[: args.limit]
    print(f"Кандидатов: {len(files)} (quality={args.quality}, max={args.max_size})")
    if args.dry_run or not files:
        return 0

    started = time.time()
    converted = 0
    old_total = new_total = 0
    pairs: list[tuple[str, str, int, int]] = []
    work = partial(convert_one, quality=args.quality, max_size=args.max_size)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for index, result in enumerate(pool.map(work, [str(path) for path in files], chunksize=20), 1):
            if result:
                old_path, new_path, old_size, new_size = result
                pairs.append((old_path, new_path, old_size, new_size))
                converted += 1
                old_total += old_size
                new_total += new_size
            if index % 2000 == 0:
                print(f"  обработано {index}/{len(files)}, сконвертировано {converted}")

    if pairs:
        conn = sqlite3.connect(settings.db_path, timeout=60)
        for old_path, new_path, _old_size, new_size in pairs:
            old_rel = str(Path(old_path).relative_to(settings.assets_dir))
            new_rel = str(Path(new_path).relative_to(settings.assets_dir))
            conn.execute(
                "UPDATE assets SET file = ?, bytes = ? WHERE file = ?",
                (new_rel, new_size, old_rel),
            )
        conn.commit()
        conn.close()

    elapsed = time.time() - started
    print(
        f"Готово: {converted} файлов за {elapsed / 60:.1f} мин; "
        f"{old_total / 1024**3:.2f} ГБ → {new_total / 1024**3:.2f} ГБ "
        f"(экономия {(old_total - new_total) / 1024**3:.2f} ГБ)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
