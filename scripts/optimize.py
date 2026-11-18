#!/usr/bin/env python3
"""Оптимизация занимаемого места.

    python3 scripts/optimize.py --compress-raw --dedupe-assets --hardlink-out --vacuum

Что делает:
  --compress-raw   сжимает data/raw/**/*.html в .gz (pigz/gzip), оригиналы удаляет
  --dedupe-assets  одинаковые файлы в data/assets заменяет жёсткими ссылками
  --hardlink-out   проверяет, что out/site/media — жёсткие ссылки на data/assets
  --vacuum         VACUUM SQLite (запускать, когда нет записи в БД)
  --dry-run        только показать, что будет сделано
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara.config import load_settings  # noqa: E402


def du(path: Path) -> str:
    try:
        out = subprocess.run(
            ["du", "-sh", str(path)], capture_output=True, text=True, timeout=120
        )
        return out.stdout.split()[0] if out.stdout else "—"
    except Exception:
        return "—"


def compress_raw(settings, dry: bool) -> None:
    files = list(settings.raw_dir.rglob("*.html"))
    print(f"Сырой HTML: {len(files)} файлов, {du(settings.raw_dir)}")
    if dry or not files:
        return
    compressor = "pigz" if shutil.which("pigz") else "gzip"
    print(f"Сжимаю через {compressor}…")
    command = (
        f"find {settings.raw_dir} -name '*.html' -print0 "
        f"| xargs -0 -P 4 -n 20 {compressor} -9"
    )
    subprocess.run(command, shell=True, check=True)
    print(f"После сжатия: {du(settings.raw_dir)}")


def file_hash(path: Path) -> tuple[Path, str] | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return path, digest.hexdigest()
    except OSError:
        return None


def dedupe_assets(settings, dry: bool, workers: int = 8) -> None:
    files = [path for path in settings.assets_dir.rglob("*") if path.is_file()]
    print(f"Медиа: {len(files)} файлов, {du(settings.assets_dir)}")
    if dry or not files:
        return

    by_size: dict[int, list[Path]] = {}
    for path in files:
        try:
            by_size.setdefault(path.stat().st_size, []).append(path)
        except OSError:
            continue
    candidates = [path for group in by_size.values() if len(group) > 1 for path in group]
    print(f"Кандидатов на проверку (совпадает размер): {len(candidates)}")

    hashes: dict[str, Path] = {}
    saved = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(file_hash, candidates):
            if result is None:
                continue
            path, digest = result
            original = hashes.get(digest)
            if original is None:
                hashes[digest] = path
                continue
            try:
                size = path.stat().st_size
                path.unlink()
                os.link(original, path)
                saved += size
            except OSError as exc:
                print(f"  ! {path}: {exc}")
    print(f"Дедуплицировано, экономия ~{saved / 1024 / 1024:.1f} МБ")


def hardlink_out(settings, dry: bool) -> None:
    media = settings.site_dir / "media"
    if not media.exists():
        print("out/site/media нет — пропуск")
        return
    replaced = 0
    for path in media.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(media)
        source = settings.assets_dir / rel
        if not source.exists():
            continue
        try:
            if path.stat().st_ino == source.stat().st_ino:
                continue
            if dry:
                replaced += 1
                continue
            path.unlink()
            os.link(source, path)
            replaced += 1
        except OSError:
            continue
    print(f"Hardlinks в out/site/media: заменено {replaced}")


def vacuum(settings, dry: bool) -> None:
    if dry:
        print("VACUUM: пропуск (dry-run)")
        return
    before = settings.db_path.stat().st_size
    conn = sqlite3.connect(settings.db_path, timeout=60)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("VACUUM")
    conn.close()
    after = settings.db_path.stat().st_size
    print(f"SQLite: {before / 1024**2:.0f} МБ → {after / 1024**2:.0f} МБ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Оптимизация места")
    parser.add_argument("--compress-raw", action="store_true")
    parser.add_argument("--dedupe-assets", action="store_true")
    parser.add_argument("--hardlink-out", action="store_true")
    parser.add_argument("--vacuum", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    print(f"До: data {du(settings.data_dir)}, out {du(settings.out_dir)}")
    if args.compress_raw:
        compress_raw(settings, args.dry_run)
    if args.dedupe_assets:
        dedupe_assets(settings, args.dry_run)
    if args.hardlink_out:
        hardlink_out(settings, args.dry_run)
    if args.vacuum:
        vacuum(settings, args.dry_run)
    print(f"После: data {du(settings.data_dir)}, out {du(settings.out_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
