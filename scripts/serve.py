#!/usr/bin/env python3
"""Опциональный локальный сервер для просмотра архива.

Нужен только если хочется «как настоящий сайт» (нормальные URL, без file://).
По умолчанию отдаёт out/site на 127.0.0.1:8765.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara.config import load_settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Локальный просмотр архива")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    directory = settings.site_dir
    if not (directory / "index.html").exists():
        print("Сайт ещё не собран. Запустите: python3 scripts/04_build.py")
        return 1

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(directory)
    )
    server = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Сервер: {url}  (Ctrl-C для остановки)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
