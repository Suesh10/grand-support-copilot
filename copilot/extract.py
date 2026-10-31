"""Извлечение структурированных фактов из текста обращения.

Факты из жалобы — это слова игрока, а не истина: они идут в черновик только
как «по словам заявителя», решение подтверждает администратор.
"""

import re

from .rules import REF_RE, parse_refs
from .signals import TOXIC_RE

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


def spans(text: str) -> list[dict]:
    """Где в тексте лежат извлечённые факты: их подсвечивает интерфейс админа."""
    found = []
    for kind, rx in (("nick", NICK_RE), ("server", SERVER_RE)):
        found += [{"start": m.start(), "end": m.end(), "kind": kind} for m in rx.finditer(text)]
    # «доказ» находит слово, а подсветить нужно его целиком.
    for m in EVIDENCE_RE.finditer(text):
        end = m.end()
        while end < len(text) and text[end].isalpha():
            end += 1
        found.append({"start": m.start(), "end": end, "kind": "proof"})
    # Подсвечиваем только настоящие пункты: «99.1» из текста игрока фактом не считается.
    found += [{"start": m.start(), "end": m.end(), "kind": "rule"} for m in REF_RE.finditer(text) if parse_refs(m.group(0))]
    found += [{"start": m.start(), "end": m.end(), "kind": "toxic"} for m in TOXIC_RE.finditer(text)]
    found.sort(key=lambda x: x["start"])
    out: list[dict] = []
    for item in found:
        if not out or item["start"] >= out[-1]["end"]:
            out.append(item)
    return out
