"""RAG по правилам: поиск пунктов, подходящих к обращению, по их тексту.

Символьные n-граммы находят пункт и при опечатках. Запрос — текст игрока плюс
описание категории из taxonomy.json: короткое «оск родни» само по себе правило
не найдёт. Кандидаты упорядочены: сначала то, что подтверждено категорией и
исходом, затем найденное поиском. LLM выбирает только из этого списка.
"""

import json
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer

from . import config
from .labels import REF_CATEGORY
from .rules import load_points

# Пункт, который обосновывает сам исход: это правила подачи жалоб.
VERDICT_REFS = {"need_evidence": "1.2.2 ЖБ", "invalid_format": "1.3.1 ЖБ", "duplicate": "1.2.9 ЖБ"}
# Основной пункт категории (taxonomy.json), если поиск и игрок ничего точнее не дали.
PRIMARY_REFS = {"complaint.insult": "2.1 ОП", "complaint.cheat": "5.2 ОП", "complaint.dm": "5.3 ОП",
                "complaint.scam": "4.1 ОП", "complaint.rmt_ads": "4.4 ОП", "complaint.admin": "3.4 ОП",
                "complaint.invalid": "1.3.1 ЖБ"}
# ТЗ: ответ без цитат допустим только там, где правила не нужны.
NEEDS_CITATION = set(PRIMARY_REFS)
MIN_SCORE = 0.08


@lru_cache(maxsize=1)
def _index() -> tuple | None:
    points = load_points()
    if not points:
        return None
    refs = list(points)
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    matrix = vec.fit_transform(f"{points[r].section_title}. {points[r].text}" for r in refs)
    return vec, matrix, refs


@lru_cache(maxsize=1)
def _category_hints() -> dict[str, str]:
    if not config.TAXONOMY_PATH.exists():
        return {}
    data = json.loads(config.TAXONOMY_PATH.read_text(encoding="utf-8"))
    return {c["code"]: f"{c['title']}. {' '.join(c.get('examples', []))}" for c in data["categories"]}


def search(text: str, category: str = "", k: int = 5) -> list[tuple[str, float]]:
    """Топ-k пунктов правил по близости к обращению."""
    index = _index()
    if index is None:
        return []
    vec, matrix, refs = index
    query = vec.transform([f"{text} {_category_hints().get(category, '')}"])
    scores = (matrix @ query.T).toarray().ravel()
    top = scores.argsort()[::-1][:k]
    return [(refs[i], float(scores[i])) for i in top if scores[i] >= MIN_SCORE]


def required(category: str, verdict: str | None, refs: list[str], cited: list[str]) -> list[str]:
    """Какие пункты обязаны быть в жалобе: по теме нарушения и, если исход на него опирается, правило жалоб."""
    procedural = set(VERDICT_REFS.values()) | {PRIMARY_REFS["complaint.invalid"]}
    has_topic = any(r not in procedural for r in cited)
    topic = next((r for r in refs if r not in procedural), None)
    need = [] if has_topic or topic is None else [topic]
    verdict_ref = VERDICT_REFS.get(verdict or "")
    if verdict_ref and verdict_ref in refs:
        need.append(verdict_ref)
    if not need and not cited and refs:
        need = [refs[0]]
    return need


def candidates(category: str, verdict: str | None, text: str, player_refs: list[str]) -> list[str]:
    """Пункты для черновика: от самых обоснованных к найденным поиском, без повторов."""
    points = load_points()
    hits = [ref for ref, _ in search(text, category)]
    ranked = [
        VERDICT_REFS.get(verdict or ""),
        *[r for r in player_refs if REF_CATEGORY.get(r) == category],
        *[r for r in hits if REF_CATEGORY.get(r) == category],
        PRIMARY_REFS.get(category),
        *hits,
        *player_refs,
    ]
    out: list[str] = []
    for ref in ranked:
        if ref and ref in points and ref not in out:
            out.append(ref)
    return out[:6]
