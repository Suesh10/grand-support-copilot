"""Интерфейс админа (бонус ТЗ): очередь, черновик, «отправить / править / эскалировать».

Действия админа и правки черновиков пишутся в feedback.jsonl: это обучающий
сигнал для будущих версий шаблонов и модели.
"""

import json
import os
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import config, llm, reputation
from .normalize import normalize
from .pipeline import triage_full
from .predict import open_any, ticket_to_request
from .rules import load_points

router = APIRouter()

STATIC = Path(__file__).parent / "static"
QUEUE_PATH = os.getenv("COPILOT_QUEUE", str(config.ROOT / "examples" / "sample_tickets.jsonl"))
FEEDBACK_PATH = config.ARTIFACTS_DIR / "feedback.jsonl"
PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
GENERATE_VERDICTS = {"approved", "need_evidence", "rejected", "invalid_format", "duplicate"}


def punishments(ref: str) -> list[str]:
    """Варианты наказания из текста пункта правил: всё после «|» вида «Нарушение: MUTE…»."""
    point = load_points().get(ref)
    if not point:
        return []
    parts = [p.strip(" .") for p in point.text.split("|")[1:]]
    return [p for p in parts if ":" in p and len(p) < 90][:4]


def rule_card(ref: str) -> dict | None:
    point = load_points().get(ref)
    if not point:
        return None
    return {"ref": ref, "section": point.section_title, "text": point.text.split("|")[0].strip()[:220],
            "punishments": punishments(ref)}


@lru_cache(maxsize=1)
def raw_tickets() -> tuple:
    return tuple(json.loads(line) for line in open_any(QUEUE_PATH) if line.strip())


@lru_cache(maxsize=1)
def load_queue() -> tuple:
    tickets = raw_tickets()
    series = Counter(t.get("reported_nick") for t in tickets if t.get("reported_nick"))
    items = []
    for t in tickets:
        request = ticket_to_request(t)
        pred, meta = triage_full(request)
        refs = meta["cited_full"] or meta["rule_refs_full"]
        items.append({
            "id": t.get("ticket_id"),
            "kind": t.get("kind"),
            "messages": [{**m, "text": normalize(m.get("text", ""))} for m in request["messages"]],
            "images": t.get("images_count") or 0,
            "region": t.get("region"),
            "triage": pred,
            "rules": [c for c in (rule_card(r) for r in refs) if c],
            "series": series.get(t.get("reported_nick"), 1),
            "reporter_hash": t.get("reporter_hash"),
            "reported_hash": t.get("reported_hash"),
            "auto": not pred["needs_human"],
        })
    items.sort(key=lambda x: (PRIORITY_ORDER.get(x["triage"]["priority"], 9), not x["triage"]["needs_human"]))
    return tuple(items)


class Feedback(BaseModel):
    ticket_id: str
    action: str  # send | edit | escalate | undo | merge
    draft_before: str = ""
    draft_after: str = ""
    category: str = ""  # вид обращения: админ мог поменять то, что определил ИИ
    ai_category: str = ""
    priority: str = ""
    reported_hash: str | None = None


@router.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(STATIC / "admin.html")


@router.get("/api/queue")
def api_queue() -> dict:
    # Профили считаем при каждом запросе: они меняются от решений админа.
    items = [{**x, "profiles": {"reporter": reputation.profile(x["reporter_hash"]),
                                "reported": reputation.profile(x["reported_hash"])}} for x in load_queue()]
    return {"items": items, "llm": llm.enabled(), "notes": reputation.read_notes()}


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
    with open(FEEDBACK_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    if fb.action == "send" and fb.category.startswith("complaint."):
        reputation.remember(fb.reported_hash, fb.category)
    return {"ok": True}


class Note(BaseModel):
    nick: str = Field(min_length=3, max_length=40)
    category: str
    status: str
    comment: str = Field(default="", max_length=500)


@router.post("/api/notes")
def api_add_note(note: Note) -> dict:
    return reputation.add_note(note.model_dump())


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
