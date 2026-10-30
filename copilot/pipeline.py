"""Главная функция: обращение → ответ по контракту POST /triage."""

from . import classify as clf
from . import guard, model, retrieve
from .draft import offline_draft, retrieval_draft
from .extract import extract
from .labels import REF_CATEGORY
from .normalize import detect_lang, normalize
from .rules import filter_valid

ALWAYS_TEMPLATE = {"report.account", "report.payment"}


def relevant_refs(category: str, facts: dict) -> set[str]:
    """Пункты, которые уместно цитировать для этой категории и этого обращения."""
    refs = {r for r, c in REF_CATEGORY.items() if c == category}
    refs |= set(facts["rule_refs"])
    if category == "complaint.invalid":
        refs |= {"1.2.7 ЖБ", "1.1.2 ЖБ"}
    if category == "report.offtopic":
        refs.add("3.1 ОП")
    return refs


def likely_verdict(kind: str, category: str, text: str, rule_refs_raw: str) -> str | None:
    if kind != "complaint":
        return None
    pred = model.predict("verdict", text, rule_refs_raw)
    verdict = pred[0] if pred else None
    if category == "complaint.admin" and verdict not in ("appeal_approved", "appeal_rejected"):
        return "appeal_rejected"
    if category == "complaint.invalid" and verdict not in ("invalid_format", "need_evidence"):
        return "need_evidence"
    return verdict


def player_text(messages: list[dict]) -> str:
    """Текст заявителя и обвиняемого, без ответов админа."""
    return " \n".join(normalize(m.get("text", "")) for m in messages if m.get("role") != "admin")


def triage(request: dict) -> dict:
    kind = request.get("kind", "report")
    messages = request.get("messages", [])
    text = player_text(messages)
    attachments = sum(int(m.get("attachments") or 0) for m in messages)
    first_player = next((normalize(m.get("text", "")) for m in messages if m.get("role", "player") == "player"), text)

    rule_refs_raw = request.get("rule_refs_raw") or ""
    lang = detect_lang(first_player)
    facts = extract(text, attachments, rule_refs_raw)
    if not facts["nickname"] and request.get("reported_nick"):
        facts["nickname"] = request["reported_nick"]
    category, priority, confidence = clf.classify(kind, text, facts["has_evidence"], rule_refs_raw)
    is_spam = kind == "report" and clf.is_empty(text)

    reasons = guard.check(category, text)
    needs_human = bool(reasons)

    draft = None
    if kind == "report" and category not in ALWAYS_TEMPLATE and lang in ("ru", "und"):
        template = retrieve.report_template(category)
        if template:
            draft = {"lang": "ru", "text": template, "cited": []}
    if draft is None and category not in ALWAYS_TEMPLATE:
        verdict = likely_verdict(kind, category, text, rule_refs_raw)
        draft = retrieval_draft(kind, text, lang, verdict, facts["nickname"], relevant_refs(category, facts))
    if draft is None:
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
