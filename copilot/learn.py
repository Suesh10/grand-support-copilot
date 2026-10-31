"""Учёба на правках админа: исправленный ответ становится образцом для похожих обращений.

Правка не обходит защиту: черновик из урока проходит те же проверки цитат и обещаний.
Уроки работают только в интерфейсе админа. make eval и make predict о них не знают,
иначе метрики зависели бы от того, что админ случайно нажал на своей машине.
"""

import json
import threading

from sklearn.metrics.pairwise import cosine_similarity

from . import config, retrieve

LESSONS_PATH = config.ARTIFACTS_DIR / "lessons.json"
MIN_SIMILAR = 0.25  # похожесть обращений, с которой правка переносится на новый случай
MIN_REPLY = 8
_lock = threading.Lock()
_active = False


def activate() -> None:
    global _active
    _active = True


def _read() -> list[dict]:
    return json.loads(LESSONS_PATH.read_text(encoding="utf-8")) if LESSONS_PATH.exists() else []


def lessons() -> list[dict]:
    return _read()


def _write(lessons: list[dict]) -> None:
    LESSONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LESSONS_PATH.write_text(json.dumps(lessons, ensure_ascii=False), encoding="utf-8")


def add(ticket_id: str, text: str, reply: str, category: str, lang: str, nick: str | None) -> None:
    if len(reply.strip()) < MIN_REPLY:
        return
    with _lock:
        lessons = [x for x in _read() if x["ticket_id"] != ticket_id]
        lessons.append({"ticket_id": ticket_id, "text": text, "reply": reply.strip(), "category": category, "lang": lang, "nick": nick})
        _write(lessons)


def remove(ticket_id: str) -> None:
    with _lock:
        _write([x for x in _read() if x["ticket_id"] != ticket_id])


def find(text: str, category: str, lang: str) -> dict | None:
    """Самая близкая правка той же категории и языка или None."""
    if not _active:
        return None
    lessons = [x for x in _read() if x["category"] == category and x["lang"] == lang]
    index = retrieve.load()
    if not lessons or not index:
        return None
    vectors = index["vectorizer"].transform([text] + [x["text"] for x in lessons])
    scores = cosine_similarity(vectors[0], vectors[1:]).ravel()
    best = int(scores.argmax())
    return lessons[best] if scores[best] >= MIN_SIMILAR else None
