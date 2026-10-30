"""Категория, приоритет и спам.

Сейчас заглушка на ключевых словах. В блоке 3 заменяется обученной моделью
(TF-IDF + логистическая регрессия), ключевые слова останутся запасным вариантом.
"""

import re

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

EMPTY_RE = re.compile(r"^[\W\d_]*(помогите|помоги|ау|алло|админ|\+|help|hi|привет)?[\W\d_]*$", re.I)

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
    "report.help": "p2",
    "complaint.invalid": "p3",
    "report.question": "p3",
    "report.offtopic": "p3",
}


def is_empty(text: str) -> bool:
    return len(text.strip()) < 3 or bool(EMPTY_RE.match(text.strip()))


def classify(kind: str, text: str, has_evidence: bool) -> tuple[str, str, float]:
    """Вернуть (категория, приоритет, уверенность)."""
    t = text.lower()
    category, conf = None, 0.4
    if kind == "report" and is_empty(t):
        category, conf = "report.offtopic", 0.8
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
    return category, priority, conf
