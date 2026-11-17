#!/usr/bin/env python3
"""Этап 4: сборка статического офлайн-сайта.

Результат — out/site/, открывается в браузере по file:// без сервера.
Поиск работает через search-index.js (fetch JSON на file:// запрещён).

Примеры:
    python3 scripts/04_build.py
    python3 scripts/04_build.py --lang ru --clean
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import urls  # noqa: E402
from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402

KINDS = ("note", "parts", "review", "product", "qa", "model")

CSS = """
:root { --fg:#1d1d1f; --muted:#6b7280; --bg:#fafafa; --card:#fff; --accent:#0a6cff; }
* { box-sizing: border-box; }
body { margin:0; font:16px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif;
       color:var(--fg); background:var(--bg); }
header { padding:14px 20px; background:var(--card); border-bottom:1px solid #e5e7eb;
         position:sticky; top:0; z-index:2; }
header a { color:var(--accent); text-decoration:none; }
.wrap { max-width:900px; margin:0 auto; padding:20px; }
h1 { font-size:1.5rem; margin:.2em 0 .6em; }
h2 { font-size:1.15rem; margin:1.4em 0 .4em; }
.meta { color:var(--muted); font-size:.9rem; margin-bottom:1em; }
.meta span { margin-right:1em; }
.card { background:var(--card); border:1px solid #e5e7eb; border-radius:10px;
        padding:14px 16px; margin:10px 0; }
.card a { color:var(--fg); text-decoration:none; }
.card a:hover { color:var(--accent); }
.ja { color:var(--muted); font-size:.92rem; }
.ru { margin-top:.25em; }
figure { margin:18px 0; }
figure img { max-width:100%; height:auto; border-radius:8px; display:block; }
figcaption { margin-top:.5em; }
.comment { border-top:1px solid #eee; padding:10px 0; }
.comment .who { color:var(--muted); font-size:.85rem; }
.controls { display:flex; gap:8px; flex-wrap:wrap; margin:12px 0 4px; }
.controls input, .controls select { padding:8px 10px; border:1px solid #d1d5db;
        border-radius:8px; font-size:.95rem; background:#fff; }
.controls input { flex:1 1 240px; }
.external::after { content:" ↗"; color:var(--muted); }
.badge { display:inline-block; font-size:.75rem; padding:1px 7px; border-radius:999px;
         background:#eef2ff; color:#3730a3; margin-right:.4em; }
table.ratings { border-collapse:collapse; margin:1em 0; }
table.ratings td, table.ratings th { border-bottom:1px solid #eee; padding:4px 12px 4px 0;
         text-align:left; font-weight:normal; }
footer { color:var(--muted); font-size:.85rem; padding:30px 20px; text-align:center; }
"""

INDEX_JS = """
const KIND_LABELS = __KIND_LABELS__;
const PAGE = 100;
const state = { q: "", model: "", gen: "", kind: "", limit: PAGE };
const $ = (id) => document.getElementById(id);
function render() {
  const list = window.MINKARA_INDEX || [];
  const q = state.q.trim().toLowerCase();
  const items = list.filter((it) => {
    if (state.model && it.m !== state.model) return false;
    if (state.gen && String(it.g) !== state.gen) return false;
    if (state.kind && it.k !== state.kind) return false;
    if (!q) return true;
    return (it.x || "").toLowerCase().includes(q);
  });
  const shown = items.slice(0, state.limit);
  $("count").textContent = "показано " + shown.length + " из " + items.length;
  $("more").style.display = items.length > state.limit ? "inline-block" : "none";
  $("list").innerHTML = shown.map((it) => {
    const title = it.tr || it.tj || "(без названия)";
    const sub = it.tr && it.tj ? '<div class="ja">' + escapeHtml(it.tj) + "</div>" : "";
    const meta = [it.d, it.c, it.mn, it.g ? "поколение " + it.g : ""]
      .filter(Boolean).map(escapeHtml).join(" · ");
    const badge = it.k ? '<span class="badge">' +
      escapeHtml(KIND_LABELS[it.k] || it.k) + "</span>" : "";
    return '<div class="card"><a href="' + it.u + '">' + badge +
      '<span class="ru">' + escapeHtml(title) + "</span></a>" + sub +
      '<div class="meta">' + meta + "</div></div>";
  }).join("");
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",
    '"':"&quot;","'":"&#39;" }[c]));
}
document.addEventListener("DOMContentLoaded", () => {
  const list = window.MINKARA_INDEX || [];
  const models = [...new Set(list.map((it) => it.m).filter(Boolean))].sort();
  $("model").innerHTML = '<option value="">Все модели</option>' +
    models.map((m) => '<option value="' + m + '">' + escapeHtml(m) + "</option>").join("");
  const reset = () => { state.limit = PAGE; render(); };
  $("q").addEventListener("input", (e) => { state.q = e.target.value; reset(); });
  $("model").addEventListener("change", (e) => { state.model = e.target.value; reset(); });
  $("gen").addEventListener("change", (e) => { state.gen = e.target.value; reset(); });
  $("kind").addEventListener("change", (e) => { state.kind = e.target.value; reset(); });
  $("more").addEventListener("click", () => { state.limit += PAGE; render(); });
  render();
});
"""

KIND_LABELS = {
    "note": "заметка",
    "parts": "запчасть",
    "review": "отзыв",
    "product": "товар",
    "qa": "вопрос",
    "model": "модель",
}
KIND_LABELS_JS = json.dumps(KIND_LABELS, ensure_ascii=False)


def esc(value: str | None) -> str:
    return html.escape(value or "")


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def page_relpath(page) -> str:
    kind = page["kind"]
    query = dict(parse_qsl(urlsplit(page["url"]).query))
    if kind == "note":
        return f"notes/{page['uid']}-{page['car']}-{page['note']}.html"
    if kind == "parts":
        return f"parts/{page['uid']}-{page['car']}-{page['note']}.html"
    if kind == "review":
        return f"reviews/{query.get('cid') or page['id']}.html"
    if kind == "product":
        return f"products/{query.get('pt') or page['id']}.html"
    if kind == "qa":
        match = re.search(r"/qa/unit(\d+)/", page["url"])
        unit = match.group(1) if match else str(page["id"])
        return f"qa/{page['brand']}-{page['model']}-{unit}.html"
    if kind == "model":
        return f"models/{page['brand']}-{page['model']}.html"
    return f"misc/{page['id']}.html"


def ensure_media(settings, media_url: str) -> str | None:
    if not media_url:
        return None
    absolute = urls.canonical(urls.absolute(settings.base_url, media_url))
    rel = urls.asset_relpath(absolute)
    src = settings.assets_dir / rel
    if not src.exists():
        return None
    link_or_copy(src, settings.site_dir / "media" / rel)
    return f"media/{rel}"


def layout(title: str, body: str, depth: str = "") -> str:
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{esc(title)} — Minkara archive</title>"
        f"<link rel='stylesheet' href='{depth}style.css'></head><body>"
        f"<header><a href='{depth}index.html'>← Все материалы</a></header>"
        f"<div class='wrap'>{body}</div>"
        "<footer>Личный офлайн-архив. Контент принадлежит авторам и Carview.</footer>"
        "</body></html>"
    )


def bilingual(ru_text: str | None, ja_text: str | None, lang: str) -> str:
    parts = []
    if ru_text and lang != "ja":
        parts.append(f"<div class='ru'>{esc(ru_text)}</div>")
    if ja_text and lang != "ru":
        parts.append(f"<div class='ja'>{esc(ja_text)}</div>")
    return "".join(parts)


def render_note(settings, page, meta, tr, path_map, lang) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    body = [f"<h1>{esc(title_ru or title_ja)}</h1>"]
    if title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    bits = [
        meta.get("date"),
        meta.get("car_model"),
        f"поколение {page['generation']}" if page["generation"] else "",
        meta.get("work_time"),
        meta.get("difficulty"),
        f"♥ {meta['likes']}" if meta.get("likes") is not None else "",
    ]
    body.append(
        "<div class='meta'>"
        + "".join(f"<span>{esc(str(b))}</span>" for b in bits if b)
        + "</div>"
    )
    if meta.get("categories"):
        body.append(
            "<div class='meta'>"
            + "".join(f"<span>{esc(c)}</span>" for c in meta["categories"])
            + "</div>"
        )
    body.append(
        f"<div class='meta'><a class='external' href='{esc(page['url'])}'>"
        "оригинал на minkara</a></div>"
    )

    for item in meta.get("gallery") or []:
        media = ensure_media(settings, item.get("image"))
        if not media:
            continue
        caption = bilingual(tr.get(("memo", item.get("idx"))), item.get("memo"), lang)
        body.append(
            f"<figure><img loading='lazy' src='../{esc(media)}' alt=''>"
            f"<figcaption>{caption}</figcaption></figure>"
        )

    comments = meta.get("comments") or []
    if comments:
        body.append("<h2>Комментарии</h2>")
        for i, comment in enumerate(comments, start=1):
            body.append(
                "<div class='comment'><div class='who'>"
                f"{esc(comment.get('author'))} · {esc(comment.get('date'))}</div>"
                f"{bilingual(tr.get(('comment', i)), comment.get('text'), lang)}</div>"
            )

    nav = []
    for key, label in (("prev", "← Предыдущая"), ("next", "Следующая →")):
        target = meta.get(key)
        if not target:
            continue
        absolute = urls.canonical(urls.absolute(settings.base_url, target))
        local = path_map.get(absolute)
        if local:
            nav.append(f"<a href='../{esc(local)}'>{label}</a>")
        else:
            nav.append(f"<a class='external' href='{esc(absolute)}'>{label}</a>")
    if nav:
        body.append("<div class='meta' style='margin-top:2em'>" + " · ".join(nav) + "</div>")
    return layout(title_ru or title_ja, "".join(body), "../")


def render_parts(settings, page, meta, tr, path_map, lang) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    body = [f"<h1>{esc(title_ru or title_ja)}</h1>"]
    if title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    bits = [
        meta.get("author"),
        meta.get("date"),
        f"оценка {meta['score']}" if meta.get("score") else "",
    ]
    body.append(
        "<div class='meta'>"
        + "".join(f"<span>{esc(str(b))}</span>" for b in bits if b)
        + "</div>"
    )
    if meta.get("categories"):
        body.append(
            "<div class='meta'>"
            + "".join(f"<span>{esc(c)}</span>" for c in meta["categories"])
            + "</div>"
        )
    body.append(
        f"<div class='meta'><a class='external' href='{esc(page['url'])}'>"
        "оригинал на minkara</a></div>"
    )
    media = ensure_media(settings, meta.get("image"))
    if media:
        body.append(f"<figure><img loading='lazy' src='../{esc(media)}' alt=''></figure>")
    body.append(bilingual(tr.get(("review", 1)), meta.get("text"), lang))
    return layout(title_ru or title_ja, "".join(body), "../")


def render_review(settings, page, meta, tr, path_map, lang) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    body = [f"<h1>{esc(title_ru or title_ja)}</h1>"]
    if title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    bits = [
        meta.get("author"),
        meta.get("model"),
        meta.get("grade"),
        meta.get("date"),
        f"оценка {meta['score']}" if meta.get("score") else "",
        f"поколение {page['generation']}" if page["generation"] else "",
    ]
    body.append(
        "<div class='meta'>"
        + "".join(f"<span>{esc(str(b))}</span>" for b in bits if b)
        + "</div>"
    )
    body.append(
        f"<div class='meta'><a class='external' href='{esc(page['url'])}'>"
        "оригинал на minkara</a></div>"
    )

    aspects = meta.get("aspects") or {}
    if aspects:
        body.append("<h2>Оценки</h2><table class='ratings'>")
        for name, value in aspects.items():
            body.append(f"<tr><th>{esc(name)}</th><td>{esc(value)}</td></tr>")
        body.append("</table>")

    for i, (name, value) in enumerate((meta.get("sections") or {}).items(), start=1):
        body.append(f"<h2>{esc(name)}</h2>")
        body.append(bilingual(tr.get(("review", i)), value, lang))

    for image in meta.get("images") or []:
        media = ensure_media(settings, image)
        if media:
            body.append(f"<figure><img loading='lazy' src='../{esc(media)}' alt=''></figure>")
    if meta.get("related_url"):
        body.append(
            f"<div class='meta'><a class='external' href='{esc(meta['related_url'])}'>"
            "связанная запись</a></div>"
        )
    return layout(title_ru or title_ja, "".join(body), "../")


def render_product(settings, page, meta, tr, path_map, lang) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    body = [f"<h1>{esc(title_ru or title_ja)}</h1>"]
    if title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    bits = [
        meta.get("rating"),
        meta.get("reviews_header"),
    ]
    body.append(
        "<div class='meta'>"
        + "".join(f"<span>{esc(str(b))}</span>" for b in bits if b)
        + "</div>"
    )
    body.append(
        f"<div class='meta'><a class='external' href='{esc(page['url'])}'>"
        "оригинал на minkara</a></div>"
    )
    reviews = meta.get("reviews") or []
    if reviews:
        body.append("<h2>Отзывы</h2>")
        for href in reviews:
            absolute = urls.canonical(urls.absolute(settings.base_url, href))
            local = path_map.get(absolute)
            if local:
                body.append(f"<div class='card'><a href='../{esc(local)}'>отзыв</a></div>")
            else:
                body.append(
                    f"<div class='card'><a class='external' href='{esc(absolute)}'>"
                    "отзыв на minkara</a></div>"
                )
    return layout(title_ru or title_ja, "".join(body), "../")


def render_qa(settings, page, meta, tr, path_map, lang) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    body = [f"<h1>{esc(title_ru or title_ja)}</h1>"]
    if title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    bits = [meta.get("author"), meta.get("date"), f"ответов {len(meta.get('answers') or [])}"]
    body.append(
        "<div class='meta'>"
        + "".join(f"<span>{esc(str(b))}</span>" for b in bits if b)
        + "</div>"
    )
    body.append(
        f"<div class='meta'><a class='external' href='{esc(page['url'])}'>"
        "оригинал на minkara</a></div>"
    )
    body.append("<h2>Вопрос</h2>")
    body.append(bilingual(tr.get(("qa", 1)), meta.get("question"), lang))
    answers = meta.get("answers") or []
    if answers:
        body.append("<h2>Ответы</h2>")
        for i, answer in enumerate(answers, start=2):
            body.append(
                "<div class='comment'><div class='who'>"
                f"{esc(answer.get('author'))} · {esc(answer.get('date'))}</div>"
                f"{bilingual(tr.get(('qa', i)), answer.get('text'), lang)}</div>"
            )
    for image in meta.get("images") or []:
        media = ensure_media(settings, image)
        if media:
            body.append(f"<figure><img loading='lazy' src='../{esc(media)}' alt=''></figure>")
    return layout(title_ru or title_ja, "".join(body), "../")


def render_model(settings, page, meta, tr, path_map, lang, related=None) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    body = [f"<h1>{esc(title_ru or title_ja)}</h1>"]
    if title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    body.append(bilingual(tr.get(("description", 1)), meta.get("description"), lang))
    body.append(
        f"<div class='meta'><a class='external' href='{esc(page['url'])}'>"
        "оригинал на minkara</a></div>"
    )
    links = meta.get("links") or {}
    if links:
        body.append("<h2>Разделы на minkara</h2>")
        for name, href in links.items():
            body.append(
                f"<div class='card'><a class='external' href='{esc(href)}'>{esc(name)}</a></div>"
            )
    groups: dict[str, list[dict]] = {}
    for item in related or []:
        if item["k"] == "model":
            continue
        groups.setdefault(item["k"], []).append(item)
    for kind, items in groups.items():
        body.append(f"<h2>{esc(KIND_LABELS.get(kind, kind))} ({len(items)})</h2>")
        for item in items[:100]:
            title = item["tr"] or item["tj"] or "(без названия)"
            body.append(
                f"<div class='card'><a href='../{esc(item['u'])}'>{esc(title)}</a></div>"
            )
        if len(items) > 100:
            body.append(
                f"<div class='meta'>… и ещё {len(items) - 100}; полный список — в "
                "<a href='../index.html'>общем индексе</a></div>"
            )
    return layout(title_ru or title_ja, "".join(body), "../")


RENDERERS = {
    "note": render_note,
    "parts": render_parts,
    "review": render_review,
    "product": render_product,
    "qa": render_qa,
    "model": render_model,
}


def search_text(meta: dict, tr: dict) -> str:
    chunks = [tr.get(("title", 0)) or "", meta.get("title") or ""]
    for key in ("text", "lead"):
        if meta.get(key):
            chunks.append(meta[key])
    for item in meta.get("gallery") or []:
        chunks.append(tr.get(("memo", item.get("idx"))) or "")
        chunks.append(item.get("memo") or "")
    for value in (meta.get("sections") or {}).values():
        chunks.append(value or "")
    if meta.get("question"):
        chunks.append(meta["question"])
    if meta.get("description"):
        chunks.append(meta["description"])
    for answer in meta.get("answers") or []:
        chunks.append(answer.get("text") or "")
    for i in range(1, 20):
        chunks.append(tr.get(("review", i)) or "")
        chunks.append(tr.get(("qa", i)) or "")
    for comment in meta.get("comments") or []:
        chunks.append(comment.get("text") or "")
    return " ".join(chunk for chunk in chunks if chunk)[:1000]


def render_index(entries: list[dict]) -> str:
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Minkara archive — Honda Freed</title>"
        "<link rel='stylesheet' href='style.css'></head><body>"
        "<header><strong>Minkara archive</strong> · Honda Freed</header>"
        "<div class='wrap'><h1>Материалы</h1>"
        "<div class='controls'>"
        "<input id='q' type='search' placeholder='Поиск по заголовкам и тексту (ru/ja)'>"
        "<select id='kind'><option value=''>Все типы</option>"
        "<option value='note'>Заметки</option><option value='parts'>Запчасти</option>"
        "<option value='review'>Отзывы</option><option value='product'>Товары</option>"
        "<option value='qa'>Вопросы</option><option value='model'>Модели</option></select>"
        "<select id='model'><option value=''>Все модели</option></select>"
        "<select id='gen'><option value=''>Все поколения</option>"
        "<option value='1'>1-е</option><option value='2'>2-е</option>"
        "<option value='3'>3-е</option></select>"
        "</div><div class='meta'><span id='count'></span></div>"
        "<div id='list'></div>"
        "<div style='text-align:center;margin:16px 0'>"
        "<button id='more' style='padding:8px 16px;border:1px solid #d1d5db;"
        "border-radius:8px;background:#fff;cursor:pointer'>Показать ещё</button>"
        "</div></div>"
        "<footer>Личный офлайн-архив. Контент принадлежит авторам и Carview.</footer>"
        "<script src='search-index.js'></script><script>"
        + INDEX_JS.replace("__KIND_LABELS__", KIND_LABELS_JS)
        + "</script>"
        "</body></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка офлайн-сайта")
    parser.add_argument("--lang", choices=["both", "ru", "ja"], default="both")
    parser.add_argument("--clean", action="store_true", help="удалить out/site перед сборкой")
    args = parser.parse_args()

    settings = load_settings()
    store = Store(settings.db_path)
    store.init()

    if args.clean and settings.site_dir.exists():
        shutil.rmtree(settings.site_dir)
    settings.site_dir.mkdir(parents=True, exist_ok=True)
    (settings.site_dir / "style.css").write_text(CSS, encoding="utf-8")

    pages = []
    for kind in KINDS:
        pages.extend(store.parsed_pages(kind))
    path_map = {page["url"]: page_relpath(page) for page in pages}

    # Первый проход: метаданные и индексные записи (нужны страницам моделей).
    records: list[tuple] = []
    entries: list[dict] = []
    for page in pages:
        meta = json.loads(page["meta_json"])
        tr = store.units_for_page(page["id"])
        records.append((page, meta, tr))
        entries.append(
            {
                "u": page_relpath(page),
                "k": page["kind"],
                "tr": tr.get(("title", 0)) or "",
                "tj": meta.get("title") or "",
                "d": meta.get("date") or "",
                "c": " / ".join(meta.get("categories") or []),
                "m": page["model"] or "",
                "mn": meta.get("car_model") or meta.get("model") or "",
                "g": page["generation"],
                "x": search_text(meta, tr),
            }
        )

    by_model: dict[str, list[dict]] = {}
    for entry in entries:
        by_model.setdefault(entry["m"], []).append(entry)

    built = 0
    for page, meta, tr in records:
        renderer = RENDERERS.get(page["kind"])
        if renderer is None:
            continue
        if page["kind"] == "model":
            html_text = renderer(
                settings,
                page,
                meta,
                tr,
                path_map,
                args.lang,
                related=by_model.get(page["model"] or "", []),
            )
        else:
            html_text = renderer(settings, page, meta, tr, path_map, args.lang)
        target = settings.site_dir / page_relpath(page)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html_text, encoding="utf-8")
        built += 1

    (settings.site_dir / "search-index.js").write_text(
        "window.MINKARA_INDEX = " + json.dumps(entries, ensure_ascii=False) + ";",
        encoding="utf-8",
    )
    (settings.site_dir / "index.html").write_text(render_index(entries), encoding="utf-8")

    print(f"Собрано страниц: {built}")
    print(f"Сайт: {settings.site_dir}/index.html")
    if not built:
        print("Пока нечего собирать: сначала выполните 01_discover и 02_fetch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
