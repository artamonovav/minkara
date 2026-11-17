#!/usr/bin/env python3
"""Настройка MCP-серверов OpenCode (V2) для проекта.

Мержит записи в mcp.servers файла opencode.json, не трогая остальные ключи.
Идемпотентен: повторный запуск не дублирует серверы.

Серверы:
    sqlite      — доступ к data/archive.sqlite (DBHub; старый mcp-server-sqlite
                  несовместим с текущим MCP SDK)
    fetch       — точечные HTTP-запросы
    filesystem  — доступ к каталогу проекта
    git         — история репозитория
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara.db import Store  # noqa: E402

CONFIG_PATH = ROOT / "opencode.json"


def build_servers() -> dict:
    db_path = ROOT / "data" / "archive.sqlite"
    return {
        "sqlite": {
            "type": "local",
            "command": [
                "npx",
                "-y",
                "@bytebase/dbhub@1.7.1",
                "--transport",
                "stdio",
                "--dsn",
                f"sqlite:///{db_path}",
            ],
            "cwd": str(ROOT),
        },
        "fetch": {
            "type": "local",
            "command": ["uvx", "mcp-server-fetch"],
            "cwd": str(ROOT),
        },
        "filesystem": {
            "type": "local",
            "command": [
                "npx",
                "-y",
                "@modelcontextprotocol/server-filesystem",
                str(ROOT),
            ],
            "cwd": str(ROOT),
        },
        "git": {
            "type": "local",
            "command": ["uvx", "mcp-server-git", "--repository", str(ROOT)],
            "cwd": str(ROOT),
        },
    }


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {"$schema": "https://opencode.ai/config.json"}
    text = CONFIG_PATH.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"opencode.json содержит невалидный JSON: {exc}") from exc


def main() -> int:
    # База должна существовать: sqlite MCP открывает файл при старте.
    db_path = ROOT / "data" / "archive.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = Store(db_path)
    store.init()
    store.close()

    if not shutil.which("uvx"):
        print("! uvx не найден: MCP-серверы на uvx не запустятся. Установите uv.")
    if not shutil.which("npx"):
        print("! npx не найден: filesystem MCP не запустится. Установите Node.js.")

    config = load_config()
    config.setdefault("$schema", "https://opencode.ai/config.json")
    mcp = config.setdefault("mcp", {})
    servers = mcp.setdefault("servers", {})

    added, updated, same = [], [], []
    for name, spec in build_servers().items():
        if name not in servers:
            servers[name] = spec
            added.append(name)
        elif servers[name] != spec:
            servers[name] = spec
            updated.append(name)
        else:
            same.append(name)

    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Конфиг: {CONFIG_PATH}")
    print(f"  добавлено:  {', '.join(added) or '—'}")
    print(f"  обновлено:  {', '.join(updated) or '—'}")
    print(f"  без изменений: {', '.join(same) or '—'}")
    print("Проверить: opencode mcp list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
