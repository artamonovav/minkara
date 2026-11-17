"""Прогресс выполнения: `[x/y] % ETA` для терминала и лога."""
from __future__ import annotations

import sys
import time
from collections.abc import Callable


def _fmt(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class Progress:
    """Печатает прогресс не чаще `min_interval` секунд (или каждые `every`).

    total может быть числом или функцией — вторая нужна, когда очередь
    пополняется по ходу работы (например, отзывы, найденные на страницах
    товаров).
    """

    def __init__(
        self,
        total: int | Callable[[], int],
        label: str = "",
        every: int = 10,
        min_interval: float = 5.0,
    ) -> None:
        self.total = total
        self.label = label
        self.every = every
        self.min_interval = min_interval
        self.start = time.monotonic()
        self.last = 0.0
        self.tty = sys.stdout.isatty()
        self._last_len = 0

    def _total(self) -> int:
        return self.total() if callable(self.total) else self.total

    def update(self, done: int, extra: str = "") -> None:
        now = time.monotonic()
        total = self._total()
        finished = total > 0 and done >= total
        if not finished and done % self.every and now - self.last < self.min_interval:
            return
        self.last = now
        elapsed = max(now - self.start, 1e-6)
        rate = done / elapsed
        percent = (done / total * 100) if total else 0.0
        eta = (total - done) / rate if rate > 0 and total > done else 0.0
        parts = [
            f"[{done}/{total or '?'}]",
            f"{percent:5.1f}%",
        ]
        if rate:
            parts.append(f"{rate:.1f}/с")
        if eta:
            parts.append(f"ETA {_fmt(eta)}")
        if self.label:
            parts.append(self.label)
        if extra:
            parts.append(extra)
        line = "  ".join(parts)
        if self.tty:
            padding = max(self._last_len - len(line), 0)
            sys.stdout.write("\r" + line + " " * padding)
            sys.stdout.flush()
            self._last_len = len(line)
        else:
            print(line, flush=True)

    def close(self, done: int | None = None) -> None:
        if done is not None:
            self.update(done)
        if self.tty:
            sys.stdout.write("\n")
            sys.stdout.flush()
