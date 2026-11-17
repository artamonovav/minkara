"""Канонизация URL, классификация страниц и раскладка файлов на диске."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Параметры, которые влияют на содержимое страницы и должны сохраняться.
KEEP_PARAMS = {"pn", "bi", "sci", "ci", "mk", "br", "id", "cid", "pt"}

SECTIONS = {"note", "partsreview", "review", "photo", "qa"}

_LISTING_RE = re.compile(r"^/car/(?P<brand>[^/]+)/(?P<model>[^/]+)/(?P<section>[^/]+)/$")
_MODEL_RE = re.compile(r"^/car/(?P<brand>[^/]+)/(?P<model>[^/]+)/$")
_NOTE_RE = re.compile(r"^/userid/(?P<uid>\d+)/car/(?P<car>\d+)/(?P<note>\d+)/note\.aspx$")
_PARTS_RE = re.compile(r"^/userid/(?P<uid>\d+)/car/(?P<car>\d+)/(?P<note>\d+)/parts\.aspx$")
_CAR_RE = re.compile(r"^/userid/(?P<uid>\d+)/car/(?P<car>\d+)/profile\.aspx$")
_REVIEW_RE = re.compile(r"^/car/(?P<brand>[^/]+)/(?P<model>[^/]+)/review/detail\.aspx$")
_QA_RE = re.compile(r"^/car/(?P<brand>[^/]+)/(?P<model>[^/]+)/qa/unit(?P<unit>\d+)/$")
_PRODUCT_RE = re.compile(r"^(?:/car/[^/]+/[^/]+)?/partsreview/parts\.aspx$")


def absolute(base: str, href: str) -> str:
    return urljoin(base, href)


def canonical(url: str) -> str:
    """Приводит URL к каноническому виду.

    * https и нижний регистр хоста;
    * без фрагмента;
    * только значимые query-параметры, отсортированные по имени;
    * ?pn=1 эквивалентен отсутствию pn.
    """
    parts = urlsplit(url.strip())
    scheme = "https"
    host = (parts.hostname or "").lower()
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    path = parts.path or "/"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k in KEEP_PARAMS]
    query = [(k, v) for k, v in query if not (k == "pn" and v == "1")]
    query.sort()
    return urlunsplit((scheme, host + port, path, urlencode(query), ""))


def classify(url: str) -> dict:
    """Определяет тип страницы и извлекает параметры из пути."""
    parts = urlsplit(url)
    path = parts.path or "/"
    host = (parts.hostname or "").lower()
    info: dict = {
        "url": url,
        "host": host,
        "kind": "other",
        "brand": None,
        "model": None,
        "section": None,
        "uid": None,
        "car": None,
        "note": None,
        "pn": None,
    }
    if host.endswith("snsimg.carview.co.jp") or re.search(
        r"\.(jpe?g|png|gif|webp|svg|css|js|ico)$", path, re.I
    ):
        info["kind"] = "asset"
        return info

    if _PRODUCT_RE.match(path):
        product_id = dict(parse_qsl(parts.query)).get("pt")
        if product_id:
            info.update(kind="product", pt=product_id)
            return info
    m = _NOTE_RE.match(path)
    if m:
        info.update(kind="note", **m.groupdict())
        return info
    m = _PARTS_RE.match(path)
    if m:
        info.update(kind="parts", **m.groupdict())
        return info
    m = _CAR_RE.match(path)
    if m:
        info.update(kind="car", **m.groupdict())
        return info
    m = _REVIEW_RE.match(path)
    if m:
        info.update(kind="review", **m.groupdict())
        info["cid"] = dict(parse_qsl(parts.query)).get("cid")
        return info
    m = _QA_RE.match(path)
    if m:
        info.update(kind="qa", **m.groupdict())
        return info
    m = _LISTING_RE.match(path)
    if m and m.group("section") in SECTIONS:
        info.update(kind="listing", **m.groupdict())
        info["pn"] = int(dict(parse_qsl(parts.query)).get("pn") or 1)
        return info
    m = _MODEL_RE.match(path)
    if m:
        info.update(kind="model", **m.groupdict())
        return info
    return info


def listing_url(base_url: str, brand: str, model: str, section: str, pn: int = 1) -> str:
    url = f"{base_url}/car/{brand}/{model}/{section}/"
    return url if pn <= 1 else f"{url}?pn={pn}"


def raw_relpath(info: dict) -> str:
    """Относительный путь для сохранения HTML в data/raw."""
    kind = info["kind"]
    if kind == "listing":
        pn = info.get("pn") or 1
        name = "index.html" if pn <= 1 else f"pn{pn}.html"
        return f"car/{info['brand']}/{info['model']}/{info['section']}/{name}"
    if kind in ("note", "parts"):
        ext = "note" if kind == "note" else "parts"
        return f"userid/{info['uid']}/car/{info['car']}/{info['note']}/{ext}.html"
    if kind == "car":
        return f"userid/{info['uid']}/car/{info['car']}/profile.html"
    if kind == "product":
        return f"partsreview/product-{info['pt']}.html"
    if kind == "review":
        return f"car/{info['brand']}/{info['model']}/review/{info.get('cid')}.html"
    if kind == "qa":
        return f"car/{info['brand']}/{info['model']}/qa/unit{info['unit']}.html"
    if kind == "model":
        return f"car/{info['brand']}/{info['model']}/index.html"
    digest = hashlib.sha1(info["url"].encode()).hexdigest()[:16]
    return f"misc/{digest}.html"


def asset_relpath(url: str) -> str:
    """Относительный путь для медиа в data/assets (host + path без query)."""
    parts = urlsplit(url)
    host = (parts.hostname or "unknown").lower()
    path = parts.path.lstrip("/") or "index"
    path = re.sub(r"[^A-Za-z0-9._/\-]", "_", path)
    if len(path) > 180:
        digest = hashlib.sha1(url.encode()).hexdigest()[:12]
        stem, dot, ext = path.rpartition(".")
        path = f"{stem[:150]}-{digest}{dot}{ext}" if dot else f"{path[:150]}-{digest}"
    return f"{host}/{path}"
