#!/usr/bin/env python3
"""Сводка состояния архива: этап выкачки, БД, квота, диск."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402

try:
    from minkara import deepl as deepl_api
except Exception:  # pragma: no cover
    deepl_api = None


def last_line(path: Path, pattern: str) -> str:
    if not path.exists():
        return ""
    matches = [
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if re.search(pattern, line)
    ]
    return matches[-1] if matches else ""


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "КБ", "МБ", "ГБ"):
        if size < 1024 or unit == "ГБ":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ГБ"


def dir_size(path: Path) -> int:
    total = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    return total


def main() -> int:
    as_json = "--json" in sys.argv
    settings = load_settings()
    store = Store(settings.db_path)
    store.init()

    log = settings.work_dir / "crawl.log"
    stage = last_line(log, r"^=== .*(discover|fetch|медиа|перевод|сборка|DONE)")
    progress = last_line(log, r"^\[[0-9]+/[0-9]+\]|^  стр\.")

    pages_by_kind = {
        row["kind"]: row["n"]
        for row in store.conn.execute("SELECT kind, COUNT(*) n FROM pages GROUP BY kind")
    }
    pages_by_state = {
        row["state"]: row["n"]
        for row in store.conn.execute("SELECT state, COUNT(*) n FROM pages GROUP BY state")
    }
    assets_total = store.conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    assets_done = store.conn.execute(
        "SELECT COUNT(*) FROM assets WHERE state = 'done'"
    ).fetchone()[0]
    units_total = store.conn.execute("SELECT COUNT(*) FROM text_units").fetchone()[0]
    units_done = store.conn.execute(
        "SELECT COUNT(*) FROM text_units WHERE ru IS NOT NULL"
    ).fetchone()[0]
    cars_total = store.conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
    cars_done = store.conn.execute(
        "SELECT COUNT(*) FROM cars WHERE state IN ('parsed','skipped','error')"
    ).fetchone()[0]

    quota = None
    key = os.environ.get("MINKARA_TRANSLATE_API_KEY") or os.environ.get("DEEPL_API_KEY", "")
    if key and deepl_api is not None:
        try:
            quota = deepl_api.usage(key)
        except Exception:
            quota = None

    running = bool(
        subprocess.run(
            ["pgrep", "-f", "crawl_all|02_fetch|01_discover"],
            capture_output=True,
            text=True,
        ).stdout.strip()
    )

    data = {
        "running": running,
        "stage": stage,
        "progress": progress,
        "pages": pages_by_kind,
        "states": pages_by_state,
        "cars": {"done": cars_done, "total": cars_total},
        "assets": {"done": assets_done, "total": assets_total},
        "translation": {"done": units_done, "total": units_total},
        "deepl": quota,
        "disk": {
            "data": human_bytes(dir_size(settings.data_dir)),
            "out": human_bytes(dir_size(settings.out_dir)),
        },
    }

    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    print(f"Выкачка: {'ИДЁТ' if running else 'остановлена'}")
    if stage:
        print(f"  этап: {stage}")
    if progress:
        print(f"  прогресс: {progress}")
    print()
    print("Страницы по типам:")
    for kind, count in sorted(pages_by_kind.items()):
        print(f"  {kind:10s} {count:7d}")
    print(f"  состояния: {pages_by_state}")
    print()
    print(f"Машины:      {cars_done}/{cars_total}")
    print(f"Медиа:       {assets_done}/{assets_total}")
    print(f"Перевод:     {units_done}/{units_total}")
    if quota:
        print(
            f"DeepL:       остаток {quota['remaining']} из {quota['limit']} "
            f"(использовано {quota['used']})"
        )
    print(f"Диск:        data {data['disk']['data']}, out {data['disk']['out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
