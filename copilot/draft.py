"""Черновик ответа.

Офлайн-режим (без ключа LLM): шаблон по категории + проверенные цитаты правил.
В блоке 3 сюда добавляется RAG (похожие ответы админов) и LLM.
"""

from .rules import load_points

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
