"""Отсев дублей: один игрок, одна проблема, несколько обращений подряд.

Жалоба — дубль, если тот же заявитель уже жаловался на того же игрока за час
(окно из ТЗ: по валидации повторы через 8–23 часа — это уже разные инциденты).
Репорт — дубль, если тот же игрок прислал тот же текст за час. Без идентификатора
заявителя дубль не определяется: одинаковый текст от разных игроков дублем не считается.
"""

from datetime import datetime

from .normalize import normalize

WINDOW_COMPLAINT_H = 1
WINDOW_REPORT_H = 1
MIN_REPORT_TEXT = 5
MAX_SEEN = 200_000  # окно всего час: старые записи не нужны, а сервис работает неделями


def _parse(ts: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


class Deduper:
    def __init__(self) -> None:
        self.seen: dict[tuple, datetime | None] = {}

    def is_duplicate(self, ticket: dict) -> bool:
        """Запомнить обращение и сказать, повторяет ли оно уже виденное."""
        reporter = ticket.get("reporter_hash")
        if not reporter:
            return False
        reported = ticket.get("reported_hash")
        if reported:
            key, window = (reporter, "c", reported), WINDOW_COMPLAINT_H
        else:
            text = normalize(" ".join(m.get("text") or "" for m in ticket.get("messages") or []
                                      if m.get("role") != "admin")).lower()
            if len(text) < MIN_REPORT_TEXT:
                return False
            key, window = (reporter, "r", text), WINDOW_REPORT_H
        now = _parse(ticket.get("created_at"))
        if len(self.seen) > MAX_SEEN:
            self.seen.clear()
        known = key in self.seen
        before = self.seen.get(key)
        self.seen[key] = now
        if not known:
            return False
        if now is None or before is None:
            return True
        return abs((now - before).total_seconds()) <= window * 3600
