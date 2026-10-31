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
# «і» есть и в украинском, поэтому надёжны только остальные буквы.
STRONG_KK = set("әғқңөұүһӘҒҚҢӨҰҮҺ")
KK_SHARE = 0.06  # столько казахских букв в тексте случайно не наберётся
SHORT_TEXT = 30  # в коротком тексте хватает одной казахской буквы, если нет русских слов
SERVER_LANGS = {"kk", "uz"}  # язык сервера подсказывает ответ там, где текст ничего не говорит
# Частые узбекские слова и буквосочетания в латинице.
UZ_HINTS = re.compile(
    r"\b(men|menga|meni|uchun|qildi|bilan|nima|yoq|bor|iltimos|qoida|shikoyat|"
    r"haqorat|sokdi|sokindi|sukindi|onadan|berizla|mani|qanday|nega|kerak|o['ʻ‘`]|g['ʻ‘`]|"
    r"yordam|chora|xaqorat|sababsiz|sababsz|besabab|berila|korila|ozidan|uzidan|bunga|kishan|boglab|"
    r"sokvoti|sokinish|sokinib|sokib|kunga|oldirdi|qilaman|assalomu|nma)", re.I)
RU_WORDS = re.compile(r"\b(что|чтоб|чтобы|как|это|меня|мне|вместо|прошу|когда|тут|уже|если|свою|его|он|она)\b", re.I)
UK_WORDS = re.compile(r"\b(щоб|як|потрібно|дати|мене|будь ласка|чому)\b", re.I)
KK_HINTS = re.compile(r"\b(мен|маған|сен|неге|жоқ|бар|көмек|өтінемін|қалай|ойын|ұрды)\b", re.I)
EN_HINTS = re.compile(r"\b(the|is|please|help|my|he|she|account|cheat|hack|why)\b", re.I)
PT_HINTS = re.compile(r"\b(não|nao|por favor|ajuda|minha|meu|você|voce|conta|está)\b", re.I)
ES_HINTS = re.compile(r"\b(por favor|ayuda|mi|cuenta|está|tramposo|porque|usted)\b", re.I)


LAT_TO_CYR = str.maketrans("abvgdeziklmnoprstufhcyABVGDEZIKLMNOPRSTUFHCY",
                           "абвгдезиклмнопрстуфхсуАБВГДЕЗИКЛМНОПРСТУФХСУ")
MIXED_WORD_RE = re.compile(r"\b\w*[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]\w*\b")


def fix_mixed_script(text: str) -> str:
    """Латинские буквы внутри кириллического слова («алайda») — сбой генерации, переводим в кириллицу."""
    def fix(m: re.Match) -> str:
        word = m.group(0)
        return word.translate(LAT_TO_CYR) if re.search(r"[A-Za-z]", word) else word
    return MIXED_WORD_RE.sub(fix, text)


def normalize(text: str) -> str:
    """Вернуть казахские буквы, убрать лишние пробелы."""
    text = (text or "").translate(CP1251_KK)
    return re.sub(r"\s+", " ", text).strip()


def detect_lang(text: str, server_lang: str | None = None) -> str:
    """Язык текста, а если он не ясен, то казахский или узбекский по серверу."""
    lang = _detect_lang(text)
    return server_lang if lang == "und" and server_lang in SERVER_LANGS else lang


def _detect_lang(text: str) -> str:
    """Грубая эвристика: ru | kk | uz | en | es | pt | und."""
    t = normalize(text)
    letters = [c for c in t if c.isalpha()]
    if len(letters) < 2:
        return "und"
    cyr = sum("а" <= c.lower() <= "я" or c.lower() == "ё" or c in KK_LETTERS for c in letters)
    if cyr / len(letters) > 0.5:
        # Украинский идёт по-русски. Доля букв важнее русских слов: «он» и «мен» есть в обоих языках.
        strong = sum(c in STRONG_KK for c in t)
        if UK_WORDS.search(t):
            return "ru"
        if strong / len(letters) >= KK_SHARE:
            return "kk"
        # Одна «қ» в длинном русском тексте — опечатка на kz-сервере.
        if RU_WORDS.search(t):
            return "ru"
        if (strong and len(letters) <= SHORT_TEXT) or sum(c in KK_LETTERS for c in t) >= 2 or KK_HINTS.search(t):
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
