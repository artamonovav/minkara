"""Вежливый HTTP-клиент: ограничение частоты, повторы, детект geo-блока."""
from __future__ import annotations

import threading
import time
from pathlib import Path

import requests

from .config import Settings


class FetchError(RuntimeError):
    """Не удалось получить страницу после всех повторов."""


class BlockedError(FetchError):
    """Сайт вернул 403 — вероятно, geo-блок (нужен VPN вне РФ)."""


class RateLimiter:
    """Общий для потоков ограничитель: не чаще одного запроса в `delay`."""

    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
            self._last = time.monotonic()


class Fetcher:
    def __init__(self, settings: Settings, delay: float | None = None) -> None:
        self.settings = settings
        self.limiter = RateLimiter(settings.delay if delay is None else delay)
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": self.settings.user_agent,
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,*/*;q=0.8"
                    ),
                    "Accept-Language": "ja,en;q=0.8",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                }
            )
            self._local.session = session
        return session

    def _wait(self) -> None:
        self.limiter.wait()

    def get(self, url: str) -> requests.Response:
        last_error: str = ""
        for attempt in range(1, self.settings.retries + 1):
            self._wait()
            try:
                response = self.session.get(
                    url, timeout=self.settings.timeout, allow_redirects=True
                )
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt == self.settings.retries:
                    break
                time.sleep(min(2**attempt, 30))
                continue

            if response.status_code == 403:
                raise BlockedError(
                    "403 Forbidden от minkara.carview.co.jp. Это geo-блок: "
                    "включите VPN/прокси с выходом за пределы РФ и повторите."
                )
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {response.status_code}"
                if attempt == self.settings.retries:
                    break
                retry_after = response.headers.get("Retry-After")
                pause = float(retry_after) if (retry_after or "").isdigit() else 2**attempt
                time.sleep(min(pause, 60))
                continue
            if response.status_code >= 400:
                raise FetchError(f"HTTP {response.status_code}: {url}")
            return response
        raise FetchError(f"Не удалось получить {url}: {last_error}")

    def text(self, url: str) -> str:
        response = self.get(url)
        response.encoding = response.encoding or "utf-8"
        return response.text

    def download(self, url: str, dest: Path) -> int:
        """Скачивает файл во временный путь и атомарно переименовывает."""
        response = self.get(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    fh.write(chunk)
        tmp.replace(dest)
        return dest.stat().st_size
