"""Статьи центра поддержки: на вопрос об игре ссылка на готовый ответ вместо «уточните вопрос».

Сервис не пересказывает игру своими словами: он только находит статью, поэтому выдумать факт не может.
Пороги подобраны на вопросах валидации: при меньшем сходстве статья чаще мимо, и лучше попросить уточнить.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

PATH = Path(__file__).parent / "support_articles.json"
MIN_ASKED = 0.29  # игрок явно спрашивает
MIN_STATED = 0.4  # игрок просто описывает проблему: «пропала машина»
ASK_RE = re.compile(r"\?|\bкак\b|\bгде\b|\bпочему\b|что делать|можно ли|\bсколько\b|подскаж", re.I)

HACK_ARTICLE = "11029958"
PAYMENT_ARTICLE = "11029218"
OUTAGE_ARTICLE = "12802228"


@lru_cache(maxsize=1)
def articles() -> dict:
    return {a["id"]: a for a in json.loads(PATH.read_text(encoding="utf-8"))} if PATH.exists() else {}


@lru_cache(maxsize=1)
def _index() -> tuple | None:
    found = list(articles().values())
    if not found:
        return None
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    # Название важнее ключевых слов, поэтому оно считается дважды.
    return vec, vec.fit_transform(f"{a['title']} {a['title']} {' '.join(a['terms'])}".lower() for a in found), found


def article(article_id: str) -> dict | None:
    item = articles().get(article_id)
    return {"title": item["title"], "url": item["url"]} if item else None


def find(text: str) -> dict | None:
    """Статья, которая отвечает на обращение, или None, если уверенности нет."""
    index = _index()
    if not index or not text.strip():
        return None
    vec, matrix, found = index
    scores = linear_kernel(vec.transform([text.lower()]), matrix)[0]
    best = int(scores.argmax())
    enough = scores[best] >= MIN_ASKED if ASK_RE.search(text) else scores[best] >= MIN_STATED and len(text.split()) > 1
    return article(found[best]["id"]) if enough else None
