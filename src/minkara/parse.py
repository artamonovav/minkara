"""Парсеры страниц minkara.

Функции чистые: принимают HTML и URL, возвращают словари. Сеть и БД здесь
не используются, поэтому парсеры легко тестировать на сохранённых фикстурах.
"""
from __future__ import annotations

import re
import warnings
from typing import Any

from bs4 import BeautifulSoup

try:  # BeautifulSoup предупреждает о XHTML-документах — нам это не мешает
    from bs4 import XMLParsedAsHTMLWarning

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except Exception:  # pragma: no cover
    pass


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _text(element) -> str:
    return element.get_text(" ", strip=True) if element is not None else ""


def _text_br(element) -> str:
    """Текст с сохранением переводов строк (<br> -> \\n)."""
    if element is None:
        return ""
    for br in element.find_all("br"):
        br.replace_with("\n")
    return re.sub(r"\n{3,}", "\n\n", element.get_text()).strip()


def _int(value: str | None) -> int | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else None


def _table_rows(soup: BeautifulSoup) -> dict[str, str]:
    rows: dict[str, str] = {}
    for tr in soup.select("table tr"):
        th, td = tr.find("th"), tr.find("td")
        if th is not None and td is not None:
            key = _text(th)
            if key:
                rows[key] = _text(td)
    return rows


# --------------------------------------------------------------------------
# Листинги
# --------------------------------------------------------------------------


def parse_listing(html: str) -> list[dict[str, Any]]:
    """Элементы списка заметок/обзоров.

    Основной список — li.item с ссылкой a[id$=_HL_Image]. Блок
    «注目のコンテンツ» (li.itemlist) сюда не попадает.
    """
    soup = soup_of(html)
    items: list[dict[str, Any]] = []
    for li in soup.select("li.item"):
        link = li.select_one('a[id$="_HL_Image"]')
        if link is None or not link.get("href"):
            continue
        title_el = li.select_one("h2.article-title a")
        lead_el = li.select_one("p.lead")
        date_el = li.select_one("span.date")
        user_el = li.select_one("span.username a")
        likes = li.select_one("ul.sharevalue li.like span.value")
        comments = li.select_one("ul.sharevalue li.comment span.value")
        thumbs = [img.get("src") for img in li.select("ol.figure4 img") if img.get("src")]
        items.append(
            {
                "url": link["href"],
                "title": _text(title_el),
                "lead": _text(lead_el),
                "date": _text(date_el),
                "user": _text(user_el),
                "likes": _int(_text(likes)),
                "comments": _int(_text(comments)),
                "thumbs": thumbs,
                "difficulty": len(li.select("div.stars span.cmn_icon_difficult")),
            }
        )
    return items


def listing_has_items(html: str) -> bool:
    return "UnitList_rList" in html


# --------------------------------------------------------------------------
# Заметка (整備手帳)
# --------------------------------------------------------------------------


def parse_note(html: str, url: str = "") -> dict[str, Any]:
    soup = soup_of(html)
    title_el = soup.select_one("h1.contentsTitle")
    date_el = soup.select_one("p.user-article-header__date")
    car_el = soup.select_one('a[id$="_HL_UserCarTitle"]')
    car_profile_el = soup.select_one('a[id$="_HL_UserCar"]')
    likes_el = soup.select_one('span[id^="txtLikeCount"]')
    rows = _table_rows(soup)

    gallery: list[dict[str, Any]] = []
    for index, title in enumerate(soup.select("div.galleryTitle"), start=1):
        photo = title.find_next_sibling("div", class_="galleryPhoto")
        memo = photo.find_next_sibling("div", class_="galleryMemo") if photo else None
        image_el = photo.select_one("img") if photo else None
        page_el = photo.select_one("a") if photo else None
        gallery.append(
            {
                "idx": index,
                "number": _text(title),
                "image": (image_el.get("src") if image_el else None),
                "page": (page_el.get("href") if page_el else None),
                "memo": _text_br(memo),
            }
        )

    comments: list[dict[str, Any]] = []
    for comment_title in soup.select("div.commentTitle"):
        author_el = comment_title.select_one("a")
        date = comment_title.find_next_sibling("div", class_="commentDate")
        body = comment_title.find_next_sibling("div", class_="commentArea")
        comments.append(
            {
                "author": _text(author_el) or _text(comment_title),
                "date": _text(date),
                "text": _text_br(body),
            }
        )

    prev_el = soup.select_one('a[id$="_Pager3_HL_Pre"]')
    next_el = soup.select_one('a[id$="_Pager3_HL_Next"]')
    list_el = soup.select_one('a[id$="_Pager3_HL_List"]')

    return {
        "url": url,
        "title": _text(title_el),
        "date": re.sub(r"^作業日[：:]\s*", "", _text(date_el)),
        "categories": [_text(a) for a in soup.select("ul.article-category-contents a")],
        "car_model": _text(car_el),
        "car_profile": (car_profile_el.get("href") if car_profile_el else None),
        "difficulty": rows.get("難易度"),
        "work_time": rows.get("作業時間"),
        "likes": _int(_text(likes_el)),
        "gallery": gallery,
        "comments": comments,
        "prev": (prev_el.get("href") if prev_el else None),
        "next": (next_el.get("href") if next_el else None),
        "note_list": (list_el.get("href") if list_el else None),
    }


# --------------------------------------------------------------------------
# Профиль машины
# --------------------------------------------------------------------------


def parse_profile(html: str, url: str = "") -> dict[str, Any]:
    soup = soup_of(html)
    rows = _table_rows(soup)
    title_el = soup.select_one(".car_title") or soup.select_one("h2")
    return {
        "url": url,
        "title": _text(title_el),
        "grade": rows.get("グレード"),
        "code": rows.get("型式"),
        "color": rows.get("ボディーカラー"),
        "ownership": rows.get("所有形態"),
        "history": rows.get("車歴"),
        "period": rows.get("所有期間"),
        "rows": rows,
    }


# --------------------------------------------------------------------------
# Отзыв о запчасти (parts.aspx)
# --------------------------------------------------------------------------


def parse_parts(html: str, url: str = "") -> dict[str, Any]:
    soup = soup_of(html)
    title_el = soup.select_one("h1.contentsTitle")
    date_el = soup.select_one("p.user-article-header__date")
    score_el = soup.select_one("em.score")
    memo_el = soup.select_one(".userCarPhotoMemo")
    photo_el = soup.select_one("#UserCarPhoto img")
    rows = _table_rows(soup)
    return {
        "url": url,
        "title": _text(title_el),
        "date": _text(date_el),
        "score": _text(score_el),
        "text": _text_br(memo_el),
        "image": (photo_el.get("src") if photo_el else None),
        "categories": [_text(a) for a in soup.select("ul.article-category-contents a")],
        "rows": rows,
    }


# --------------------------------------------------------------------------
# Отзыв об автомобиле (review/detail.aspx)
# --------------------------------------------------------------------------


def parse_review(html: str, url: str = "") -> dict[str, Any]:
    soup = soup_of(html)
    box = soup.select_one(".kr_reviewbox") or soup.select_one("main")
    title_el = soup.select_one("h1")
    score_el = soup.select_one(".kr_reviewStar__title, .kr_reviewStar")
    body_parts = []
    if box is not None:
        for paragraph in box.select("p"):
            text = _text(paragraph)
            if len(text) > 20:
                body_parts.append(text)
    return {
        "url": url,
        "title": _text(title_el),
        "score": _text(score_el),
        "text": "\n\n".join(dict.fromkeys(body_parts)),
    }


# --------------------------------------------------------------------------
# Единицы перевода
# --------------------------------------------------------------------------


def extract_text_units(parsed: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    """Какие строки страницы отправлять на перевод.

    Возвращает список {kind, idx, ja}. idx стабилен в пределах страницы.
    """
    units: list[dict[str, Any]] = []
    if kind == "note":
        if parsed.get("title"):
            units.append({"kind": "title", "idx": 0, "ja": parsed["title"]})
        for item in parsed.get("gallery") or []:
            if item.get("memo"):
                units.append({"kind": "memo", "idx": item["idx"], "ja": item["memo"]})
        for i, comment in enumerate(parsed.get("comments") or [], start=1):
            if comment.get("text"):
                units.append({"kind": "comment", "idx": i, "ja": comment["text"]})
    elif kind == "parts":
        if parsed.get("title"):
            units.append({"kind": "title", "idx": 0, "ja": parsed["title"]})
        if parsed.get("text"):
            units.append({"kind": "review", "idx": 1, "ja": parsed["text"]})
    elif kind == "review":
        if parsed.get("title"):
            units.append({"kind": "title", "idx": 0, "ja": parsed["title"]})
        if parsed.get("text"):
            units.append({"kind": "review", "idx": 1, "ja": parsed["text"]})
    return units
