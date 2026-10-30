"""Главная функция: обращение → ответ по контракту POST /triage."""

from . import classify as clf
from . import guard
from .draft import offline_draft
from .extract import extract
from .normalize import detect_lang, normalize
from .rules import filter_valid


def player_text(messages: list[dict]) -> str:
    """Текст заявителя и обвиняемого, без ответов админа."""
    return " \n".join(normalize(m.get("text", "")) for m in messages if m.get("role") != "admin")


def triage(request: dict) -> dict:
    kind = request.get("kind", "report")
    messages = request.get("messages", [])
    text = player_text(messages)
    attachments = sum(int(m.get("attachments") or 0) for m in messages)
    first_player = next((normalize(m.get("text", "")) for m in messages if m.get("role", "player") == "player"), text)

    lang = detect_lang(first_player)
    facts = extract(text, attachments, request.get("rule_refs_raw", ""))
    category, priority, confidence = clf.classify(kind, text, facts["has_evidence"], request.get("rule_refs_raw") or "")
    is_spam = kind == "report" and clf.is_empty(text)

    reasons = guard.check(category, text)
    needs_human = bool(reasons)

    draft = offline_draft(lang, category, facts["rule_refs"], facts["has_evidence"], needs_human)
    # Последний барьер: в ответ попадают только существующие пункты правил.
    draft["cited"] = filter_valid(draft["cited"])
    if guard.has_forbidden_promise(draft["text"]):
        needs_human = True
        reasons.append("черновик содержит обещание, которое может дать только администратор")

    return {
        "lang": lang,
        "category": category,
        "priority": priority,
        "is_spam_or_duplicate": is_spam,
        "extracted": facts,
        "draft_reply": draft,
        "needs_human": needs_human,
        "confidence": round(confidence, 2),
        "reasons": reasons,
    }
