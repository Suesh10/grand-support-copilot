"""Черновик ответа.

Офлайн-режим (без ключа LLM): ответ админа на самый похожий прошлый случай
с тем же видом и вероятным исходом, с подставленными именами. Если индекса
нет — шаблон по категории. Цитаты в любом случае проверяются по rules.json.
"""

import re

from . import retrieve, templates
from .labels import REF_CATEGORY
from .normalize import detect_lang
from .rules import filter_valid, load_points, parse_refs, punishments

NICK_RE = re.compile(r"\b[A-Z][a-z]+_[A-Z][a-z]+\d{0,3}\b")
PLAYER_WORD = {"hurmatli": "o‘yinchi", "құрметті": "ойыншы"}
GREETING_NAME_RE = re.compile(r"(уважаем(?:ый|ая)|hurmatli|құрметті)\s*(,?)\s*(?:игрок)?\s*([,.!]|\n)", re.I)


# Чужой ответ утверждает факты, которых по новому обращению мы не знаем.
INVENTED_FACT_RE = re.compile(r"предоставил\w* доказательств|уже (был\w* )?наказан|наказание (вам )?(было )?выдано верно|"
                              r"уже получил|дубликат|ранее рассмотрен", re.I)
PUNISH_TERM_RE = re.compile(r"\b\d+\s*(минут|мин\b|час|дн|день|дня|дней|kun|daqiqa|күн)", re.I)
COMPLAINT_RULES_RE = re.compile(r"подач\w+ жалоб|ппж", re.I)
RAW_NUMBER_RE = re.compile(r"\b\d\.\d")
SERVER_RE = re.compile(r"(администрация)\s+\d+\s+сервера", re.I)
BRAND_SERVER_RE = re.compile(r"(grand\s?mobile)\s+\d{1,3}\b", re.I)
MIN_REPLY = 45  # короче админы пишут наспех, без знаков препинания: такой ответ хуже нашего шаблона
SENIOR_RE = re.compile(r"старш(?:ей|ую|ая)\s+администраци|старшему\s+администратору", re.I)


def strip_foreign_details(text: str) -> str:
    """Подпись конкретного сервера из чужого ответа: номера сервера нашего обращения мы не знаем."""
    text = BRAND_SERVER_RE.sub(r"\1", SERVER_RE.sub(r"\1", text))
    # Структуру админов мы не знаем: не обещаем передачу конкретной должности.
    return SENIOR_RE.sub(lambda m: "администраци" if "администраци" in m.group(0) else "администрации", text)


RELATIVES_RE = re.compile(r"родн|сем[ьеи]|мать|мам[уаы]|отц|ona\w*|onadan|ана\w*", re.I)
# Если в пункте несколько нарушений, а игрок не уточнил, какое из них подразумевается по категории.
DEFAULT_PUNISHMENT = {"5.2 ОП": "стороннего ПО"}


def pick_punishment(ref: str, text: str) -> str | None:
    """Наказание дословно из пункта правил: срок мы не придумываем, а цитируем."""
    lines = punishments(ref)
    if not lines:
        return None
    # Если упомянуты родные, админы в 61% случаев блокируют персонажа: это последняя, самая строгая строка о них.
    about_relatives = [line for line in lines if "родн" in line.partition(":")[0].lower()]
    if about_relatives and RELATIVES_RE.search(text):
        return about_relatives[-1].partition(":")[2].strip()
    known = DEFAULT_PUNISHMENT.get(ref)
    line = next((x for x in lines if known and known in x.partition(":")[0]), None)
    line = line or next((x for x in lines if x not in about_relatives), lines[0])
    return line.partition(":")[2].strip()


def term_is_quoted(text: str, refs: list[str]) -> bool:
    """Срок наказания в черновике есть в тексте цитируемых пунктов: придуманный срок хуже, чем никакого."""
    points = load_points()
    rules = " ".join(points[r].text for r in refs if r in points)
    return all(m.group(0) in rules for m in PUNISH_TERM_RE.finditer(text))


def proposal_draft(lang: str, category: str, verdict: str | None, nick: str | None, refs: list[str], text: str) -> dict | None:
    """Черновик по существу: предложенное решение или «на проверке» с ником и пунктом."""
    lang = lang if lang in templates.PROPOSALS else "ru"
    table = templates.PROPOSALS[lang]
    appeal = category == "complaint.admin"
    key = "appeal_review" if appeal else "review"
    if verdict in ("approved", "need_evidence", "appeal_rejected", "duplicate"):
        key = verdict
    if key not in table or (verdict and verdict not in ("approved", "need_evidence", "appeal_rejected", "duplicate", "under_review")):
        return None
    topic = next((r for r in refs if REF_CATEGORY.get(r) == category or (category == "complaint.invalid" and r.endswith(" ЖБ"))), None)
    by = templates.BY_RULE[lang].format(ref=topic) if topic else ""
    named, anonymous = templates.WHO.get(lang, ("", ""))
    term = pick_punishment(topic, text) if topic and lang == "ru" else None
    filled = table[key].format(who=named.format(nick=nick) if nick else anonymous, by=by, term=f": {term}" if term else "",
                               on=templates.ON_NICK.get(lang, "").format(nick=nick) if nick else "")
    return {"lang": lang, "text": filled, "cited": [topic] if topic and "{by}" in table[key] else []}


def adapt_reply(reply: str, source_reported: str | None, target_reported: str | None) -> str:
    """Перенести ответ на новый случай: ник обвиняемого — на нового, остальные ники убрать."""
    def swap(m: re.Match) -> str:
        nick = m.group(0)
        if source_reported and nick == source_reported:
            return target_reported or "игрок"
        return ""

    text = NICK_RE.sub(swap, reply)
    text = re.sub(r"\s*(под\s+|№\s*)?#\s*<digits>(-raqamli|-sonli)?-?", " ", text)
    text = re.sub(r"<(url|email|handle|digits)>", "", text)
    text = GREETING_NAME_RE.sub(
        lambda m: f"{m.group(1)} {PLAYER_WORD.get(m.group(1).lower(), 'игрок')}{m.group(2)}{m.group(3)}", text)
    text = re.sub(r",([,.!])", r"\1", text)
    text = text.replace("Уважаемый(ая)", "Уважаемый игрок")
    text = re.sub(r"[ \t]+([,.!?])", r"\1", text)
    text = re.sub(r",\.", ".", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return strip_foreign_details(text).strip()


def retrieval_draft(kind: str, text: str, lang: str, verdict: str | None,
                    reported_nick: str | None, allowed_refs: set[str]) -> dict | None:
    """Ответ на самый похожий случай, где все упомянутые пункты относятся к нашему."""
    for case in retrieve.similar(kind, text, k=12, verdict=verdict, lang=lang):
        reply = adapt_reply(case["reply"], case.get("reported_nick"), reported_nick)
        # Срок наказания решает админ, длинные шаблоны админы тоже не любят.
        if INVENTED_FACT_RE.search(reply) or PUNISH_TERM_RE.search(reply) or not MIN_REPLY <= len(reply) <= 450:
            continue
        section = "ЖБ" if COMPLAINT_RULES_RE.search(reply) else "ОП"
        mentioned = parse_refs(reply, default_section=section)
        if any(r not in allowed_refs for r in mentioned) or (RAW_NUMBER_RE.search(reply) and not mentioned):
            continue
        # Язык берём по самому ответу: на казахские и английские обращения админы часто отвечали по-русски.
        reply_lang = detect_lang(reply)
        return {"lang": reply_lang if reply_lang != "und" else "ru", "text": reply, "cited": filter_valid(mentioned)}
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
        "human": "Здравствуйте! Ваше обращение передано администрации. Пожалуйста, ожидайте ответа.",
    },
}


HANDOFF = {
    "ru": "Здравствуйте! Ваше обращение передано администрации. Пожалуйста, ожидайте ответа.",
    "kk": templates.KK["senior"],
    "uz": templates.UZ["senior"],
    "en": "Hello! Your request has been forwarded to the administration. Please wait for a reply.",
    "es": "¡Hola! Su solicitud ha sido enviada a la administración. Por favor, espere la respuesta.",
    "pt": "Olá! Sua solicitação foi encaminhada à administração. Por favor, aguarde a resposta.",
}


def handoff_draft(lang: str) -> dict:
    """Нейтральная передача человеку: без решений, обещаний и цитат."""
    lang = lang if lang in HANDOFF else "ru"
    return {"lang": lang, "text": HANDOFF[lang], "cited": []}


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
