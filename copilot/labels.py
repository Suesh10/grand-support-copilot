"""Автоматическая (слабая) разметка обращений для обучения классификатора.

Категорий в выгрузке нет, но у жалоб есть исход из ответа админа: вердикт и
нарушение («2.1 ОП»). По ним категорию можно восстановить с хорошей точностью.
Источники по убыванию надёжности:
  1. вердикт-апелляция → жалоба на действия администрации;
  2. пункт нарушения из ответа админа → категория по карте пунктов;
  3. пункт, указанный игроком, и ключевые слова в тексте;
  4. вердикт «неверно оформлена» / «нужны доказательства» → complaint.invalid.
Тикеты без надёжного сигнала в обучение не попадают.
"""

import re

from .rules import parse_refs

# Пункт правил → категория (taxonomy.json + тексты пунктов rules.json).
REF_CATEGORY = {
    "2.1 ОП": "complaint.insult", "2.4 ОП": "complaint.insult", "2.6 ОП": "complaint.insult",
    "2.2 ОП": "complaint.insult", "2.5 ОП": "complaint.insult", "5.6 ОП": "complaint.insult",
    "1.6 ОП": "complaint.other", "5.7 ОП": "complaint.other", "5.8 ОП": "complaint.other",
    "5.2 ОП": "complaint.cheat",
    "5.3 ОП": "complaint.dm", "5.4 ОП": "complaint.dm", "5.4.1 ОП": "complaint.dm", "5.4.2 ОП": "complaint.dm",
    "5.1 ОП": "complaint.dm", "5.1.1 ОП": "complaint.dm", "5.5 ОП": "complaint.dm", "5.9 ОП": "complaint.dm",
    "4.1 ОП": "complaint.scam", "4.2 ОП": "complaint.scam",
    "2.3 ОП": "complaint.rmt_ads", "4.4 ОП": "complaint.rmt_ads",
    "3.2 ОП": "complaint.admin", "3.4 ОП": "complaint.admin",
}

RP_DM_RE = re.compile(r"\b(dm|дм|sk|ск|db|дб|tk|тк|nonrp|нонрп|non rp|pg|пг|mg|мг)\b", re.I)

TEXT_RULES = [
    ("complaint.cheat", re.compile(r"чит|\bsoft\b|софт|аим|aimbot|\bwh\b|\bвх\b|летает|спидхак|телепорт(ится|ирует)", re.I)),
    ("complaint.scam", re.compile(r"обман|кинул|развел|развёл|мошен|скам|\bscam\b|не отдал|не вернул", re.I)),
    ("complaint.rmt_ads", re.compile(r"реклам|за реал|продает акк|продаёт акк|\brmt\b", re.I)),
    ("complaint.insult", re.compile(r"\bоск|оскорб|мат(ом|ы|ери)|токсич|haqorat|sokdi|sokindi|сокинди|родн", re.I)),
]

APPEAL_VERDICTS = {"appeal_rejected", "appeal_approved"}
APPEAL_TEXT_RE = re.compile(r"не согласен|не согласна|несогласен|снимите|наказали (меня|зря)|выдал(и)? (мне )?(бан|наказ)", re.I)

REPORT_RULES = [
    ("report.account", re.compile(r"взлом|украл|пароль|доступ к акк|зайти в акк|пропал[аио]? (машин|дом|деньг|имущ)", re.I)),
    ("report.payment", re.compile(r"донат|оплат|платеж|платёж|не пришл[иа] (деньг|донат|гк)|списал", re.I)),
    ("report.help", re.compile(r"застрял|текстур|телепорт|\bтп\b|\bбаг|эвакуат|спавн|провалил|в воде|не могу выйти|вытащ", re.I)),
    ("report.complaint", re.compile(r"оск|дм\b|\bdm\b|убил|чит|нарушает|наказ|жалоб|\bдб\b|\bsk\b", re.I)),
    ("report.question", re.compile(r"\?|как |где |когда |почему |сколько |можно ли|что делать", re.I)),
]
OFFTOPIC_RE = re.compile(r"^[\W\d_]*(помогите|помоги|ау+|алло|админ|адм|\+|help|hi|привет|здравствуйте|ку)?[\W\d_]*$", re.I)


def player_text(ticket: dict) -> str:
    return " \n".join(m.get("text", "") for m in ticket.get("messages", []) if m.get("role") == "player")


def admin_text(ticket: dict) -> str:
    return " \n".join(m.get("text", "") for m in ticket.get("messages", []) if m.get("role") == "admin")


def weak_label(ticket: dict) -> str | None:
    """Категория по исходу обращения или None, если сигнала нет."""
    text = player_text(ticket)
    if ticket.get("kind") == "report":
        if OFFTOPIC_RE.match(text.strip()) or len(text.strip()) < 3:
            return "report.offtopic"
        for cat, rx in REPORT_RULES:
            if rx.search(text):
                return cat
        return None

    verdict = ticket.get("verdict")
    if verdict in APPEAL_VERDICTS or APPEAL_TEXT_RE.search(text[:120]):
        return "complaint.admin"

    violation = ticket.get("violation") or ""
    for ref in parse_refs(violation):
        if ref in REF_CATEGORY:
            return REF_CATEGORY[ref]
    if re.search(r"\bGZ\b|ГЗ|зел[её]н", violation, re.I) or RP_DM_RE.search(violation):
        return "complaint.dm"

    raw = f"{ticket.get('rule_refs_raw') or ''} {text}"
    for ref in parse_refs(raw):
        if ref in REF_CATEGORY:
            return REF_CATEGORY[ref]
    if RP_DM_RE.search(raw) or re.search(r"\bgz\b|зел[её]н", raw, re.I):
        return "complaint.dm"
    for cat, rx in TEXT_RULES:
        if rx.search(raw):
            return cat

    if verdict in ("invalid_format", "need_evidence"):
        return "complaint.invalid"
    return None
