"""Главная функция: обращение → ответ по контракту POST /triage."""

import logging
import re

from . import classify as clf
from . import guard, llm, model, rag, retrieve, templates
from .draft import (INVENTED_FACT_RE, adapt_reply, handoff_draft, offline_draft, proposal_draft, retrieval_draft,
                    strip_foreign_details)
from .extract import extract
from .normalize import detect_lang, normalize
from .rules import filter_valid, short_ref

ALWAYS_TEMPLATE = {"report.account", "report.payment"}


log = logging.getLogger(__name__)
REPLY_LANGS = {"kk", "uz", "en", "es", "pt"}
UNDER_REVIEW = "under_review"
# С какой уверенности исход можно предложить админу. Подобрано на валидации: одна планка на всех пропускала
# «оформлена неверно» с точностью около 30% и выбрасывала «одобрено» с точностью 85%. Остальные исходы
# модель угадывает плохо, поэтому сама их не предлагает, их выбирает админ.
PROPOSE_FROM = {"approved": 0.4, "need_evidence": 0.6, "appeal_rejected": 0.6}
# Голосование похожих случаев видит то, чего не видит модель по тексту: при таком большинстве оно верно в 80% и выше.
# Для апелляций не работает: там точность 62%, поэтому их предлагает только модель.
HISTORY_FROM = {"approved": 0.7, "need_evidence": 0.7}
PROPOSAL_REASON = "исход предложен моделью, вложений она не видит: проверьте доказательства"
EMPTY_COMPLAINT = 15  # символов: короче этого в жалобе нет описания
LOW_CONFIDENCE = 0.5  # на ручной разметке ниже этой уверенности категория верна меньше чем в половине случаев
CITATION_LINE = {"ru": "Основание: пункт {ref}.", "kk": "Негіз: {ref} тармағы.", "uz": "Asos: {ref} bandi.",
                 "en": "Reference: rule {ref}.", "es": "Referencia: regla {ref}.", "pt": "Referência: regra {ref}."}
CLOSED_RE = re.compile(r"\s*(жалоба\s+)?закрыт[оа]\b[.!]?|\s*yopildi\b[.!]?", re.I)
SIGNATURE_RE = re.compile(r"(с уважением|hurmat bilan|құрметпен)", re.I)


def with_citation(draft: dict, refs: list[str]) -> dict:
    """Дописать обязательные цитаты: ТЗ не допускает ответ без цитаты, где правила нужны."""
    missing = [r for r in refs if r not in draft["cited"]]
    if not missing:
        return draft
    line = CITATION_LINE.get(draft["lang"], CITATION_LINE["ru"]).format(ref=", ".join(missing))
    text = draft["text"].rstrip()
    sign = SIGNATURE_RE.search(text)
    text = f"{text[:sign.start()].rstrip()} {line}\n{text[sign.start():].lstrip()}" if sign else f"{text} {line}"
    return {**draft, "text": text, "cited": [*draft["cited"], *missing]}


def likely_verdict(kind: str, category: str, text: str, rule_refs_raw: str, has_evidence: bool = False) -> str | None:
    if kind != "complaint":
        return None
    pred = model.predict("verdict", text, rule_refs_raw)
    verdict, confidence = pred if pred else (None, 0.0)
    # Дубль и «уже наказан» определяются по фактам, а не угадываются по тексту.
    if verdict in ("duplicate", "already_punished"):
        verdict = None
    if category == "complaint.admin":
        return verdict if verdict == "appeal_rejected" and confidence >= PROPOSE_FROM[verdict] else UNDER_REVIEW
    if not has_evidence:
        return "invalid_format" if category == "complaint.invalid" and verdict == "invalid_format" else "need_evidence"
    # Пустая жалоба («жб», «вот он») не оформлена, сколько бы вложений ни было.
    if category == "complaint.invalid" and len(text) < EMPTY_COMPLAINT:
        return "invalid_format"
    if confidence >= PROPOSE_FROM.get(verdict, 2.0):
        return verdict
    history = retrieve.history(text)
    if history:
        top, count = history["outcomes"][0]
        if count / history["n"] >= HISTORY_FROM.get(top, 2.0):
            return top
    # Вложений сервис не видит: без уверенности не утверждаем исход, а говорим, что жалоба на проверке.
    return UNDER_REVIEW


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
    lang = detect_lang(first_player, request.get("server_lang"))
    facts = extract(text, attachments, rule_refs_raw)
    if not facts["nickname"] and request.get("reported_nick"):
        facts["nickname"] = request["reported_nick"]
    category, priority, confidence = clf.classify(kind, text, facts["has_evidence"], rule_refs_raw)
    is_duplicate = bool(request.get("is_duplicate"))
    is_spam = is_duplicate or clf.is_empty(text) or category == "report.offtopic"
    if is_duplicate and kind == "complaint" and not verdict_override:
        verdict_override = "duplicate"

    reasons = guard.check(category, text)
    if confidence < LOW_CONFIDENCE and category != "report.offtopic":
        reasons.append("сервис не уверен в категории")
    needs_human = bool(reasons)

    meta = {"draft_source": None, "is_duplicate": is_duplicate}
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

    verdict = verdict_override or likely_verdict(kind, category, text, rule_refs_raw, facts["has_evidence"])
    known_verdict = None if verdict == UNDER_REVIEW else verdict
    # Прогноз модели, а не решение админа и не факт вроде «доказательств нет совсем».
    proposed = not verdict_override and facts["has_evidence"] and verdict in PROPOSE_FROM
    refs = rag.candidates(category, verdict, text, facts["rule_refs"])
    allowed = set(refs)
    if draft is None and llm.enabled():
        examples = templates.style_examples(lang, kind, verdict) + [
            adapt_reply(c["reply"], c.get("reported_nick"), facts["nickname"])
            for c in retrieve.similar(kind, text, k=3, verdict=known_verdict, lang=lang)]
        result = llm.draft(kind, lang if lang in llm.LANG_NAMES else "ru", category, verdict, text,
                           facts["nickname"], refs, examples, decided=bool(verdict_override),
                           proposed=proposed)
        if result and "_error" not in result:
            meta.update(result.pop("_meta"), draft_source="llm")
            if result.pop("needs_human"):
                needs_human = True
            reasons += [r for r in result.pop("reasons") if r not in reasons]
            draft = result
            # Фильтр выдуманных фактов действует и на LLM: он тоже копирует их из примеров.
            if INVENTED_FACT_RE.search(draft["text"]) and verdict not in ("duplicate", "appeal_rejected"):
                draft, meta["draft_source"] = handoff_draft(lang), "handoff"
                needs_human = True
        elif result:
            meta["llm_error"] = result["_error"]
    # Без LLM жалоба всё равно получает ответ по существу: близкий ответ админа или предложение решения.
    if draft is None and kind == "complaint":
        # Просьбу о доказательствах админы пишут разнообразно, а одобрение ближе всего к шаблону: замерено на валидации.
        if lang == "ru" and verdict == "need_evidence":
            draft = retrieval_draft(kind, text, lang, verdict, facts["nickname"], allowed)
            meta["draft_source"] = "retrieval" if draft else None
        if draft is None:
            draft = proposal_draft(lang, category, verdict, facts["nickname"], refs, text)
            meta["draft_source"] = "proposal" if draft else None
    # Офлайн на kk/uz: шаблон по вероятному исходу лучше, чем чужой русский ответ.
    if draft is None and lang in templates.BY_LANG:
        situation = "senior" if category in guard.ALWAYS_HUMAN else templates.VERDICT_SITUATION.get(verdict or "")
        template = templates.get(lang, situation) if situation else None
        if template:
            draft, meta["draft_source"] = {"lang": lang, "text": template, "cited": []}, "template"
    # Запасной путь: языка нет в таблице предложений, но решать за админа мы всё равно не будем.
    if draft is None and (category == "complaint.admin" or verdict == UNDER_REVIEW):
        draft, meta["draft_source"] = handoff_draft(lang), "handoff"
    if draft is None and category not in ALWAYS_TEMPLATE:
        draft = retrieval_draft(kind, text, lang, verdict, facts["nickname"], allowed)
        meta["draft_source"] = "retrieval" if draft else None
    if draft is None:
        draft = offline_draft(lang, category, facts["rule_refs"], facts["has_evidence"], needs_human)
        meta["draft_source"] = "template"
    # Не отвечаем игроку на чужом языке: без подходящего текста передаём человеку на языке игрока.
    if lang in REPLY_LANGS and draft["lang"] != lang:
        draft = handoff_draft(lang)
        meta["draft_source"] = "handoff"
        needs_human = True
        reasons.append("нет шаблона на языке игрока")
    draft["text"] = strip_foreign_details(draft["text"])
    # Последний барьер: в ответ попадают только существующие пункты правил.
    draft["cited"] = filter_valid(draft["cited"])
    # Черновик без решения о наказании (просьба о доказательствах и т.п.) не требует админа.
    # Вложений сервис не видит: приложенные доказательства оценивает только человек.
    cannot_judge_evidence = kind == "complaint" and facts["has_evidence"] and verdict != "duplicate"
    if (kind == "complaint" and verdict in guard.NO_DECISION_VERDICTS and reasons == [guard.PUNISH_REASON]
            and meta["draft_source"] != "llm" and not cannot_judge_evidence):
        reasons, needs_human = [], False
    if cannot_judge_evidence and not needs_human:
        needs_human, reasons = True, ["вложения не видны сервису, доказательства оценивает администратор"]
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
    # Пока решает человек, обращение не закрыто.
    if needs_human:
        draft = {**draft, "text": CLOSED_RE.sub("", draft["text"]).strip()}
    if category in rag.NEEDS_CITATION:
        draft = with_citation(draft, rag.required(category, verdict, refs, draft["cited"]))
    # Предложение решения админ проверяет всегда, даже если остальным проверкам оно не интересно.
    if proposed and meta["draft_source"] != "handoff":
        needs_human = True
        reasons.append(PROPOSAL_REASON)
        meta["proposal"] = verdict

    # Внутри пункт однозначен («2.1 ОП»), наружу по контракту идёт points[].ref из rules.json («2.1»).
    meta["cited_full"], meta["rule_refs_full"] = draft["cited"], facts["rule_refs"]
    result = {
        "lang": lang,
        "category": category,
        "priority": priority,
        "is_spam_or_duplicate": is_spam,
        "extracted": {**facts, "rule_refs": list(dict.fromkeys(short_ref(r) for r in facts["rule_refs"]))},
        "draft_reply": {**draft, "cited": list(dict.fromkeys(short_ref(r) for r in draft["cited"]))},
        "needs_human": needs_human,
        "confidence": round(confidence, 2),
        "reasons": reasons,
    }
    return result, meta


def fallback(request: dict) -> dict:
    """Ответ по контракту при сбое: одно обращение не должно ронять весь прогон."""
    kind = "complaint" if isinstance(request, dict) and request.get("kind") == "complaint" else "report"
    return {
        "lang": "und",
        "category": "complaint.other" if kind == "complaint" else "report.question",
        "priority": "p2",
        "is_spam_or_duplicate": False,
        "extracted": {"nickname": None, "rule_refs": [], "has_evidence": False, "server": None},
        "draft_reply": handoff_draft("ru"),
        "needs_human": True,
        "confidence": 0.0,
        "reasons": ["сбой обработки, обращение передано человеку"],
    }


def triage(request: dict) -> dict:
    """Ответ строго по контракту POST /triage."""
    try:
        return triage_full(request)[0]
    except Exception:
        log.exception("сбой обработки обращения")
        return fallback(request)
