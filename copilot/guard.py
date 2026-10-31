"""Защитные правила: когда черновик нельзя отправлять без человека.

Требования ТЗ: платежи, апелляции банов и подозрения на взлом — всегда человеку;
черновик не обещает разбан, возврат средств или наказание другого игрока.
"""

import re

from .signals import APPEAL_RE, HACK_RE, OFFLINE_RE, PAYMENT_RE, THREAT_RE

ALWAYS_HUMAN = {"report.account", "report.payment", "complaint.admin"}

# Попытка управлять сервисом через текст обращения (prompt injection).
INJECTION_RE = re.compile(r"игнорир\w* .{0,20}(инструкц|правил)|ignore (all|previous|the above)|needs_human|"
                          r"system prompt|системн\w+ промпт|ты (теперь|больше не)", re.I)

# Решение о наказании другого игрока: допустимо в черновике только с needs_human
# (так в примере контракта из ТЗ), админ подтверждает его перед отправкой.
PROMISE_RE = re.compile(
    r"(будет|получит|получат|будут)\s+(наказан|забанен|заблокирован)|"
    r"(разбаним|разблокируем|снимем (бан|наказание)|вернём|вернем|возместим)", re.I)

# Разбан, снятие наказания, возврат денег/имущества, компенсация — черновик
# не может обещать этого никогда. Такой текст заменяется нейтральным.
FORBIDDEN_RE = re.compile(
    r"наказани\w*\s+(будет\s+|было\s+)?(снят|отмен|аннулир)|сним(у|ем|ут)\s+(вам\s+)?(наказ|бан|мут|блок)|"
    r"(наказани|бан|мут|блокировк)\w*\s+(вам\s+)?(сним|отмен)|"
    r"(разбан|разблокир)\w*\s*(вас|аккаунт|будет)|аккаунт\s+(будет\s+)?(восстановлен|разблокирован)|"
    r"(верн|возвра|возмест|компенсир)\w*\s+(вам\s+)?(деньг|средств|донат|имуществ|машин|гк|grand coins)|"
    r"jazo\w*\s+(olib tashlan|bekor)|qaytar(amiz|iladi)|"
    r"жаза\w*\s+(алын|жойыл)|қайтар(амыз|ылады)", re.I)


def has_forbidden_promise_hard(draft: str) -> bool:
    return bool(FORBIDDEN_RE.search(draft))


def check(category: str, text: str) -> list[str]:
    """Причины, по которым нужен человек. Пустой список — можно отвечать автоматически."""
    reasons = []
    if category in ALWAYS_HUMAN:
        reasons.append("такие обращения всегда решает человек")
    if APPEAL_RE.search(text):
        reasons.append("апелляция или просьба снять наказание")
    if HACK_RE.search(text):
        reasons.append("подозрение на взлом аккаунта")
    if PAYMENT_RE.search(text):
        reasons.append("вопрос о платеже или возврате")
    if THREAT_RE.search(text) or OFFLINE_RE.search(text):
        reasons.append("возможная угроза вне игры")
    if INJECTION_RE.search(text):
        reasons.append("попытка управлять ответом через текст обращения")
    if category.startswith("complaint.") and category != "complaint.invalid":
        reasons.append(PUNISH_REASON)
    return reasons


PUNISH_REASON = "решение о наказании подтверждает администратор"
# Исходы, при которых черновик никого не наказывает: просьба о доказательствах,
# неверное оформление, дубликат. Такой ответ можно отправлять без проверки.
NO_DECISION_VERDICTS = {"need_evidence", "invalid_format", "duplicate"}


def has_forbidden_promise(draft: str) -> bool:
    return bool(PROMISE_RE.search(draft))
