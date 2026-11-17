"""DeepL API: перевод, проверка квоты и выбор эндпоинта."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request


def endpoint(api_key: str) -> str:
    return (
        "https://api-free.deepl.com/v2"
        if api_key.endswith(":fx")
        else "https://api.deepl.com/v2"
    )


def _request(url: str, api_key: str, data: bytes | None = None, timeout: int = 120) -> dict:
    headers = {"Authorization": f"DeepL-Auth-Key {api_key}"}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def usage(api_key: str) -> dict:
    """Возвращает {'used': int, 'limit': int, 'remaining': int}."""
    data = _request(f"{endpoint(api_key)}/usage", api_key, timeout=30)
    used = int(data.get("character_count", 0))
    limit = int(data.get("character_limit", 0))
    return {"used": used, "limit": limit, "remaining": max(limit - used, 0)}


def translate(api_key: str, texts: list[str]) -> list[str]:
    """Переводит пачку текстов JA -> RU. До 50 элементов за запрос."""
    if not texts:
        return []
    fields = [
        ("auth_key", api_key),
        ("source_lang", "JA"),
        ("target_lang", "RU"),
    ]
    fields.extend(("text", text) for text in texts)
    data = urllib.parse.urlencode(fields).encode()
    payload = _request(f"{endpoint(api_key)}/translate", api_key, data=data)
    return [item["text"] for item in payload["translations"]]
