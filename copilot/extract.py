"""Извлечение структурированных фактов из текста обращения.

Факты из жалобы — это слова игрока, а не истина: они идут в черновик только
как «по словам заявителя», решение подтверждает администратор.
"""

import re

from .rules import parse_refs

# Ники в игре: Имя_Фамилия, иногда с цифрами.
NICK_RE = re.compile(r"\b([A-Z][a-z]+_[A-Z][a-z]+\d{0,3})\b")
EVIDENCE_RE = re.compile(r"скрин|видео|запис|fraps|фрапс|док-?в|доказ|<url>|screen|video|isbot|dalil", re.I)
SERVER_RE = re.compile(r"(?:сервер|server|серв)\s*[№#:]?\s*(\d{1,2})", re.I)


def extract(text: str, attachments: int = 0, rule_refs_raw: str = "") -> dict:
    nick = NICK_RE.search(text)
    server = SERVER_RE.search(text)
    return {
        "nickname": nick.group(1) if nick else None,
        "rule_refs": parse_refs(f"{rule_refs_raw} {text}"),
        "has_evidence": attachments > 0 or bool(EVIDENCE_RE.search(text)),
        "server": server.group(1) if server else None,
    }
