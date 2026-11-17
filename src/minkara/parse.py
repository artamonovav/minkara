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
    author = ""
    for link in soup.select('a[href*="/profile/"]'):
        text = _text(link)
        if text and text not in ("プロフィール", "プロフィールを見る"):
            author = text
    return {
        "url": url,
        "title": _text(title_el),
        "date": _text(date_el),
        "score": _text(score_el),
        "author": author,
        "text": _text_br(memo_el),
        "image": (photo_el.get("src") if photo_el else None),
        "categories": [_text(a) for a in soup.select("ul.article-category-contents a")],
        "rows": rows,
    }


# --------------------------------------------------------------------------
# Каталог обзоров запчастей: список товаров -> товар -> отзывы
# --------------------------------------------------------------------------


def _split_rating(value: str) -> tuple[str, int | None]:
    """'4.43 （7 件）' -> ('4.43', 7)."""
    score = ""
    match = re.search(r"\d+(?:\.\d+)?", value or "")
    if match:
        score = match.group(0)
    count = None
    count_match = re.search(r"[（(]\s*(\d+)\s*件", value or "")
    if count_match:
        count = int(count_match.group(1))
    return score, count


def parse_product_listing(html: str) -> list[dict[str, Any]]:
    soup = soup_of(html)
    items: list[dict[str, Any]] = []
    for li in soup.select("li.item-common"):
        link = li.select_one('a[id$="_HyperLink_PartsName"]') or li.select_one(
            'a[id$="_HyperLink_PartsImage"]'
        )
        if link is None or not link.get("href"):
            continue
        rows = _table_rows(li)
        score, reviews = _split_rating(rows.get("評価", ""))
        image_el = li.select_one("img.parts_image")
        image = None
        if image_el is not None:
            image = image_el.get("data-original") or image_el.get("src")
            if image and "loading.gif" in image:
                image = image_el.get("data-original")
        latest = li.select_one("a.contents-bottom")
        items.append(
            {
                "url": link["href"],
                "title": _text(link),
                "image": image,
                "score": score,
                "reviews": reviews,
                "price": rows.get("購入価格"),
                "maker": rows.get("メーカー"),
                "brand": rows.get("ブランド"),
                "series": rows.get("シリーズ"),
                "categories": [_text(li_) for li_ in li.select("ol.categorytext li")],
                "latest_review": (latest.get("href") if latest else None),
            }
        )
    return items


def parse_product(html: str, url: str = "") -> dict[str, Any]:
    soup = soup_of(html)
    headings = [text for text in (_text(h) for h in soup.select("h1")) if text]
    title = headings[-1] if headings else ""
    title = re.sub(r"の評価・評判・口コミ$", "", title).strip()
    rating_el = soup.select_one(".parts-data__review-star-point")
    header_el = soup.select_one("#reviewlist")
    review_links: list[str] = []
    for link in soup.select('a[href*="/parts.aspx"]'):
        href = link.get("href") or ""
        if re.match(r"^/userid/\d+/car/\d+/\d+/parts\.aspx$", href):
            if href not in review_links:
                review_links.append(href)
    return {
        "url": url,
        "title": title,
        "rating": _text(rating_el),
        "reviews_header": _text(header_el),
        "reviews": review_links,
        "categories": [_text(a) for a in soup.select("ol.categorytext li")],
    }


# --------------------------------------------------------------------------
# Отзывы об автомобиле (クルマレビュー)
# --------------------------------------------------------------------------


def parse_review_listing(html: str) -> list[dict[str, Any]]:
    soup = soup_of(html)
    items: list[dict[str, Any]] = []
    containers = soup.select("ul.review-carpage-list > li") or soup.select(
        "div.kr_reviewbox"
    )
    for container in containers:
        box = container.select_one("div.kr_reviewbox") or container
        link = container.select_one("h2.kr_ttltxt a")
        if link is None:
            for candidate in container.select('a[href*="review/detail.aspx"]'):
                text = _text(candidate)
                if text and text != "もっと見る":
                    link = candidate
                    break
        if link is None:
            continue
        grade_el = box.select_one(".kr_reviewGrade")
        model_el = box.select_one(".kr_reviewModel")
        model = _text(model_el)
        grade = _text(grade_el)
        if grade and model.endswith(grade):
            model = model[: -len(grade)].strip()
        date = ""
        for li in box.select("li"):
            if "レビュー日" in _text(li):
                date_el = li.select_one(".kr_reviewDaysize")
                date = _text(date_el) or _text(li).replace("レビュー日：", "").strip()
                break
        image = None
        for img in box.select("img"):
            src = img.get("src") or ""
            if "cdn.snsimg" in src and "/User/" not in src:
                image = src
                break
        items.append(
            {
                "url": link["href"],
                "title": _text(link),
                "author": _text(box.select_one(".user-name a")),
                "model": model,
                "grade": grade,
                "date": date,
                "score": _text(box.select_one(".kr_reviewStar__title")),
                "image": image,
            }
        )
    return items


def parse_review(html: str, url: str = "") -> dict[str, Any]:
    soup = soup_of(html)
    box = soup.select_one("div.kr_reviewbox") or soup
    title = re.split(r"\s+-\s+", _text(soup.select_one("h1")), maxsplit=1)[0].strip()
    model = _text(box.select_one(".kr_reviewModel"))
    grade = _text(box.select_one(".kr_reviewGrade"))
    if grade and model.endswith(grade):
        model = model[: -len(grade)].strip()

    date = ""
    for li in box.select("li"):
        if "レビュー日" in _text(li):
            date = _text(li).replace("レビュー日：", "").strip()
            break

    aspects: dict[str, str] = {}
    for item in box.select(".detail-value__item"):
        name = _text(item.select_one(".detail-value__item-name"))
        num = _text(item.select_one(".detail-value__num"))
        if name:
            aspects[name] = num

    sections: dict[str, str] = {}
    for title_el in box.select("dt.review-data__title"):
        body = title_el.find_next_sibling("dd")
        key = _text(title_el)
        if key:
            sections[key] = _text_br(body)

    related = ""
    for dt in box.select("dt"):
        if "関連情報URL" in _text(dt):
            related = _text(dt.find_next_sibling("dd"))
            break

    images: list[str] = []
    for img in box.select("img"):
        src = img.get("src") or ""
        if "cdn.snsimg" in src and "/User/" not in src and src not in images:
            images.append(src)

    return {
        "url": url,
        "title": title,
        "author": _text(box.select_one(".user-name a")),
        "model": model,
        "grade": grade,
        "date": date,
        "score": _text(box.select_one(".kr_reviewStar__title")),
        "aspects": aspects,
        "sections": sections,
        "related_url": related,
        "images": images,
        "text": "\n\n".join(value for value in sections.values() if value),
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
        idx = 1
        for value in (parsed.get("sections") or {}).values():
            if value:
                units.append({"kind": "review", "idx": idx, "ja": value})
                idx += 1
    elif kind == "product":
        if parsed.get("title"):
            units.append({"kind": "title", "idx": 0, "ja": parsed["title"]})
    return units
