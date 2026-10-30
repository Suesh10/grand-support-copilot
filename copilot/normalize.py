"""Нормализация текста и определение языка.

На kz-серверах игра работает в cp1251, поэтому казахские буквы приходят
похожими символами из других кириллиц: ќ вместо қ, ґ вместо ғ и т.д.
"""

import re

CP1251_KK = str.maketrans({
    "ќ": "қ", "Ќ": "Қ",
    "ґ": "ғ", "Ґ": "Ғ",
    "ѕ": "ң", "Ѕ": "Ң",
    "є": "ә", "Є": "Ә",
    "ј": "ө", "Ј": "Ө",
    "ў": "ұ", "Ў": "Ұ",
    "ї": "ү", "Ї": "Ү",
})

KK_LETTERS = set("әғқңөұүһіӘҒҚҢӨҰҮҺІ")
# Частые узбекские слова и буквосочетания в латинице.
UZ_HINTS = re.compile(
    r"\b(men|menga|meni|uchun|qildi|bilan|nima|yoq|bor|iltimos|qoida|shikoyat|"
    r"haqorat|sokdi|sokindi|qanday|nega|kerak|o['ʻ‘`]|g['ʻ‘`])", re.I)
KK_HINTS = re.compile(r"\b(мен|маған|сен|неге|жоқ|бар|көмек|өтінемін|қалай|ойын|ұрды)\b", re.I)
EN_HINTS = re.compile(r"\b(the|is|please|help|my|he|she|account|cheat|hack|why)\b", re.I)
PT_HINTS = re.compile(r"\b(não|nao|por favor|ajuda|minha|meu|você|voce|conta|está)\b", re.I)
ES_HINTS = re.compile(r"\b(por favor|ayuda|mi|cuenta|está|tramposo|porque|usted)\b", re.I)


def normalize(text: str) -> str:
    """Вернуть казахские буквы, убрать лишние пробелы."""
    text = (text or "").translate(CP1251_KK)
    return re.sub(r"\s+", " ", text).strip()


def detect_lang(text: str) -> str:
    """Грубая эвристика: ru | kk | uz | en | es | pt | und."""
    t = normalize(text)
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 2:
        return "und"
    cyr = sum("а" <= c.lower() <= "я" or c.lower() == "ё" or c in KK_LETTERS for c in letters)
    if cyr / len(letters) > 0.5:
        if any(c in KK_LETTERS for c in t) or KK_HINTS.search(t):
            return "kk"
        return "ru"
    # Узбекская латиница: oʻ, gʻ с особым апострофом внутри слова.
    if re.search(r"[og][ʻ‘`'][a-z]", t, re.I):
        return "uz"
    scores = {
        "uz": len(UZ_HINTS.findall(t)),
        "pt": len(PT_HINTS.findall(t)),
        "es": len(ES_HINTS.findall(t)),
        "en": len(EN_HINTS.findall(t)),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "und"
