"""Интерфейс админа (бонус ТЗ): очередь, черновик, «отправить / править / эскалировать».

Действия админа и правки черновиков пишутся в feedback.jsonl: это обучающий
сигнал для будущих версий шаблонов и модели.
"""

import hashlib
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

from . import clusters, config, dedupe, learn, llm, reputation, retrieve
from .draft import handoff_draft
from .extract import spans
from .normalize import normalize
from .pipeline import player_text, triage_full
from .predict import open_any, ticket_to_request
from .rules import load_points, punishments

router = APIRouter()

STATIC = Path(__file__).parent / "static"
QUEUE_PATH = os.getenv("COPILOT_QUEUE", str(config.ROOT / "examples" / "sample_tickets.jsonl"))
FEEDBACK_PATH = config.ARTIFACTS_DIR / "feedback.jsonl"
ARCHIVE_PATH = config.ARTIFACTS_DIR / "archive.json"
DELETED_PATH = config.ARTIFACTS_DIR / "deleted_tickets.json"
DECISIONS_PATH = config.ARTIFACTS_DIR / "template_decisions.json"
REVIEW_PATH = config.ROOT / "data" / "gold" / "drafts_review.jsonl"
SCORES_PATH = config.ROOT / "data" / "gold" / "drafts_scores.jsonl"
RETENTION_DAYS = 30  # через сколько дней сайт предлагает удалить, но сам не удаляет
PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
_queue_lock = threading.Lock()  # страница и фоновый прогрев не должны считать очередь дважды
_files_lock = threading.Lock()  # два быстрых действия админа не должны затирать друг друга
GENERATE_VERDICTS = {"approved", "need_evidence", "rejected", "invalid_format", "duplicate", "appeal_rejected"}


def rule_card(ref: str) -> dict | None:
    point = load_points().get(ref)
    if not point:
        return None
    return {"ref": ref, "section": point.section_title, "text": point.text.split("|")[0].strip()[:220],
            "punishments": punishments(ref)}


def appeal_from(t: dict) -> dict | None:
    """Ответ обвиняемого в жалобе идёт отдельным обращением во вкладку апелляций."""
    replies = [m for m in t.get("messages") or [] if m.get("role") == "reported_player"]
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
    learn.activate()
    tickets = raw_tickets()
    series = Counter(t.get("reported_nick") for t in tickets if t.get("reported_nick") and not t.get("appeal_of"))
    items = []
    deduper = dedupe.Deduper()
    for t in tickets:
        request = ticket_to_request(t)
        request["is_duplicate"] = not t.get("appeal_of") and deduper.is_duplicate(t)
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
            "duplicate": request["is_duplicate"],
            "shows": t.get("shows"),  # только у демо-примеров: какую функцию показывает обращение
            "kind": t.get("kind"),
            "messages": [{**m, "text": normalize(m["text"]), "spans": spans(normalize(m["text"]))} for m in request["messages"]],
            "history": retrieve.history(player_text(request["messages"])) if t.get("kind") == "complaint" else None,
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


def reports() -> list[tuple]:
    """Отчёты make eval с прогнозом: сначала замеры с LLM, внутри них самые свежие."""
    found = []
    for path in config.ARTIFACTS_DIR.glob("report*.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("gold") and report.get("proposals"):
            found.append((bool(report.get("llm_model")), path.stat().st_mtime, report))
    return sorted(found, key=lambda x: x[:2], reverse=True)


def proposal_accuracy() -> dict:
    """Точность прогноза из последнего отчёта: интерфейс показывает измеренное, а не зашитое."""
    for _, _, report in reports():
        return {verdict: row["precision"] for verdict, row in report["proposals"]["by_outcome"].items() if row["checked"] >= 10}
    return {}


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
    items = [{**x, "profiles": {"reporter": reputation.mini_profile(x["reporter_hash"]),
                                "reported": reputation.mini_profile(x["reported_hash"])}}
             for x in load_queue() if x["id"] not in closed]
    return {"items": items, "llm": llm.status(), "notes": reputation.read_notes(), "proposal_accuracy": proposal_accuracy()}


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


def refreshed(skip: set) -> list[dict]:
    """Обращения очереди, которые изменил новый урок: админ сразу видит, что сервис учится."""
    updated = []
    for t in raw_tickets():
        if t.get("ticket_id") in skip or t.get("appeal_of"):
            continue
        pred, meta = triage_full(ticket_to_request(t))
        if meta["draft_source"] == "lesson":
            updated.append({"id": t.get("ticket_id"), "draft": pred["draft_reply"]["text"]})
    return updated


def relearn(fb: Feedback, closed: set) -> list[dict]:
    ticket = next((t for t in raw_tickets() if t.get("ticket_id") == fb.ticket_id), None)
    if ticket is None or not fb.category:
        return []
    item = next((x for x in load_queue() if x["id"] == fb.ticket_id), None)
    lang = item["triage"]["lang"] if item else "ru"
    learn.add(fb.ticket_id, player_text(ticket_to_request(ticket)["messages"]), fb.draft_after, fb.category, lang, fb.nick)
    return refreshed(closed | {fb.ticket_id})


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
    if fb.action == "undo":
        learn.remove(fb.ticket_id)
    if fb.action == "send" and record["edited"]:
        return {"ok": True, "learned": relearn(fb, {x["ticket_id"] for x in items})}
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


def read_decisions() -> dict:
    return json.loads(DECISIONS_PATH.read_text(encoding="utf-8")) if DECISIONS_PATH.exists() else {}


@router.get("/api/templates")
def api_templates() -> dict:
    """Предложенные шаблоны по кластерам обращений, если они построены (make train)."""
    path = clusters.CANDIDATES_PATH
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    decisions = read_decisions()
    return {"items": [{**x, "decision": decisions.get(str(x["id"]))} for x in items if decisions.get(str(x["id"])) != "rejected"]}


class TemplateDecision(BaseModel):
    decision: Literal["accepted", "rejected"]


@router.post("/api/templates/{template_id}")
def api_template_decision(template_id: int, body: TemplateDecision) -> dict:
    """Принятый шаблон становится уроком: дальше он идёт теми же проверками, что и правка админа."""
    path = clusters.CANDIDATES_PATH
    items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    item = next((x for x in items if x["id"] == template_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="такого шаблона нет")
    with _files_lock:
        decisions = {**read_decisions(), str(template_id): body.decision}
        DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DECISIONS_PATH.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
    if body.decision == "rejected":
        return {"ok": True, "learned": []}
    load_queue()
    learn.add(f"template-{template_id}", " ".join(item["terms"]), item["reply"], item["category"], item["lang"], None)
    return {"ok": True, "learned": refreshed({x["ticket_id"] for x in read_archive()})}


def read_scores() -> list[dict]:
    return [json.loads(line) for line in open(SCORES_PATH, encoding="utf-8")] if SCORES_PATH.exists() else []


def score_summary(scores: list[dict], review: list[dict]) -> dict:
    # Набор черновиков пересобирается: оценки старых версий к нынешним ответам не относятся.
    langs = {r["ticket_id"]: r["lang"] for r in review}
    scores = [x for x in scores if x["ticket_id"] in langs]
    mean = lambda rows, key: round(sum(r[key] for r in rows) / len(rows), 2) if rows else None  # noqa: E731
    by_lang = {}
    for lang in sorted(set(langs.values())):
        rows = [s for s in scores if langs.get(s["ticket_id"]) == lang]
        if rows:
            by_lang[lang] = {"n": len(rows), "draft": mean(rows, "draft_score"), "admin": mean(rows, "admin_score")}
    return {"n": len(scores), "draft": mean(scores, "draft_score"), "admin": mean(scores, "admin_score"), "by_lang": by_lang}


@router.get("/api/review")
def api_review() -> dict:
    """Слепая оценка: два ответа в случайном порядке, какой из них написал сервис, видно только после оценки."""
    if not REVIEW_PATH.exists():
        return {"available": False}
    review = [json.loads(line) for line in open(REVIEW_PATH, encoding="utf-8") if line.strip()]
    scores = read_scores()
    done = {s["ticket_id"] for s in scores}
    left = [r for r in review if r["ticket_id"] not in done]
    item = None
    if left:
        r = left[0]
        draft_first = hash_flip(r["ticket_id"])
        item = {"ticket_id": r["ticket_id"], "lang": r["lang"], "player": r["player"],
                "a": r["draft"] if draft_first else r["admin"], "b": r["admin"] if draft_first else r["draft"]}
    return {"available": True, "total": len(review), "done": len(done & {r["ticket_id"] for r in review}),
            "item": item, "summary": score_summary(scores, review)}


def hash_flip(ticket_id: str) -> bool:
    return hashlib.sha256(ticket_id.encode("utf-8")).digest()[0] % 2 == 0


class ReviewScore(BaseModel):
    ticket_id: str
    a: int = Field(ge=1, le=5)
    b: int = Field(ge=1, le=5)
    rater: str = ""


@router.post("/api/review")
def api_review_score(body: ReviewScore) -> dict:
    draft_first = hash_flip(body.ticket_id)
    row = {"ticket_id": body.ticket_id, "draft_score": body.a if draft_first else body.b,
           "admin_score": body.b if draft_first else body.a, "rater": body.rater, "ts": int(time.time())}
    with _files_lock:
        SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SCORES_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True, "draft_was": "a" if draft_first else "b"}


def latest_report() -> dict | None:
    """Последние измеренные цифры сервиса с датой: панель показывает их, а не значения из кода."""
    for _, measured_at, report in reports():
        cost, latency = report.get("cost") or {}, report.get("latency") or {}
        return {"measured_at": int(measured_at), "llm": bool(report.get("llm_model")),
                "category_accuracy": report["gold"]["category_accuracy"], "priority_macro_f1": report["gold"]["priority_macro_f1"],
                "citations": report["hallucinations"]["citations_total"], "citations_invalid": report["hallucinations"]["citations_not_in_rules_json"],
                "needs_human": report["shares"]["needs_human"], "usd_per_ticket": cost.get("usd_per_ticket_blended"),
                "p95_s": (latency.get("with_llm_sample") or latency.get("offline") or {}).get("p95_s")}
    return None


@router.get("/api/stats")
def api_stats() -> dict:
    """Смена в цифрах. Итог берём из архива: отменённые действия в него не попадают."""
    rows = [json.loads(line) for line in open(FEEDBACK_PATH, encoding="utf-8")] if FEEDBACK_PATH.exists() else []
    edited = {r["ticket_id"]: r["edited"] for r in rows if r["action"] == "send"}
    closed = read_archive()
    deleted = set(read_deleted())
    sent = [x for x in closed if x["action"] == "send"]
    times = sorted(x["review_seconds"] for x in closed if x.get("review_seconds") is not None)
    open_items = [x for x in load_queue() if x["id"] not in {c["ticket_id"] for c in closed} and x["id"] not in deleted]
    return {
        "total": len(closed), "sent": len(sent), "edited": sum(edited.get(x["ticket_id"], False) for x in sent),
        "escalated": sum(x["action"] == "escalate" for x in closed), "merged": sum(x["action"] == "merge" for x in closed),
        "median_seconds": times[len(times) // 2] if times else None,
        "by_category": Counter(x["category"] for x in closed if x["category"]).most_common(),
        "open_by_priority": sorted(Counter(x["triage"]["priority"] for x in open_items if not x["auto"]).items()),
        "open_by_category": Counter(x["triage"]["category"] for x in open_items if not x["auto"]).most_common(),
        "auto": sum(x["auto"] for x in open_items), "lessons": len(learn.lessons()),
        "report": latest_report(), "llm": llm.status(),
    }
