"""Главная функция: обращение → ответ по контракту POST /triage."""

from . import classify as clf
from . import guard, llm, model, retrieve, templates
from .draft import adapt_reply, handoff_draft, offline_draft, retrieval_draft, strip_foreign_details
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


def triage_full(request: dict, verdict_override: str | None = None) -> tuple[dict, dict]:
    """Ответ по контракту + служебные данные (источник черновика, токены, стоимость, задержка).

    verdict_override: админ сам выбрал исход и просит черновик под него, шаблоны репортов не применяются.
    """
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

    meta = {"draft_source": None}
    draft = None
    # Типовые репорты на русском: частый ответ админов, без LLM и бесплатно.
    if kind == "report" and category not in ALWAYS_TEMPLATE and lang in ("ru", "und") and not verdict_override:
        template = retrieve.report_template(category)
        if template:
            draft, meta["draft_source"] = {"lang": "ru", "text": template, "cited": []}, "template"
    # Репорты на казахском и узбекском: шаблон носителя языка, тоже без LLM.
    if kind == "report" and lang in templates.BY_LANG and not verdict_override:
        template = templates.get(lang, templates.REPORT_SITUATION.get(category, "senior"))
        if template:
            draft, meta["draft_source"] = {"lang": lang, "text": template, "cited": []}, "template"

    verdict = verdict_override or likely_verdict(kind, category, text, rule_refs_raw)
    allowed = relevant_refs(category, facts)
    if draft is None and llm.enabled():
        refs = facts["rule_refs"] + sorted(r for r in allowed if r not in facts["rule_refs"])
        examples = templates.style_examples(lang, kind, verdict) + [
            adapt_reply(c["reply"], c.get("reported_nick"), facts["nickname"])
            for c in retrieve.similar(kind, text, k=3, verdict=verdict, lang=lang)]
        result = llm.draft(kind, lang if lang in llm.LANG_NAMES else "ru", category, verdict, text,
                           facts["nickname"], refs[:5], examples)
        if result and "_error" not in result:
            meta.update(result.pop("_meta"), draft_source="llm")
            if result.pop("needs_human"):
                needs_human = True
            reasons += [r for r in result.pop("reasons") if r not in reasons]
            draft = result
        elif result:
            meta["llm_error"] = result["_error"]
    # Офлайн на kk/uz: шаблон по вероятному исходу лучше, чем чужой русский ответ.
    if draft is None and lang in templates.BY_LANG:
        situation = "senior" if category in guard.ALWAYS_HUMAN else templates.VERDICT_SITUATION.get(verdict or "")
        template = templates.get(lang, situation) if situation else None
        if template:
            draft, meta["draft_source"] = {"lang": lang, "text": template, "cited": []}, "template"
    if draft is None and category not in ALWAYS_TEMPLATE:
        draft = retrieval_draft(kind, text, lang, verdict, facts["nickname"], allowed)
        meta["draft_source"] = "retrieval" if draft else None
    if draft is None:
        draft = offline_draft(lang, category, facts["rule_refs"], facts["has_evidence"], needs_human)
        meta["draft_source"] = "template"
    draft["text"] = strip_foreign_details(draft["text"])
    # Последний барьер: в ответ попадают только существующие пункты правил.
    draft["cited"] = filter_valid(draft["cited"])
    # Черновик без решения о наказании (просьба о доказательствах и т.п.) не требует админа.
    if (kind == "complaint" and verdict in guard.NO_DECISION_VERDICTS and reasons == [guard.PUNISH_REASON]
            and meta["draft_source"] != "llm"):
        reasons, needs_human = [], False
    if guard.has_forbidden_promise_hard(draft["text"]):
        # Разбан, снятие наказания, возврат — не обещаем никогда: заменяем нейтральной передачей человеку.
        draft = handoff_draft(draft["lang"])
        meta["draft_source"] = "handoff"
        needs_human = True
        reasons.append("черновик обещал разбан или возврат — заменён, решение за администратором")
    if guard.has_forbidden_promise(draft["text"]):
        needs_human = True
        reason = "черновик содержит решение, которое подтверждает только администратор"
        if reason not in reasons:
            reasons.append(reason)

    result = {
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
    return result, meta


def triage(request: dict) -> dict:
    """Ответ строго по контракту POST /triage."""
    return triage_full(request)[0]
