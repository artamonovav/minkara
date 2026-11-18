"""Чтение сырых файлов с поддержкой сжатых копий (.gz)."""
from __future__ import annotations

import gzip
from pathlib import Path


def read_text(path: Path) -> str:
    """Читает HTML как есть или из .gz, если оригинал сжат."""
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    compressed = Path(str(path) + ".gz")
    if compressed.exists():
        with gzip.open(compressed, "rt", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    raise FileNotFoundError(path)
