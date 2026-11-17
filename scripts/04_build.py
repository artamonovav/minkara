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
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import urls  # noqa: E402
from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402

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
figcaption .ja { margin-top:.25em; }
.comment { border-top:1px solid #eee; padding:10px 0; }
.comment .who { color:var(--muted); font-size:.85rem; }
.controls { display:flex; gap:8px; flex-wrap:wrap; margin:12px 0 4px; }
.controls input, .controls select { padding:8px 10px; border:1px solid #d1d5db;
        border-radius:8px; font-size:.95rem; background:#fff; }
.controls input { flex:1 1 240px; }
.external::after { content:" ↗"; color:var(--muted); }
footer { color:var(--muted); font-size:.85rem; padding:30px 20px; text-align:center; }
"""

INDEX_JS = """
const state = { q: "", model: "", gen: "" };
const $ = (id) => document.getElementById(id);
function render() {
  const list = window.MINKARA_INDEX || [];
  const q = state.q.trim().toLowerCase();
  const items = list.filter((it) => {
    if (state.model && it.m !== state.model) return false;
    if (state.gen && String(it.g) !== state.gen) return false;
    if (!q) return true;
    return (it.x || "").toLowerCase().includes(q);
  });
  $("count").textContent = items.length + " из " + list.length;
  $("list").innerHTML = items.map((it) => {
    const title = it.tr || it.tj || "(без названия)";
    const sub = it.tr && it.tj ? '<div class="ja">' + escapeHtml(it.tj) + "</div>" : "";
    const meta = [it.d, it.c, it.mn, it.g ? "поколение " + it.g : ""]
      .filter(Boolean).map(escapeHtml).join(" · ");
    return '<div class="card"><a href="' + it.u + '"><div class="ru">' +
      escapeHtml(title) + "</div></a>" + sub +
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
  $("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });
  $("model").addEventListener("change", (e) => { state.model = e.target.value; render(); });
  $("gen").addEventListener("change", (e) => { state.gen = e.target.value; render(); });
  render();
});
"""


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


def note_relpath(page) -> str:
    return f"notes/{page['uid']}-{page['car']}-{page['note']}.html"


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


def render_note(settings, page, meta: dict, translations: dict, path_map: dict, lang: str) -> str:
    def ru(kind: str, idx: int) -> str | None:
        return translations.get((kind, idx))
    title_ja = meta.get("title") or ""
    title_ru = ru("title", 0)
    title = title_ru or title_ja
    model_name = meta.get("car_model") or page["model"] or ""

    parts = [
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>{esc(title)} — Minkara archive</title>",
        "<link rel='stylesheet' href='../style.css'></head><body>",
        "<header><a href='../index.html'>← Все заметки</a></header><div class='wrap'>",
        f"<h1>{esc(title)}</h1>",
    ]
    if title_ru and title_ja:
        parts.append(f"<div class='ja'>{esc(title_ja)}</div>")
    meta_bits = [
        meta.get("date"),
        model_name,
        f"поколение {page['generation']}" if page["generation"] else "",
        meta.get("work_time"),
        meta.get("difficulty"),
        f"♥ {meta['likes']}" if meta.get("likes") is not None else "",
    ]
    parts.append(
        "<div class='meta'>"
        + "".join(f"<span>{esc(str(bit))}</span>" for bit in meta_bits if bit)
        + "</div>"
    )
    if meta.get("categories"):
        parts.append(
            "<div class='meta'>"
            + "".join(f"<span>{esc(c)}</span>" for c in meta["categories"])
            + "</div>"
        )
    parts.append(
        f"<div class='meta'><a class='external' href='{esc(page['url'])}'>"
        "оригинал на minkara</a></div>"
    )

    for item in meta.get("gallery") or []:
        media = ensure_media(settings, item.get("image"))
        if not media:
            continue
        memo_ru = ru("memo", item.get("idx"))
        memo_ja = item.get("memo") or ""
        caption = []
        if memo_ru and lang != "ja":
            caption.append(f"<div class='ru'>{esc(memo_ru)}</div>")
        if memo_ja and lang != "ru":
            caption.append(f"<div class='ja'>{esc(memo_ja)}</div>")
        parts.append(
            f"<figure><img loading='lazy' src='../{esc(media)}' alt=''>"
            f"<figcaption>{''.join(caption)}</figcaption></figure>"
        )

    comments = meta.get("comments") or []
    if comments:
        parts.append("<h2>Комментарии</h2>")
        for i, comment in enumerate(comments, start=1):
            text_ru = ru("comment", i)
            text_ja = comment.get("text") or ""
            body = []
            if text_ru and lang != "ja":
                body.append(f"<div class='ru'>{esc(text_ru)}</div>")
            if text_ja and lang != "ru":
                body.append(f"<div class='ja'>{esc(text_ja)}</div>")
            parts.append(
                "<div class='comment'><div class='who'>"
                f"{esc(comment.get('author'))} · {esc(comment.get('date'))}</div>"
                f"{''.join(body)}</div>"
            )

    nav = []
    for key, label in (("prev", "← Предыдущая"), ("next", "Следующая →")):
        target = meta.get(key)
        if not target:
            continue
        absolute = urls.canonical(urls.absolute(settings.base_url, target))
        local = path_map.get(absolute)
        if local:
            nav.append(f"<a href='{esc(local)}'>{label}</a>")
        else:
            nav.append(f"<a class='external' href='{esc(absolute)}'>{label}</a>")
    if nav:
        parts.append("<div class='meta' style='margin-top:2em'>" + " · ".join(nav) + "</div>")

    parts.append("</div><footer>Личный офлайн-архив. Контент принадлежит авторам и Carview.</footer></body></html>")
    return "".join(parts)


def render_index(entries: list[dict]) -> str:
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Minkara archive — Honda Freed</title>"
        "<link rel='stylesheet' href='style.css'></head><body>"
        "<header><strong>Minkara archive</strong> · Honda Freed</header>"
        "<div class='wrap'><h1>Заметки</h1>"
        "<div class='controls'>"
        "<input id='q' type='search' placeholder='Поиск по заголовкам и тексту (ru/ja)'>"
        "<select id='model'><option value=''>Все модели</option></select>"
        "<select id='gen'><option value=''>Все поколения</option>"
        "<option value='2'>2-е</option><option value='3'>3-е</option></select>"
        "</div><div class='meta'><span id='count'></span></div>"
        "<div id='list'></div></div>"
        "<footer>Личный офлайн-архив. Контент принадлежит авторам и Carview.</footer>"
        "<script src='search-index.js'></script><script>" + INDEX_JS + "</script>"
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

    pages = store.parsed_pages("note")
    path_map = {page["url"]: note_relpath(page) for page in pages}
    entries: list[dict] = []
    built = 0

    for page in pages:
        meta = json.loads(page["meta_json"])
        translations = store.units_for_page(page["id"])
        html_text = render_note(settings, page, meta, translations, path_map, args.lang)
        target = settings.site_dir / note_relpath(page)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html_text, encoding="utf-8")

        title_ru = translations.get(("title", 0))
        title_ja = meta.get("title") or ""
        snippet_parts = []
        if title_ru:
            snippet_parts.append(title_ru)
        snippet_parts.append(title_ja)
        for item in meta.get("gallery") or []:
            memo_ru = translations.get(("memo", item.get("idx")))
            if memo_ru:
                snippet_parts.append(memo_ru)
            if item.get("memo"):
                snippet_parts.append(item["memo"])
        entries.append(
            {
                "u": note_relpath(page),
                "tr": title_ru or "",
                "tj": title_ja,
                "d": meta.get("date") or "",
                "c": " / ".join(meta.get("categories") or []),
                "m": page["model"] or "",
                "mn": meta.get("car_model") or "",
                "g": page["generation"],
                "x": " ".join(snippet_parts)[:800],
            }
        )
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
