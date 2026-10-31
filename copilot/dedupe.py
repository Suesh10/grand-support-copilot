"""Отсев дублей: один игрок, одна проблема, несколько обращений подряд.

Жалоба — дубль, если тот же заявитель уже жаловался на того же игрока за час
(окно из ТЗ: по валидации повторы через 8–23 часа — это уже разные инциденты).
Репорт — дубль, если тот же игрок за час прислал тот же или похожий текст: «застрял»
и «помогите застрял в текстурах» это одна проблема. Без идентификатора заявителя
дубль не определяется: одинаковый текст от разных игроков дублем не считается.
"""

from datetime import datetime
from difflib import SequenceMatcher

from .normalize import normalize

WINDOW_COMPLAINT_H = 1
WINDOW_REPORT_H = 1
MIN_REPORT_TEXT = 5
SAME_PROBLEM = 0.6  # похожесть текстов: на данных кейса у таких пар в 94% совпадает и категория
MAX_SEEN = 200_000  # окно всего час: старые записи не нужны, а сервис работает неделями


def same_problem(a: str, b: str) -> bool:
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return shorter in longer or SequenceMatcher(None, a, b).ratio() >= SAME_PROBLEM


def _parse(ts: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


class Deduper:
    def __init__(self) -> None:
        self.seen: dict[tuple, datetime | None] = {}
        self.reports: dict[str, list[tuple[str, datetime | None]]] = {}

    def is_duplicate(self, ticket: dict) -> bool:
        """Запомнить обращение и сказать, повторяет ли оно уже виденное."""
        if len(self.seen) + len(self.reports) > MAX_SEEN:
            self.seen.clear()
            self.reports.clear()
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
            return self._repeated_report(reporter, text, _parse(ticket.get("created_at")))
        now = _parse(ticket.get("created_at"))
        known = key in self.seen
        before = self.seen.get(key)
        self.seen[key] = now
        if not known:
            return False
        if now is None or before is None:
            return True
        return abs((now - before).total_seconds()) <= window * 3600

    def _repeated_report(self, reporter: str, text: str, now: datetime | None) -> bool:
        """Похожий текст от того же игрока в пределах окна. Память хранит только последний час игрока."""
        window = WINDOW_REPORT_H * 3600
        fresh = [(t, ts) for t, ts in self.reports.get(reporter, [])
                 if now is None or ts is None or abs((now - ts).total_seconds()) <= window]
        repeated = any(same_problem(text, t) for t, _ in fresh)
        self.reports[reporter] = [*fresh, (text, now)]
        return repeated
