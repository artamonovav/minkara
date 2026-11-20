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

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from minkara import urls  # noqa: E402
from minkara.config import load_settings  # noqa: E402
from minkara.db import Store  # noqa: E402

KINDS = ("note", "parts", "review", "product", "model")

CSS = """
:root { --fg:#1d1d1f; --muted:#6b7280; --bg:#fafafa; --card:#fff; --accent:#0a6cff; }
* { box-sizing: border-box; }
body { margin:0; font:16px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif;
       color:var(--fg); background:var(--bg); }
header { padding:14px 20px; background:var(--card); border-bottom:1px solid #e5e7eb;
         position:sticky; top:0; z-index:2; }
header a { color:var(--accent); text-decoration:none; }
.wrap { width:100%; max-width:none; margin:0; padding:20px clamp(16px, 3vw, 48px); }
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
.multiselect { position:relative; }
.multiselect > button { padding:8px 10px; border:1px solid #d1d5db; border-radius:8px;
                        background:#fff; font-size:.95rem; cursor:pointer;
                        min-width:170px; text-align:left; }
.multiselect-menu { position:absolute; top:calc(100% + 4px); left:0; z-index:30;
                    background:#fff; border:1px solid #d1d5db; border-radius:8px;
                    box-shadow:0 8px 24px rgba(0,0,0,.12); padding:8px;
                    min-width:240px; max-height:320px; overflow:auto; }
.multiselect-menu label { display:flex; gap:8px; align-items:center; padding:4px 6px;
                          border-radius:6px; cursor:pointer; font-size:.9rem;
                          white-space:nowrap; }
.multiselect-menu label:hover { background:#f1f5f9; }
.multiselect-menu .ms-all { border-bottom:1px solid #e5e7eb; margin-bottom:4px;
                            padding-bottom:6px; font-weight:600; }
.external::after { content:" ↗"; color:var(--muted); }
.badge { display:inline-block; font-size:.75rem; padding:1px 7px; border-radius:999px;
         background:#eef2ff; color:#3730a3; margin-right:.4em; }
.table-wrap { overflow-x:auto; background:var(--card); border:1px solid #e5e7eb;
              border-radius:10px; }
table.index-table { width:100%; border-collapse:collapse; font-size:.9rem; }
.index-table th { position:sticky; top:0; background:#f8fafc; text-align:left;
                  padding:8px 10px; border-bottom:1px solid #e5e7eb;
                  font-weight:600; white-space:nowrap; }
.index-table td { padding:6px 10px; border-bottom:1px solid #f1f5f9; vertical-align:top; }
.index-table tbody tr:hover { background:#f8fafc; }
.index-table .title { font-weight:500; }
.index-table .muted { color:var(--muted); white-space:nowrap; }
.index-table .badge { margin-right:0; }
@media (max-width:700px) { .index-table .hide-sm { display:none; } }
.pager { display:flex; flex-wrap:wrap; gap:4px; align-items:center;
         justify-content:center; margin:16px 0; }
.pager button { min-width:32px; padding:5px 8px; border:1px solid #d1d5db;
                background:#fff; border-radius:7px; cursor:pointer; font-size:.9rem; }
.pager button.active { background:#0a6cff; color:#fff; border-color:#0a6cff; }
.pager button:disabled { opacity:.45; cursor:default; }
.pager .gap { color:var(--muted); padding:0 2px; }
.drawer { position:fixed; top:0; right:0; height:100%; width:66vw; min-width:320px;
          max-width:100vw; background:#fff; border-left:1px solid #e5e7eb; z-index:50;
          box-shadow:-8px 0 24px rgba(0,0,0,.12); display:flex; flex-direction:column;
          transform:translateX(100%); transition:transform .2s ease; }
.drawer-resizer { position:absolute; left:0; top:0; bottom:0; width:8px;
                  cursor:col-resize; z-index:60; }
.drawer-resizer::after { content:""; position:absolute; left:3px; top:50%;
                  width:2px; height:42px; background:#cbd5e1; border-radius:2px;
                  transform:translateY(-50%); }
.drawer.open { transform:translateX(0); }
.drawer-head { display:flex; align-items:center; justify-content:space-between;
               padding:10px 14px; border-bottom:1px solid #e5e7eb; }
.drawer-head span { display:flex; align-items:center; gap:8px; }
.drawer-head button { border:0; background:none; font-size:1.5rem; line-height:1;
                      cursor:pointer; padding:0 6px; }
.drawer-head #drawer-pdf { font-size:.8rem; border:1px solid #d1d5db; border-radius:6px;
                           padding:3px 8px; }
.drawer iframe { flex:1; width:100%; border:0; }
.drawer-backdrop { position:fixed; inset:0; background:rgba(0,0,0,.25); z-index:40;
                   opacity:0; pointer-events:none; transition:opacity .2s ease; }
.drawer-backdrop.open { opacity:1; pointer-events:auto; }
table.ratings { border-collapse:collapse; margin:1em 0; }
table.ratings td, table.ratings th { border-bottom:1px solid #eee; padding:4px 12px 4px 0;
         text-align:left; font-weight:normal; }
footer { color:var(--muted); font-size:.85rem; padding:30px 20px; text-align:center; }
@media print {
  header, footer, #nav-switch, .drawer, .drawer-backdrop { display:none !important; }
  .wrap { padding:0; }
  a { color:#000; text-decoration:none; }
}
"""

INDEX_JS = """
const KIND_LABELS = __KIND_LABELS__;
const SHOW_JA = __SHOW_JA__;
const PAGE = 10;
const state = { q: "", models: new Set(), gen: "", kind: "", page: 1 };
const modelLabels = {};
const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",
    '"':"&quot;","'":"&#39;" }[c]));
}

function pageNumbers(current, total) {
  const set = new Set([1, total, current - 1, current, current + 1]);
  const nums = [...set].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b);
  const out = [];
  let prev = 0;
  for (const n of nums) {
    if (prev && n - prev > 1) out.push(null);
    out.push(n);
    prev = n;
  }
  return out;
}

function renderPager(totalPages) {
  const parts = [];
  parts.push('<button data-page="prev" ' + (state.page <= 1 ? "disabled" : "") +
    '>← Назад</button>');
  for (const n of pageNumbers(state.page, totalPages)) {
    if (n === null) {
      parts.push('<span class="gap">…</span>');
    } else {
      parts.push('<button data-page="' + n + '"' +
        (n === state.page ? ' class="active"' : "") + '>' + n + "</button>");
    }
  }
  parts.push('<button data-page="next" ' + (state.page >= totalPages ? "disabled" : "") +
    '>Вперёд →</button>');
  $("pager").innerHTML = parts.join("");
}

function openDrawer(href) {
  $("drawer-frame").src = href;
  $("drawer").classList.add("open");
  $("drawer").setAttribute("aria-hidden", "false");
  $("drawer-backdrop").classList.add("open");
  $("drawer-close").focus();
}

function closeDrawer() {
  $("drawer").classList.remove("open");
  $("drawer").setAttribute("aria-hidden", "true");
  $("drawer-backdrop").classList.remove("open");
  setTimeout(() => {
    if (!$("drawer").classList.contains("open")) {
      $("drawer-frame").src = "about:blank";
    }
  }, 250);
}

function filteredItems() {
  const list = window.MINKARA_INDEX || [];
  const q = state.q.trim().toLowerCase();
  return list.filter((it) => {
    if (state.models.size && !state.models.has(it.m)) return false;
    if (state.gen && String(it.g) !== state.gen) return false;
    if (state.kind && it.k !== state.kind) return false;
    if (!q) return true;
    return (it.x || "").toLowerCase().includes(q);
  });
}

function render() {
  const items = filteredItems();
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE));
  if (state.page > totalPages) state.page = totalPages;
  const start = (state.page - 1) * PAGE;
  const shown = items.slice(start, start + PAGE);
  $("count").textContent = total
    ? "показано " + (start + 1) + "–" + Math.min(start + PAGE, total) + " из " + total
    : "ничего не найдено";
  renderPager(totalPages);

  if (!shown.length) {
    $("list").innerHTML = '<div class="meta" style="padding:12px">Ничего не найдено</div>';
    return;
  }
  const suffix = state.gen ? '#nav=gen' : (state.models.size === 1 ? '#nav=model' : '');
  const rows = shown.map((it) => {
    const title = it.tr || it.tj || "(без названия)";
    const href = it.u + suffix;
    const badge = it.k ? '<span class="badge">' +
      escapeHtml(KIND_LABELS[it.k] || it.k) + "</span>" : "";
    return '<tr data-href="' + href + '">' +
      "<td>" + badge + "</td>" +
      '<td class="title"><a target="_blank" rel="noopener" href="' + href + '">' +
      escapeHtml(title) + "</a></td>" +
      '<td class="muted hide-sm">' + escapeHtml(it.mn || it.m || "") + "</td>" +
      '<td class="muted hide-sm">' + (it.g ? String(it.g) : "") + "</td>" +
      '<td class="muted hide-sm">' + escapeHtml(it.d || "") + "</td>" +
      "</tr>";
  }).join("");
  $("list").innerHTML =
    '<div class="table-wrap"><table class="index-table"><thead><tr>' +
    "<th>Тип</th><th>Заголовок</th><th class='hide-sm'>Модель</th>" +
    "<th class='hide-sm'>Пок.</th><th class='hide-sm'>Дата</th>" +
    "</tr></thead><tbody>" + rows + "</tbody></table></div>";
  $("list").querySelectorAll("tr[data-href]").forEach((row) => {
    row.addEventListener("click", (event) => {
      if (event.target.closest("a")) return;
      openDrawer(row.getAttribute("data-href"));
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const list = window.MINKARA_INDEX || [];
  for (const item of list) {
    if (item.m && !modelLabels[item.m]) modelLabels[item.m] = item.mn || item.m;
  }
  const modelKeys = Object.keys(modelLabels).sort((a, b) =>
    modelLabels[a].localeCompare(modelLabels[b], "ru")
  );
  $("model-menu").innerHTML =
    '<label class="ms-all"><input type="checkbox" id="model-all" checked> Все модели</label>' +
    modelKeys.map((key) =>
      '<label><input type="checkbox" value="' + escapeHtml(key) + '"> ' +
      escapeHtml(modelLabels[key]) + "</label>"
    ).join("");

  const reset = () => { state.page = 1; render(); };
  const updateModelLabel = () => {
    const toggle = $("model-toggle");
    if (!state.models.size) {
      toggle.textContent = "Все модели";
    } else if (state.models.size === 1) {
      const key = [...state.models][0];
      toggle.textContent = modelLabels[key] || key;
    } else {
      toggle.textContent = "Модели: " + state.models.size;
    }
  };
  const menu = $("model-menu");
  $("model-toggle").addEventListener("click", (event) => {
    event.stopPropagation();
    menu.hidden = !menu.hidden;
  });
  menu.addEventListener("click", (event) => event.stopPropagation());
  menu.addEventListener("change", (event) => {
    const checkbox = event.target;
    if (!(checkbox instanceof HTMLInputElement) || checkbox.type !== "checkbox") return;
    if (checkbox.id === "model-all") {
      state.models.clear();
      menu.querySelectorAll("input[type=checkbox]:not(#model-all)").forEach((item) => {
        item.checked = false;
      });
    } else {
      if (checkbox.checked) state.models.add(checkbox.value);
      else state.models.delete(checkbox.value);
      const all = menu.querySelector("#model-all");
      if (all) all.checked = state.models.size === 0;
    }
    updateModelLabel();
    reset();
  });
  document.addEventListener("click", (event) => {
    if (!$("model-box").contains(event.target)) menu.hidden = true;
  });

  $("q").addEventListener("input", (e) => { state.q = e.target.value; reset(); });
  $("gen").addEventListener("change", (e) => { state.gen = e.target.value; reset(); });
  $("kind").addEventListener("change", (e) => { state.kind = e.target.value; reset(); });
  $("pager").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-page]");
    if (!button || button.disabled) return;
    const value = button.getAttribute("data-page");
    if (value === "prev") state.page -= 1;
    else if (value === "next") state.page += 1;
    else state.page = Number(value);
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  $("drawer-close").addEventListener("click", closeDrawer);
  $("drawer-backdrop").addEventListener("click", closeDrawer);
  $("drawer-pdf").addEventListener("click", () => {
    const frame = $("drawer-frame");
    try {
      frame.contentWindow.focus();
      frame.contentWindow.print();
    } catch (error) {
      window.open(frame.src, "_blank", "noopener");
    }
  });

  const drawer = $("drawer");
  const resizer = $("drawer-resizer");
  const savedWidth = Number(localStorage.getItem("minkara-drawer-width") || 0);
  if (savedWidth) drawer.style.width = Math.min(savedWidth, window.innerWidth) + "px";
  let dragging = false;
  resizer.addEventListener("pointerdown", (event) => {
    dragging = true;
    resizer.setPointerCapture(event.pointerId);
    document.body.style.userSelect = "none";
    event.preventDefault();
  });
  resizer.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const width = Math.max(320, Math.min(window.innerWidth, window.innerWidth - event.clientX));
    drawer.style.width = width + "px";
  });
  const stopDrag = () => {
    if (!dragging) return;
    dragging = false;
    document.body.style.userSelect = "";
    localStorage.setItem(
      "minkara-drawer-width",
      String(Math.round(drawer.getBoundingClientRect().width))
    );
  };
  resizer.addEventListener("pointerup", stopDrag);
  resizer.addEventListener("pointercancel", stopDrag);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDrawer();
      $("model-menu").hidden = true;
    }
    if (!event.ctrlKey || event.altKey || event.metaKey) return;
    const tag = (event.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (event.key === "ArrowLeft" && state.page > 1) {
      event.preventDefault();
      state.page -= 1;
      render();
    }
    if (event.key === "ArrowRight") {
      const totalPages = Math.max(1, Math.ceil(filteredItems().length / PAGE));
      if (state.page < totalPages) {
        event.preventDefault();
        state.page += 1;
        render();
      }
    }
  });

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

CATEGORY_MAP: dict[str, str] = {}
MODEL_MAP: dict[str, str] = {}
DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def ru_date(value: str | None) -> str:
    text = value or ""
    match = DATE_RE.search(text)
    if not match:
        return text
    return f"{int(match.group(3)):02d}.{int(match.group(2)):02d}.{match.group(1)}"


def ru_category(value: str) -> str:
    return CATEGORY_MAP.get(value, value)


def ru_model(value: str | None) -> str:
    return MODEL_MAP.get(value or "", value or "")


def load_taxonomy(settings) -> None:
    path = settings.root / "config" / "taxonomy.ru.yaml"
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    CATEGORY_MAP.update(data.get("categories") or {})
    MODEL_MAP.update(data.get("models") or {})
KIND_LABELS_JS = json.dumps(KIND_LABELS, ensure_ascii=False)


def esc(value: str | None) -> str:
    return html.escape(value or "")


BLOCK_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)


def minify_html(text: str) -> str:
    """Убирает комментарии и пробелы между тегами, не трогая script/style."""
    blocks: list[str] = []

    def stash(match: re.Match) -> str:
        blocks.append(match.group(0))
        return f"@@MINKARA_BLOCK_{len(blocks) - 1}@@"

    text = BLOCK_RE.sub(stash, text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r">\s+<", "><", text)
    for index, block in enumerate(blocks):
        text = text.replace(f"@@MINKARA_BLOCK_{index}@@", block)
    return text


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
        webp_rel = str(Path(rel).with_suffix(".webp"))
        webp_src = settings.assets_dir / webp_rel
        if webp_src.exists():
            rel, src = webp_rel, webp_src
        else:
            return None
    link_or_copy(src, settings.site_dir / "media" / rel)
    return f"media/{rel}"


def layout(title: str, body: str, depth: str = "") -> str:
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{esc(title)} — Minkara archive</title>"
        f"<link rel='stylesheet' href='{depth}style.css'></head><body>"
        f"<header><a href='{depth}index.html'>← Все материалы</a> · "
        f"<a href='{depth}open.html'>открыть по адресу</a></header>"
        f"<div class='wrap'>{body}</div>"
        "<footer>Личный офлайн-архив. Контент принадлежит авторам и Carview.</footer>"
        "<script>"
        "document.addEventListener('keydown', function (e) {"
        "  if (!e.ctrlKey || e.altKey || e.metaKey) return;"
        "  var tag = (e.target.tagName || '').toLowerCase();"
        "  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;"
        "  var link = null;"
        "  if (e.key === 'ArrowLeft') link = document.getElementById('nav-prev');"
        "  if (e.key === 'ArrowRight') link = document.getElementById('nav-next');"
        "  if (link) { e.preventDefault(); window.location.href = link.getAttribute('href'); }"
        "});"
        "</script>"
        "</body></html>"
    )


def note_order(records: list[tuple], base_url: str) -> list[str]:
    """Единый линейный порядок заметок без циклов.

    Внутри каждой машины сохраняем исходную цепочку prev/next, затем
    склеиваем машины в стабильном порядке. Если в исходных данных есть
    цикл или обрыв, оставшиеся записи добавляются по id — циклов не будет.
    """
    groups: dict[tuple, list] = {}
    for page, meta, _tr in records:
        if page["kind"] != "note":
            continue
        car = page["car"] if page["car"] is not None else -int(page["id"])
        groups.setdefault((page["model"] or "", car), []).append((page, meta))

    ordered: list[str] = []
    for key in sorted(groups, key=lambda item: (item[0], item[1])):
        items = groups[key]
        url_set = {page["url"] for page, _ in items}
        id_by_url = {page["url"]: int(page["id"]) for page, _ in items}
        next_map: dict[str, str] = {}
        prev_map: dict[str, str] = {}
        for page, meta in items:
            url = page["url"]
            target = meta.get("next")
            if target:
                absolute = urls.canonical(urls.absolute(base_url, target))
                if absolute in url_set and absolute != url:
                    next_map[url] = absolute
            target = meta.get("prev")
            if target:
                absolute = urls.canonical(urls.absolute(base_url, target))
                if absolute in url_set and absolute != url:
                    prev_map[url] = absolute

        starts = sorted(
            (url for url in url_set if url not in prev_map),
            key=lambda url: id_by_url[url],
        )
        if not starts:
            starts = [min(url_set, key=lambda url: id_by_url[url])]

        visited: set[str] = set()
        for start in starts:
            current = start
            while current and current not in visited:
                visited.add(current)
                ordered.append(current)
                current = next_map.get(current)

        leftovers = sorted(
            (url for url in url_set if url not in visited),
            key=lambda url: id_by_url[url],
        )
        ordered.extend(leftovers)
    return ordered


def nav_from_order(ordered: list[str]) -> dict:
    nav: dict[str, dict] = {}
    for index, rel in enumerate(ordered):
        nav[rel] = {
            "prev": ordered[index - 1] if index > 0 else None,
            "next": ordered[index + 1] if index + 1 < len(ordered) else None,
        }
    return nav


NAV_SCRIPT = """<script>
window.MINKARA_NAV = __NAV__;
(function () {
  function apply() {
    var match = location.hash.match(/^#nav=(all|model|gen)/);
    var key = match ? match[1] : 'all';
    var nav = window.MINKARA_NAV[key] || window.MINKARA_NAV.all || {};
    var prev = document.getElementById('nav-prev');
    var next = document.getElementById('nav-next');
    if (prev) {
      if (nav.prev) { prev.style.display = 'inline'; prev.setAttribute('href', '../' + nav.prev); }
      else { prev.style.display = 'none'; }
    }
    if (next) {
      if (nav.next) { next.style.display = 'inline'; next.setAttribute('href', '../' + nav.next); }
      else { next.style.display = 'none'; }
    }
    document.querySelectorAll('#nav-switch a').forEach(function (a) {
      a.style.fontWeight = a.getAttribute('href') === '#nav=' + key ? 'bold' : 'normal';
    });
  }
  window.addEventListener('hashchange', apply);
  apply();
})();
</script>"""


def inject_nav(html_text: str, variants: dict) -> str:
    switch = (
        "<div class='meta' id='nav-switch'>Навигация: "
        "<a href='#nav=all'>все</a> · "
        "<a href='#nav=model'>модель</a> · "
        "<a href='#nav=gen'>поколение</a></div>"
    )
    script = NAV_SCRIPT.replace("__NAV__", json.dumps(variants, ensure_ascii=False))
    return html_text.replace("</body>", switch + script + "</body>")


def owner_block(page) -> str:
    uid = page["uid"]
    if not uid:
        return ""
    links = []
    if page["car"]:
        links.append(
            f"<a href='../cars/{uid}-{page['car']}.html'>Все материалы этой машины</a>"
        )
    links.append(f"<a href='../authors/{uid}.html'>Все материалы автора</a>")
    return "<div class='meta'>" + " · ".join(links) + "</div>"


def render_hub(title: str, items: list[dict]) -> str:
    body = [f"<h1>{esc(title)}</h1>"]
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(item["k"], []).append(item)
    for kind in ("note", "review", "qa", "parts", "product"):
        group = groups.get(kind)
        if not group:
            continue
        body.append(f"<h2>{esc(KIND_LABELS.get(kind, kind))} ({len(group)})</h2>")
        for item in group:
            name = item["tr"] or item["tj"] or "(без названия)"
            meta = " · ".join(bit for bit in (item["d"], item["c"]) if bit)
            body.append(
                f"<div class='card'><a href='../{esc(item['u'])}'>{esc(name)}</a>"
                + (f"<div class='meta'>{esc(meta)}</div>" if meta else "")
                + "</div>"
            )
    body.append("<div class='meta'><a href='../index.html'>← Общий индекс</a></div>")
    return layout(title, "".join(body), "../")


def nav_links(nav: dict | None) -> str:
    if not nav:
        return ""
    links = []
    if nav.get("prev"):
        links.append(
            f"<a id='nav-prev' title='Ctrl+←' href='../{esc(nav['prev'])}'>← Предыдущая</a>"
        )
    if nav.get("next"):
        links.append(
            f"<a id='nav-next' title='Ctrl+→' href='../{esc(nav['next'])}'>Следующая →</a>"
        )
    if not links:
        return ""
    return "<div class='meta' style='margin-top:2em'>" + " · ".join(links) + "</div>"


def bilingual(ru_text: str | None, ja_text: str | None, lang: str) -> str:
    parts = []
    if ru_text and lang != "ja":
        parts.append(f"<div class='ru'>{esc(ru_text)}</div>")
    if ja_text and lang != "ru":
        parts.append(f"<div class='ja'>{esc(ja_text)}</div>")
    return "".join(parts)


def render_note(settings, page, meta, tr, path_map, lang, nav=None) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    title = title_ja if lang == "ja" and title_ja else (title_ru or title_ja)
    body = [f"<h1>{esc(title)}</h1>"]
    if lang == "both" and title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    bits = [
        ru_date(meta.get("date")),
        ru_model(meta.get("car_model")),
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
            + "".join(f"<span>{esc(ru_category(c))}</span>" for c in meta["categories"])
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

    body.append(nav_links(nav))
    return layout(title, "".join(body), "../")


def render_parts(settings, page, meta, tr, path_map, lang, nav=None) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    title = title_ja if lang == "ja" and title_ja else (title_ru or title_ja)
    body = [f"<h1>{esc(title)}</h1>"]
    if lang == "both" and title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    bits = [
        meta.get("author"),
        ru_date(meta.get("date")),
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
            + "".join(f"<span>{esc(ru_category(c))}</span>" for c in meta["categories"])
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
    body.append(nav_links(nav))
    return layout(title, "".join(body), "../")


def render_review(settings, page, meta, tr, path_map, lang, nav=None) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    title = title_ja if lang == "ja" and title_ja else (title_ru or title_ja)
    body = [f"<h1>{esc(title)}</h1>"]
    if lang == "both" and title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    bits = [
        meta.get("author"),
        ru_model(meta.get("model")),
        meta.get("grade"),
        ru_date(meta.get("date")),
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
    body.append(nav_links(nav))
    return layout(title, "".join(body), "../")


def render_product(settings, page, meta, tr, path_map, lang, nav=None) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    title = title_ja if lang == "ja" and title_ja else (title_ru or title_ja)
    body = [f"<h1>{esc(title)}</h1>"]
    if lang == "both" and title_ru and title_ja:
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
    body.append(nav_links(nav))
    return layout(title, "".join(body), "../")


def render_qa(settings, page, meta, tr, path_map, lang, nav=None) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    title = title_ja if lang == "ja" and title_ja else (title_ru or title_ja)
    body = [f"<h1>{esc(title)}</h1>"]
    if lang == "both" and title_ru and title_ja:
        body.append(f"<div class='ja'>{esc(title_ja)}</div>")
    bits = [
        meta.get("author"),
        ru_date(meta.get("date")),
        f"ответов {len(meta.get('answers') or [])}",
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
    body.append(nav_links(nav))
    return layout(title, "".join(body), "../")


def render_model(settings, page, meta, tr, path_map, lang, related=None, nav=None) -> str:
    title_ru = tr.get(("title", 0))
    title_ja = meta.get("title") or ""
    title = title_ja if lang == "ja" and title_ja else (title_ru or title_ja)
    body = [f"<h1>{esc(title)}</h1>"]
    if lang == "both" and title_ru and title_ja:
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
    body.append(nav_links(nav))
    return layout(title, "".join(body), "../")


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


OPEN_JS = """
const KEEP = new Set(['pn','bi','sci','ci','mk','br','id','cid','pt']);
function normalize(input) {
  let raw = (input || '').trim();
  if (!raw) return null;
  if (!/^https?:\\/\\//i.test(raw)) raw = 'https://' + raw;
  let url;
  try { url = new URL(raw); } catch (e) { return null; }
  let host = url.hostname.toLowerCase();
  if (host.endsWith('.translate.goog')) {
    host = host.slice(0, -'.translate.goog'.length).replace(/-/g, '.');
  }
  if (host === 'www.minkara.carview.co.jp') host = 'minkara.carview.co.jp';
  const params = [];
  for (const [key, value] of url.searchParams.entries()) {
    if (!KEEP.has(key)) continue;
    if (key === 'pn' && value === '1') continue;
    params.push([key, value]);
  }
  params.sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
  const query = params.map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
  return 'https://' + host + url.pathname + (query ? '?' + query : '');
}
function run(value) {
  const normalized = normalize(value);
  const box = document.getElementById('result');
  if (!normalized) { box.innerHTML = 'Не удалось разобрать адрес.'; return; }
  const local = (window.MINKARA_URLS || {})[normalized];
  if (local) {
    box.innerHTML = 'Открываю локальную копию…';
    window.location.replace(local);
    return;
  }
  box.innerHTML = 'В архиве нет этой страницы.<br>Нормализованный адрес: <code>' +
    normalized.replace(/&/g, '&amp;').replace(/</g, '&lt;') +
    '</code><br><a href="' + normalized + '">Открыть оригинал на minkara</a>';
}
document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(location.search);
  const hash = location.hash.startsWith('#url=') ? decodeURIComponent(location.hash.slice(5)) : '';
  const value = params.get('url') || hash;
  if (value) run(value);
  document.getElementById('go').addEventListener('click', () => {
    run(document.getElementById('url').value);
  });
  document.getElementById('url').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') run(e.target.value);
  });
});
"""


def render_open_page() -> str:
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Открыть по адресу minkara</title>"
        "<link rel='stylesheet' href='style.css'></head><body>"
        "<header><a href='index.html'>← Все материалы</a></header>"
        "<div class='wrap'><h1>Открыть сохранённую страницу</h1>"
        "<p class='meta'>Вставьте адрес минкары — параметры, хвост Google Translate "
        "и служебные метки будут проигнорированы.</p>"
        "<div class='controls'>"
        "<input id='url' type='text' placeholder='https://minkara.carview.co.jp/…'>"
        "<button id='go' style='padding:8px 16px;border:1px solid #d1d5db;"
        "border-radius:8px;background:#fff;cursor:pointer'>Открыть</button></div>"
        "<div id='result' class='meta' style='margin-top:1em'></div></div>"
        "<script src='url-map.js'></script><script>" + OPEN_JS + "</script>"
        "</body></html>"
    )


def render_index(entries: list[dict], lang: str = "ru") -> str:
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Minkara archive — Honda Freed</title>"
        "<link rel='stylesheet' href='style.css'></head><body>"
        "<header><strong>Minkara archive</strong> · Honda Freed · "
        "<a href='open.html'>открыть по адресу</a></header>"
        "<div class='wrap'><h1>Материалы</h1>"
        "<div class='controls'>"
        "<input id='q' type='search' placeholder='Поиск по заголовкам и тексту (ru/ja)'>"
        "<select id='kind'><option value=''>Все типы</option>"
        "<option value='note'>Заметки</option><option value='parts'>Запчасти</option>"
        "<option value='review'>Отзывы</option><option value='product'>Товары</option>"
        "<option value='qa'>Вопросы</option><option value='model'>Модели</option></select>"
        "<div class='multiselect' id='model-box'>"
        "<button id='model-toggle' type='button'>Все модели</button>"
        "<div class='multiselect-menu' id='model-menu' hidden></div></div>"
        "<select id='gen'><option value=''>Все поколения</option>"
        "<option value='1'>1-е</option><option value='2'>2-е</option>"
        "<option value='3'>3-е</option></select>"
        "</div><div class='meta'><span id='count'></span></div>"
        "<div id='list'></div>"
        "<div id='pager' class='pager'></div></div>"
        "<div id='drawer-backdrop' class='drawer-backdrop'></div>"
        "<aside id='drawer' class='drawer' aria-hidden='true'>"
        "<div id='drawer-resizer' class='drawer-resizer' title='Потяните, чтобы изменить ширину'></div>"
        "<div class='drawer-head'><strong>Предпросмотр</strong><span>"
        "<button id='drawer-pdf' title='Сохранить в PDF (печать)'>PDF</button>"
        "<button id='drawer-close' title='Закрыть (Esc)'>×</button></span></div>"
        "<iframe id='drawer-frame' title='Предпросмотр'></iframe></aside>"
        "<footer>Личный офлайн-архив. Контент принадлежит авторам и Carview.</footer>"
        "<script src='search-index.js'></script><script>"
        + INDEX_JS.replace("__KIND_LABELS__", KIND_LABELS_JS).replace("__SHOW_JA__", "true" if lang == "both" else "false")
        + "</script>"
        "</body></html>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка офлайн-сайта")
    parser.add_argument("--lang", choices=["both", "ru", "ja"], default="ru")
    parser.add_argument("--clean", action="store_true", help="удалить out/site перед сборкой")
    args = parser.parse_args()

    settings = load_settings()
    load_taxonomy(settings)
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
                "d": ru_date(meta.get("date")),
                "c": " / ".join(ru_category(c) for c in (meta.get("categories") or [])),
                "m": page["model"] or "",
                "mn": ru_model(meta.get("car_model") or meta.get("model")),
                "g": page["generation"],
                "uid": page["uid"],
                "car": page["car"],
                "x": search_text(meta, tr),
            }
        )

    by_model: dict[str, list[dict]] = {}
    for entry in entries:
        by_model.setdefault(entry["m"], []).append(entry)

    nav_all: dict[str, dict] = {}
    for kind in KINDS:
        if kind == "note":
            ordered_urls = note_order(records, settings.base_url)
            ordered = [path_map[url] for url in ordered_urls if url in path_map]
        else:
            ordered = [entry["u"] for entry in entries if entry["k"] == kind]
        nav_all[kind] = nav_from_order(ordered)

    # Порядок для фильтров: по модели и по модели+поколению.
    nav_model: dict[tuple, dict] = {}
    nav_gen: dict[tuple, dict] = {}
    for kind in KINDS:
        models = sorted({entry["m"] for entry in entries if entry["k"] == kind})
        for model in models:
            if kind == "note":
                subset = [
                    record
                    for record in records
                    if record[0]["kind"] == "note"
                    and (record[0]["model"] or "") == model
                ]
                ordered_urls = note_order(subset, settings.base_url)
                ordered = [path_map[url] for url in ordered_urls if url in path_map]
            else:
                ordered = [
                    entry["u"]
                    for entry in entries
                    if entry["k"] == kind and entry["m"] == model
                ]
            nav_model[(kind, model)] = nav_from_order(ordered)

            generations = sorted(
                {
                    entry["g"]
                    for entry in entries
                    if entry["k"] == kind and entry["m"] == model and entry["g"] is not None
                }
            )
            for generation in generations:
                if kind == "note":
                    subset = [
                        record
                        for record in records
                        if record[0]["kind"] == "note"
                        and (record[0]["model"] or "") == model
                        and record[0]["generation"] == generation
                    ]
                    ordered_urls = note_order(subset, settings.base_url)
                    ordered = [path_map[url] for url in ordered_urls if url in path_map]
                else:
                    ordered = [
                        entry["u"]
                        for entry in entries
                        if entry["k"] == kind
                        and entry["m"] == model
                        and entry["g"] == generation
                    ]
                nav_gen[(kind, model, generation)] = nav_from_order(ordered)

    built = 0
    for page, meta, tr in records:
        renderer = RENDERERS.get(page["kind"])
        if renderer is None:
            continue
        rel = page_relpath(page)
        nav = nav_all.get(page["kind"], {}).get(rel)
        variants = {
            "all": nav,
            "model": nav_model.get((page["kind"], page["model"] or ""), {}).get(rel),
        }
        if page["generation"] is not None:
            variants["gen"] = nav_gen.get(
                (page["kind"], page["model"] or "", page["generation"]), {}
            ).get(rel)
        else:
            variants["gen"] = variants["model"]
        if page["kind"] == "model":
            html_text = renderer(
                settings,
                page,
                meta,
                tr,
                path_map,
                args.lang,
                related=by_model.get(page["model"] or "", []),
                nav=nav,
            )
        else:
            html_text = renderer(settings, page, meta, tr, path_map, args.lang, nav=nav)
        if page["kind"] in ("note", "parts", "review", "qa"):
            block = owner_block(page)
            if block:
                html_text = html_text.replace("<footer>", block + "<footer>")
        if variants.get("all") or variants.get("model"):
            html_text = inject_nav(html_text, variants)
        target = settings.site_dir / page_relpath(page)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(minify_html(html_text), encoding="utf-8")
        built += 1

    by_author: dict[int, list[dict]] = {}
    by_car: dict[tuple[int, int], list[dict]] = {}
    for entry in entries:
        uid = entry.get("uid")
        car = entry.get("car")
        if not uid:
            continue
        by_author.setdefault(uid, []).append(entry)
        if car:
            by_car.setdefault((uid, car), []).append(entry)

    for (uid, car), items in by_car.items():
        target = settings.site_dir / "cars" / f"{uid}-{car}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            render_hub(f"Машина {uid}/{car}", items), encoding="utf-8"
        )
    for uid, items in by_author.items():
        target = settings.site_dir / "authors" / f"{uid}.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(minify_html(render_hub(f"Автор #{uid}", items)), encoding="utf-8")
    print(f"Страниц авторов: {len(by_author)}, машин: {len(by_car)}")

    url_map = {
        urls.canonical(page["url"]): page_relpath(page)
        for page, _meta, _tr in records
    }
    (settings.site_dir / "url-map.js").write_text(
        "window.MINKARA_URLS = " + json.dumps(url_map, ensure_ascii=False) + ";",
        encoding="utf-8",
    )
    (settings.site_dir / "open.html").write_text(minify_html(render_open_page()), encoding="utf-8")

    (settings.site_dir / "search-index.js").write_text(
        "window.MINKARA_INDEX = " + json.dumps(entries, ensure_ascii=False) + ";",
        encoding="utf-8",
    )
    (settings.site_dir / "index.html").write_text(minify_html(render_index(entries, args.lang)), encoding="utf-8")

    print(f"Собрано страниц: {built}")
    print(f"Сайт: {settings.site_dir}/index.html")
    if not built:
        print("Пока нечего собирать: сначала выполните 01_discover и 02_fetch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
