"""Интерфейс админа (бонус ТЗ): очередь, черновик, «отправить / править / эскалировать».

Действия админа и правки черновиков пишутся в feedback.jsonl: это обучающий
сигнал для будущих версий шаблонов и модели.
"""

import json
import os
import threading
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import config, llm, reputation
from .draft import handoff_draft
from .normalize import normalize
from .pipeline import triage_full
from .predict import open_any, ticket_to_request
from .rules import load_points, punishments

router = APIRouter()

STATIC = Path(__file__).parent / "static"
QUEUE_PATH = os.getenv("COPILOT_QUEUE", str(config.ROOT / "examples" / "sample_tickets.jsonl"))
FEEDBACK_PATH = config.ARTIFACTS_DIR / "feedback.jsonl"
ARCHIVE_PATH = config.ARTIFACTS_DIR / "archive.json"
DELETED_PATH = config.ARTIFACTS_DIR / "deleted_tickets.json"
RETENTION_DAYS = 30  # через сколько дней сайт предлагает удалить, но сам не удаляет
PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
_queue_lock = threading.Lock()  # страница и фоновый прогрев не должны считать очередь дважды
_files_lock = threading.Lock()  # два быстрых действия админа не должны затирать друг друга
GENERATE_VERDICTS = {"approved", "need_evidence", "rejected", "invalid_format", "duplicate"}


def rule_card(ref: str) -> dict | None:
    point = load_points().get(ref)
    if not point:
        return None
    return {"ref": ref, "section": point.section_title, "text": point.text.split("|")[0].strip()[:220],
            "punishments": punishments(ref)}


def appeal_from(t: dict) -> dict | None:
    """Ответ обвиняемого в жалобе идёт отдельным обращением во вкладку апелляций."""
    replies = [m for m in t.get("messages", []) if m.get("role") == "reported_player"]
    if not replies:
        return None
    return {"ticket_id": f"{t.get('ticket_id')}-appeal", "appeal_of": t.get("ticket_id"), "kind": "complaint",
            "messages": replies, "reported_hash": t.get("reported_hash"), "reported_nick": t.get("reported_nick"),
            "server_lang": t.get("server_lang"), "region": t.get("region"),
            "attachments": [f for f in t.get("attachments") or [] if f.get("from") == "reported_player"]}


@lru_cache(maxsize=1)
def raw_tickets() -> tuple:
    tickets = [json.loads(line) for line in open_any(QUEUE_PATH) if line.strip()]
    return (*tickets, *filter(None, map(appeal_from, tickets)))


def load_queue() -> tuple:
    with _queue_lock:
        return _load_queue()


@lru_cache(maxsize=1)
def _load_queue() -> tuple:
    llm.use_cache()
    tickets = raw_tickets()
    series = Counter(t.get("reported_nick") for t in tickets if t.get("reported_nick") and not t.get("appeal_of"))
    items = []
    for t in tickets:
        request = ticket_to_request(t)
        pred, meta = triage_full(request)
        refs = meta["cited_full"] or meta["rule_refs_full"]
        if t.get("appeal_of"):  # Исход апелляции решает только человек, черновик ничего не обещает.
            pred = {**pred, "category": "complaint.admin", "priority": "p2", "needs_human": True, "draft_reply": handoff_draft(pred["lang"]),
                    "reasons": ["апелляцию решает администратор"]}
            refs = []
        items.append({
            "id": t.get("ticket_id"),
            "appeal_of": t.get("appeal_of"),
            "proposal": None if t.get("appeal_of") else meta.get("proposal"),
            "kind": t.get("kind"),
            "messages": [{**m, "text": normalize(m.get("text", ""))} for m in request["messages"]],
            "images": t.get("images_count") or 0,
            "region": t.get("region"),
            "triage": pred,
            "rules": [c for c in (rule_card(r) for r in refs) if c],
            "series": series.get(t.get("reported_nick"), 1),
            "reporter_hash": t.get("reporter_hash"),
            "reporter_nick": t.get("reporter_nick"),
            "attachments": t.get("attachments") or [],  # [{url, name, type, from}]: файлы от Grand Mobile; from = reported_player у файлов обвиняемого
            "reported_hash": t.get("reported_hash"),
            "auto": not pred["needs_human"],
        })
    items.sort(key=lambda x: (PRIORITY_ORDER.get(x["triage"]["priority"], 9), not x["triage"]["needs_human"]))
    return tuple(items)


def read_archive() -> list[dict]:
    return json.loads(ARCHIVE_PATH.read_text(encoding="utf-8")) if ARCHIVE_PATH.exists() else []


def write_archive(items: list[dict]) -> None:
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE_PATH.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def read_deleted() -> list[str]:
    return json.loads(DELETED_PATH.read_text(encoding="utf-8")) if DELETED_PATH.exists() else []


class Feedback(BaseModel):
    ticket_id: str
    action: Literal["send", "edit", "escalate", "undo", "merge", "auto_ok"]
    draft_before: str = ""
    draft_after: str = ""
    category: str = ""  # вид обращения: админ мог поменять то, что определил ИИ
    ai_category: str = ""
    priority: str = ""
    reported_hash: str | None = None
    nick: str | None = None
    review_seconds: int | None = None


@router.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(STATIC / "admin.html")


@router.get("/api/queue")
def api_queue() -> dict:
    # Профили считаем при каждом запросе: они меняются от решений админа.
    # Удалённые тоже помним по id: иначе решённый тикет вернётся в очередь как новый.
    closed = {x["ticket_id"] for x in read_archive()} | set(read_deleted())
    items = [{**x, "profiles": {"reporter": reputation.profile(x["reporter_hash"]),
                                "reported": reputation.profile(x["reported_hash"])}}
             for x in load_queue() if x["id"] not in closed]
    return {"items": items, "llm": llm.status(), "notes": reputation.read_notes()}


class TranslateRequest(BaseModel):
    text: str


@router.post("/api/translate")
def api_translate(req: TranslateRequest) -> dict:
    """Русский перевод для kk/uz: админы в основном русскоязычные."""
    return {"text": llm.translate(req.text)}


class GenerateRequest(BaseModel):
    verdict: str  # approved | need_evidence | rejected | invalid_format | duplicate


@router.post("/api/generate/{ticket_id}")
def api_generate(ticket_id: str, req: GenerateRequest) -> dict:
    """Черновик по тексту обращения под исход, выбранный админом.

    Проходит те же проверки, что и обычный: цитаты, обещания, needs_human.
    Админ может свободно править результат, правка попадёт в обратную связь.
    """
    ticket = next((t for t in raw_tickets() if t.get("ticket_id") == ticket_id), None)
    if ticket is None:
        raise HTTPException(status_code=404, detail="обращение не найдено")
    if req.verdict not in GENERATE_VERDICTS:
        raise HTTPException(status_code=422, detail="неизвестный исход")
    result, meta = triage_full(ticket_to_request(ticket), verdict_override=req.verdict)
    return {"draft_reply": result["draft_reply"], "needs_human": result["needs_human"],
            "reasons": result["reasons"], "source": meta.get("draft_source"), "llm_error": meta.get("llm_error")}


@router.post("/api/feedback")
def api_feedback(fb: Feedback) -> dict:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {**fb.model_dump(), "edited": fb.draft_before != fb.draft_after, "ts": int(time.time())}
    if fb.action == "send" and fb.category.startswith("complaint."):
        reputation.remember(fb.reported_hash, fb.category)
    with _files_lock:
        with open(FEEDBACK_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        items = [x for x in read_archive() if x["ticket_id"] != fb.ticket_id]
        if fb.action in ("send", "escalate", "merge"):
            items.append({"ticket_id": fb.ticket_id, "nick": fb.nick, "category": fb.category, "action": fb.action,
                          "reply": fb.draft_after, "closed_at": record["ts"], "review_seconds": fb.review_seconds})
        write_archive(items)
    return {"ok": True}


@router.get("/api/archive")
def api_archive() -> dict:
    """Завершённые обращения. Старше 30 дней попадают в список на удаление: решает админ.

    Эскалация не считается окончательным ответом: игрок ещё ждёт человека, удалять нечего.
    """
    now = time.time()
    items = [{**x, "age_days": int((now - x["closed_at"]) // 86400), "deletable": x["action"] != "escalate"}
             for x in read_archive()]
    return {"items": items, "retention_days": RETENTION_DAYS,
            "to_delete": [x["ticket_id"] for x in items if x["deletable"] and x["age_days"] >= RETENTION_DAYS]}


@router.delete("/api/archive/{ticket_id}")
def api_archive_delete(ticket_id: str) -> dict:
    items = read_archive()
    item = next((x for x in items if x["ticket_id"] == ticket_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="в архиве такого обращения нет")
    if item["action"] == "escalate":
        raise HTTPException(status_code=409, detail="обращение передано человеку, ответа ещё нет")
    write_archive([x for x in items if x["ticket_id"] != ticket_id])
    DELETED_PATH.write_text(json.dumps([*read_deleted(), ticket_id], ensure_ascii=False), encoding="utf-8")
    return {"ok": True}


class Note(BaseModel):
    nick: str = Field(min_length=3, max_length=40)
    category: str
    status: str
    comment: str = Field(default="", max_length=500)


@router.post("/api/notes")
def api_add_note(note: Note) -> dict:
    data = note.model_dump()
    return reputation.add_note({**data, "lookup": reputation.lookup(data["nick"], data["category"])})


@router.delete("/api/notes/{note_id}")
def api_delete_note(note_id: int) -> dict:
    reputation.delete_note(note_id)
    return {"ok": True}


@router.get("/api/stats")
def api_stats() -> dict:
    """Сводка по действиям: сколько черновиков приняли без правок — главный сигнал качества."""
    if not FEEDBACK_PATH.exists():
        return {"total": 0, "sent": 0, "edited": 0, "escalated": 0}
    rows = [json.loads(line) for line in open(FEEDBACK_PATH, encoding="utf-8")]
    sent = [r for r in rows if r["action"] == "send"]
    return {"total": len(rows), "sent": len(sent), "edited": sum(r["edited"] for r in sent),
            "escalated": sum(r["action"] == "escalate" for r in rows)}
