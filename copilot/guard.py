"""Защитные правила: когда черновик нельзя отправлять без человека.

Требования ТЗ: платежи, апелляции банов и подозрения на взлом — всегда человеку;
черновик не обещает разбан, возврат средств или наказание другого игрока.
"""

import re

ALWAYS_HUMAN = {"report.account", "report.payment", "complaint.admin"}

APPEAL_RE = re.compile(r"апелляц|разбан|разблок|снимите (бан|наказ)|незаслуж|ошибочно забан|unban|appeal", re.I)
HACK_RE = re.compile(r"взлом|взломал|украли акк|сменили пароль|hacked|buzish", re.I)
PAYMENT_RE = re.compile(r"донат|оплат|платеж|платёж|списал|верните деньги|refund|возврат", re.I)
THREAT_RE = re.compile(r"убью|найду тебя|суицид|покончу|адрес|в реале", re.I)

# Обещания, которых черновик давать не может.
PROMISE_RE = re.compile(
    r"(будет|получит|получат|будут)\s+(наказан|забанен|заблокирован)|"
    r"(разбаним|разблокируем|снимем (бан|наказание)|вернём|вернем|возместим)", re.I)


def check(category: str, text: str) -> list[str]:
    """Причины, по которым нужен человек. Пустой список — можно отвечать автоматически."""
    reasons = []
    if category in ALWAYS_HUMAN:
        reasons.append(f"категория {category} всегда идёт человеку")
    if APPEAL_RE.search(text):
        reasons.append("апелляция или просьба снять наказание")
    if HACK_RE.search(text):
        reasons.append("подозрение на взлом аккаунта")
    if PAYMENT_RE.search(text):
        reasons.append("вопрос о платеже или возврате")
    if THREAT_RE.search(text):
        reasons.append("возможная угроза вне игры")
    if category.startswith("complaint.") and category != "complaint.invalid":
        reasons.append("решение о наказании подтверждает администратор")
    return reasons


def has_forbidden_promise(draft: str) -> bool:
    return bool(PROMISE_RE.search(draft))
