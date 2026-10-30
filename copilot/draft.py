"""Черновик ответа.

Офлайн-режим (без ключа LLM): ответ админа на самый похожий прошлый случай
с тем же видом и вероятным исходом, с подставленными именами. Если индекса
нет — шаблон по категории. Цитаты в любом случае проверяются по rules.json.
"""

import re

from . import retrieve
from .rules import filter_valid, load_points, parse_refs

NICK_RE = re.compile(r"\b[A-Z][a-z]+_[A-Z][a-z]+\d{0,3}\b")
GREETING_NAME_RE = re.compile(r"(уважаем(ый|ая)|hurmatli|құрметті)\s*,?\s*(игрок)?\s*([,.!]|\n)", re.I)


def adapt_reply(reply: str, source_reported: str | None, target_reported: str | None) -> str:
    """Перенести ответ на новый случай: ник обвиняемого — на нового, остальные ники убрать."""
    def swap(m: re.Match) -> str:
        nick = m.group(0)
        if source_reported and nick == source_reported:
            return target_reported or "игрок"
        return ""

    text = NICK_RE.sub(swap, reply)
    text = re.sub(r"\s*#\s*<digits>(-?\w*)?", "", text)
    text = re.sub(r"<(url|email|handle|digits)>", "", text)
    text = GREETING_NAME_RE.sub(lambda m: f"{m.group(1)} игрок{m.group(4)}", text)
    text = re.sub(r"[ \t]+([,.!?])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def retrieval_draft(kind: str, text: str, lang: str, verdict: str | None,
                    reported_nick: str | None, allowed_refs: set[str]) -> dict | None:
    """Ответ на самый похожий случай, где все упомянутые пункты относятся к нашему."""
    for case in retrieve.similar(kind, text, k=8, verdict=verdict, lang=lang):
        reply = adapt_reply(case["reply"], case.get("reported_nick"), reported_nick)
        mentioned = parse_refs(reply)
        if any(r not in allowed_refs for r in mentioned) or len(reply) < 8:
            continue
        reply_lang = case.get("lang") if case.get("lang") in ("ru", "kk", "uz", "en") else "ru"
        return {"lang": reply_lang, "text": reply, "cited": filter_valid(mentioned)}
    return None

TEMPLATES = {
    "ru": {
        "complaint_evidence": "Здравствуйте! Ваша жалоба принята и передана администратору на рассмотрение. "
                              "По вашему описанию это может относиться к пункту {refs}. Решение примет администратор после проверки доказательств.",
        "complaint_no_evidence": "Здравствуйте! Для рассмотрения жалобы нужны доказательства нарушения: скриншоты или видеозапись. "
                                 "Пожалуйста, оформите жалобу повторно и приложите их.",
        "invalid": "Здравствуйте! Жалоба оформлена неверно. Пожалуйста, ознакомьтесь с правилами подачи жалоб{refs_tail} и подайте её повторно.",
        "help": "Здравствуйте! Администратор уже видит ваше обращение и скоро поможет. Пожалуйста, ожидайте.",
        "question": "Здравствуйте! Ваш вопрос передан администратору, ответ придёт в ближайшее время.",
        "offtopic": "Здравствуйте! Опишите, пожалуйста, вашу проблему подробнее, чтобы администратор мог помочь.",
        "human": "Здравствуйте! Ваше обращение передано старшему администратору. Пожалуйста, ожидайте ответа.",
    },
}


def offline_draft(lang: str, category: str, refs: list[str], has_evidence: bool, needs_human: bool) -> dict:
    t = TEMPLATES.get(lang, TEMPLATES["ru"])
    reply_lang = lang if lang in TEMPLATES else "ru"
    cited = [r for r in refs if r in load_points()][:2]
    refs_text = ", ".join(cited)

    if category in ("report.account", "report.payment", "complaint.admin"):
        key = "human"
    elif category == "complaint.invalid":
        key = "invalid"
    elif category.startswith("complaint."):
        key = "complaint_evidence" if has_evidence and cited else "complaint_no_evidence"
    elif category == "report.help":
        key = "help"
    elif category == "report.offtopic":
        key = "offtopic"
    else:
        key = "question"

    if key not in ("complaint_evidence", "invalid"):
        cited = []
    text = t[key].format(refs=refs_text, refs_tail=f" ({refs_text})" if cited else "")
    return {"lang": reply_lang, "text": text, "cited": cited}
