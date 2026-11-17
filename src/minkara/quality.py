"""Эвристики качества перевода JA -> RU.

Не заменяют ручную проверку, но позволяют автоматически находить явно
неудачные сегменты (непереведённое, обрезанное, мусор) и отправлять их на
пост-редактирование в DeepL или LLM.
"""
from __future__ import annotations

import re

CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")

# Пары «японский термин -> недопустимый русский вариант», характерные для
# машинного перевода (Google часто путает 交換 с «обменом»).
BAD_TERMS: dict[str, list[str]] = {
    "交換": ["обмен"],
    "取付": ["прикрепить", "прикрепление"],
    "整備": ["техническое обслуживание", "обслуживание"],
}


def score_translation(ja: str, ru: str, glossary: dict[str, str] | None = None) -> tuple[int, list[str]]:
    """Возвращает (штраф, причины). 0 — всё хорошо, >=2 — стоит перепроверить."""
    reasons: list[str] = []
    score = 0
    ja = ja or ""
    ru = ru or ""

    if not ru.strip():
        return 10, ["пустой перевод"]
    if ru.strip() == ja.strip():
        return 10, ["перевод совпадает с оригиналом"]
    if not CJK_RE.search(ja):
        return 0, []
    if CJK_RE.search(ru):
        score += 5
        reasons.append("в переводе остался японский текст")
    latin = len(re.findall(r"[A-Za-z]", ja))
    cjk = len(CJK_RE.findall(ja))
    if not CYRILLIC_RE.search(ru) and latin <= cjk:
        # Названия моделей/товаров на латинице не обязаны содержать кириллицу.
        score += 5
        reasons.append("нет кириллицы")
    if "[ru]" in ru or "⟦" in ru:
        score += 5
        reasons.append("служебный маркер/заглушка")

    ratio = len(ru) / max(len(ja), 1)
    if ratio < 0.6:
        score += 2
        reasons.append(f"подозрительно короткий ({ratio:.2f})")
    elif ratio > 6.0:
        score += 2
        reasons.append(f"подозрительно длинный ({ratio:.2f})")

    for artifact in ("、、", "。。", "，，", "  。", "??"):
        if artifact in ru:
            score += 1
            reasons.append(f"артефакт пунктуации {artifact!r}")
            break

    for ja_term, bad_variants in BAD_TERMS.items():
        if ja_term in ja:
            lowered = ru.lower()
            if any(bad in lowered for bad in bad_variants):
                score += 2
                reasons.append(f"термин {ja_term} переведён как {bad_variants[0]!r}")

    if glossary:
        missing = 0
        for ja_term, ru_term in glossary.items():
            if ja_term and ja_term in ja and ru_term and ru_term.lower() not in ru.lower():
                missing += 1
        if missing >= 2:
            score += 1
            reasons.append(f"глоссарий: не найдено терминов {missing}")

    return score, reasons


def is_bad(ja: str, ru: str, glossary: dict[str, str] | None = None) -> bool:
    score, _ = score_translation(ja, ru, glossary)
    return score >= 2
