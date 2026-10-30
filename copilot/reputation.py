"""Профиль игрока: что показывает его история обращений.

Это подсказка администратору, а не приговор: сервис не отклоняет жалобы и не меняет
черновик из-за профиля. Игрока могут заваливать ложными жалобами, поэтому показываем
факты («жалоб 12, подтверждено 3»), а выводы делает человек.

Список критериев не зашит: шаблон строится из того, как админы закрывали жалобы,
и в него попадают исходы, которые встречаются достаточно часто.
"""

import gzip
import json
import re
from collections import Counter, defaultdict
from functools import lru_cache

import joblib

from . import config

PATH = config.ARTIFACTS_DIR / "reputation.joblib"
MIN_FILED = 5  # меньше — ещё не история, профиль не создаётся
MIN_SHARE = 0.01  # критерий входит в шаблон, если встречается хотя бы в 1% жалоб

CRITERIA_NAMES = {
    "approved": "нарушение подтверждено",
    "rejected": "нарушения не нашли",
    "need_evidence": "мало доказательств",
    "bad_evidence": "доказательства недостоверны",
    "invalid_format": "неверно оформлено",
    "duplicate": "дубли",
    "already_punished": "обвиняемый уже наказан",
    "appeal_rejected": "апелляции отклонены",
    "appeal_approved": "апелляции одобрены",
}
BAD_EVIDENCE_RE = re.compile(r"отредактир|обрезан|монтаж|подделк|недостоверн|фейк|tahrirlan|qirqilgan", re.I)


def outcome(ticket: dict) -> str | None:
    """Критерий, к которому относится исход обращения."""
    admin = " ".join(m.get("text", "") for m in ticket.get("messages", []) if m.get("role") == "admin")
    if BAD_EVIDENCE_RE.search(admin):
        return "bad_evidence"
    verdict = ticket.get("verdict")
    return verdict if verdict in CRITERIA_NAMES else None


def build(tickets) -> dict:
    """Агрегаты по хэшам игроков. Содержит только счётчики, без текстов обращений."""
    filed: dict = defaultdict(Counter)
    against: dict = defaultdict(Counter)
    reports: Counter = Counter()
    total: Counter = Counter()
    for t in tickets:
        reporter = t.get("reporter_hash")
        if t.get("kind") == "report":
            reports[reporter] += 1
            continue
        name = outcome(t)
        filed[reporter]["total"] += 1
        if t.get("reported_hash"):
            against[t["reported_hash"]]["total"] += 1
        if name:
            total[name] += 1
            filed[reporter][name] += 1
            if t.get("reported_hash"):
                against[t["reported_hash"]][name] += 1
    count = sum(c["total"] for c in filed.values()) or 1
    template = [name for name, n in total.most_common() if n / count >= MIN_SHARE]
    return {"filed": dict(filed), "against": dict(against), "reports": dict(reports), "template": template}


def build_from_train() -> dict:
    with gzip.open(config.TRAIN_PATH, "rt", encoding="utf-8") as f:
        return build(json.loads(line) for line in f)


def approval(counts: Counter) -> float | None:
    decided = sum(counts.get(k, 0) for k in ("approved", "rejected", "need_evidence", "bad_evidence", "invalid_format"))
    return counts.get("approved", 0) / decided if decided else None


@lru_cache(maxsize=1)
def load() -> dict | None:
    return joblib.load(PATH) if PATH.exists() else None


@lru_cache(maxsize=1)
def demo() -> dict:
    path = config.ROOT / "examples" / "sample_profiles.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def profile(player_hash: str | None) -> dict | None:
    """Профиль игрока или None, если истории мало."""
    if not player_hash:
        return None
    if player_hash in demo():
        return {**demo()[player_hash], "demo": True}
    data = load()
    if not data:
        return None
    filed = data["filed"].get(player_hash, Counter())
    against = data["against"].get(player_hash, Counter())
    reports = data["reports"].get(player_hash, 0)
    if filed.get("total", 0) + reports < MIN_FILED and against.get("total", 0) < MIN_FILED:
        return None
    criteria = [{"name": CRITERIA_NAMES[k], "count": filed[k]} for k in data["template"] if filed.get(k)]
    return {"filed": filed.get("total", 0), "reports": reports, "criteria": criteria,
            "against": against.get("total", 0), "against_confirmed": against.get("approved", 0)}
