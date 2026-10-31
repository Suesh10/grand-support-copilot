"""RAG по правилам: поиск пунктов, подходящих к обращению, по их тексту.

Символьные n-граммы находят пункт и при опечатках. Запрос — текст игрока плюс
описание категории из taxonomy.json: короткое «оск родни» само по себе правило
не найдёт. Кандидаты упорядочены: сначала то, что подтверждено категорией и
исходом, затем найденное поиском. LLM выбирает только из этого списка.
"""

import json
import re
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer

from . import config
from .labels import REF_CATEGORY
from .rules import load_points
from .signals import THREAT_RE

# Пункт, который обосновывает сам исход: это правила подачи жалоб.
VERDICT_REFS = {"need_evidence": "1.2.2 ЖБ", "invalid_format": "1.3.1 ЖБ", "duplicate": "1.2.9 ЖБ"}
# Основной пункт категории (taxonomy.json), если поиск и игрок ничего точнее не дали.
# У DM основного пункта нет: это термин из раздела «RP термины», где нет нумерованных пунктов,
# поэтому номер ставится, только если случай подходит под конкретный пункт.
PRIMARY_REFS = {"complaint.insult": "2.1 ОП", "complaint.cheat": "5.2 ОП",
                "complaint.scam": "4.1 ОП", "complaint.rmt_ads": "4.4 ОП", "complaint.admin": "3.4 ОП",
                "complaint.invalid": "1.3.1 ЖБ"}
# ТЗ: ответ без цитат допустим только там, где правила не нужны.
NEEDS_CITATION = set(PRIMARY_REFS)
MIN_SCORE = 0.08
HOME_RE = re.compile(r"\bдом|\bквартир|\buy\b|\buyga\b|үй", re.I)
LEFT_RP_RE = re.compile(r"уш[её]л от рп|вышел из игры|ливнул|\bлив\b|покинул", re.I)
ROPE_RE = re.compile(r"вер[её]вк|связа|связк|мешок|мешк|наручн|похит|ограб", re.I)
GZ_RE = re.compile(r"\bgz\b|\bzz\b|\bзз\b|\bгз\b|зел[её]н|yashil", re.I)


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
    has_topic = any(not r.endswith(" ЖБ") for r in cited)
    topic = next((r for r in refs if not r.endswith(" ЖБ")), None)
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
    fits = [r for r in hits if REF_CATEGORY.get(r) == category and _applies(r, text)]
    ranked = [
        VERDICT_REFS.get(verdict or ""),
        "2.6 ОП" if category == "complaint.insult" and THREAT_RE.search(text) else None,  # пункт об угрозах, а не об оскорблении
        # Верёвка в зелёной зоне это криминальное действие, а не убийство: так решают админы.
        "1.2 GZ" if category == "complaint.dm" and GZ_RE.search(text) and ROPE_RE.search(text) else None,
        *[r for r in player_refs if REF_CATEGORY.get(r) == category],
        *fits,
        PRIMARY_REFS.get(category),
    ]
    # Поиск вне категории нужен там, где основного пункта нет. У остальных он даёт формально
    # существующие, но неуместные пункты («Общие положения» правил жалоб).
    if category not in PRIMARY_REFS and category != "complaint.dm":
        ranked += [r for r in hits if not r.endswith(" ЖБ")] + player_refs
    out: list[str] = []
    for ref in ranked:
        if ref and ref in points and ref not in out:
            out.append(ref)
    return out[:6]


def _applies(ref: str, text: str) -> bool:
    """Узкие пункты уместны, только если игрок говорит именно об этой ситуации."""
    if ref.endswith(" GZ"):
        return bool(GZ_RE.search(text))
    if ref.startswith("5.4"):
        return bool(HOME_RE.search(text))
    if ref.startswith("5.3"):
        return bool(LEFT_RP_RE.search(text))
    if ref in ("5.5 ОП", "5.9 ОП"):
        return False
    return True
