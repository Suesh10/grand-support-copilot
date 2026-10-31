"""Категория, приоритет и спам.

Основной путь — обученная модель (copilot/model.py). Ключевые слова — запасной
вариант, если модель не обучена, и страховка для критичных категорий:
взлом и платежи нельзя пропустить, даже если модель уверена в другом.
"""

import re

from . import model
from .labels import APPEAL_TEXT_RE, REPORT_RULES
from .signals import HACK_RE, MASS_BUG_RE, PAYMENT_RE, THREAT_RE

CRITICAL_REPORT = {"report.account", "report.payment"}

KEYWORDS = {
    "complaint.cheat": r"чит|soft|софт|аим|aim|wh\b|вх\b|летает|спидхак|cheat|hack",
    "complaint.scam": r"обман|кинул|развел|развёл|мошен|скам|scam|не отдал|aldad",
    "complaint.rmt_ads": r"реклам|продает за|продаёт за|реал|rmt|донат за|ads",
    "complaint.dm": r"\bdm\b|\bдм\b|убил|nonrp|нонрп|\bsk\b|\bdb\b|\btk\b|gz|зел[её]н",
    "complaint.insult": r"оск|мат|сокинди|sokdi|haqorat|токсич|руга|2\.1",
    "complaint.admin": r"админ.*(наруш|наказал|неправ)|жалоба на админ",
    "report.account": r"взлом|украл|пароль|доступ|аккаунт|hack|пропал",
    "report.payment": r"донат|оплат|платеж|платёж|деньги не пришли|списал|payment",
    "report.help": r"застрял|текстур|телепорт|тп\b|баг|эвакуатор|спавн|помогите выбраться",
    "report.question": r"как |где |когда |почему |что делать|\?",
}

EMPTY_RE = re.compile(r"^[\W\d_]*(ау|алло|админ|\+|hi|привет)?[\W\d_]*$", re.I)

PRIORITY_BY_CATEGORY = {
    "report.account": "p0",
    "report.payment": "p0",
    "complaint.cheat": "p1",
    "complaint.scam": "p1",
    "complaint.rmt_ads": "p1",
    "complaint.insult": "p2",
    "complaint.dm": "p2",
    "complaint.admin": "p2",
    "complaint.other": "p2",
    "report.complaint": "p2",
    "report.help": "p3",
    "complaint.invalid": "p3",
    "report.question": "p3",
    "report.offtopic": "p3",
}


def is_empty(text: str) -> bool:
    return len(text.strip()) < 3 or bool(EMPTY_RE.match(text.strip()))


def classify(kind: str, text: str, has_evidence: bool, rule_refs_raw: str = "") -> tuple[str, str, float]:
    """Вернуть (категория, приоритет, уверенность)."""
    t = text.lower()
    category, conf = None, 0.4
    predicted = model.predict(kind, text, rule_refs_raw)
    if kind == "report" and is_empty(t):
        category, conf = "report.offtopic", 0.9
    elif predicted:
        category, conf = predicted
        # Апелляция на бан за читы похожа на жалобу на читы — явные маркеры апелляции важнее модели.
        if kind == "complaint" and APPEAL_TEXT_RE.search(f"{rule_refs_raw}\n{text[:200]}"):
            category, conf = "complaint.admin", max(conf, 0.75)
        if kind == "report":
            for cat, rx in REPORT_RULES:
                if cat in CRITICAL_REPORT and rx.search(text):
                    category, conf = cat, max(conf, 0.7)
                    break
            if HACK_RE.search(text):
                category, conf = "report.account", max(conf, 0.7)
            elif PAYMENT_RE.search(text) and category != "report.account":
                category, conf = "report.payment", max(conf, 0.7)
    else:
        for cat, pattern in KEYWORDS.items():
            if cat.split(".")[0] != kind and not (kind == "report" and cat.startswith("complaint")):
                continue
            if re.search(pattern, t):
                category, conf = cat, 0.6
                break
    if category is None:
        category = "complaint.other" if kind == "complaint" else "report.question"
    if kind == "report" and category.startswith("complaint."):
        category = "report.complaint"

    priority = PRIORITY_BY_CATEGORY.get(category, "p2")
    # Жалоба с доказательствами важнее, без доказательств — ниже (taxonomy.json).
    if kind == "complaint" and not has_evidence and priority in ("p1", "p2"):
        priority = "p3"
    # Жалоба с доказательствами на серьёзное нарушение — высокий приоритет.
    if kind == "complaint" and has_evidence and category in ("complaint.cheat", "complaint.scam", "complaint.rmt_ads"):
        priority = "p1"
    if HACK_RE.search(t) or THREAT_RE.search(t) or MASS_BUG_RE.search(t):
        priority = "p0"
    return category, priority, conf
