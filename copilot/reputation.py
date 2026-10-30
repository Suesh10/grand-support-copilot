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
import threading
from collections import Counter, defaultdict
from functools import lru_cache

import joblib

from . import config
from .labels import weak_label

PATH = config.ARTIFACTS_DIR / "reputation.joblib"
MEMORY_PATH = config.ARTIFACTS_DIR / "memory.json"
FREQUENT = 10  # с какого числа обращений игрок считается частым заявителем или частой целью жалоб
NICK_RE = re.compile(r"\b[A-Z][a-z]+_[A-Z][a-z]+\d{0,3}\b")
_lock = threading.Lock()
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
    topics: dict = defaultdict(Counter)
    reports: Counter = Counter()
    reports_against: Counter = Counter()
    total: Counter = Counter()
    tickets = list(tickets)
    # Репорт не связан с обвиняемым хэшем, поэтому ищем ник: он одинаков во всём наборе.
    nick_to_hash = {t["reported_nick"]: t["reported_hash"] for t in tickets if t.get("reported_nick") and t.get("reported_hash")}
    for t in tickets:
        reporter = t.get("reporter_hash")
        if t.get("kind") == "report":
            reports[reporter] += 1
            text = " ".join(m.get("text", "") for m in t.get("messages", []) if m.get("role") == "player")
            for nick in set(NICK_RE.findall(text)):
                if nick in nick_to_hash:
                    reports_against[nick_to_hash[nick]] += 1
            continue
        # Апелляция записана как жалоба на администратора: в его профиль как игрока она не идёт.
        topic = weak_label(t)
        reported = t.get("reported_hash") if topic and topic != "complaint.admin" else None
        if reported and topic != "complaint.invalid":
            topics[reported][topic] += 1
        name = outcome(t)
        filed[reporter]["total"] += 1
        if reported:
            against[reported]["total"] += 1
        if name:
            total[name] += 1
            filed[reporter][name] += 1
            if reported:
                against[reported][name] += 1
    count = sum(c["total"] for c in filed.values()) or 1
    template = [name for name, n in total.most_common() if n / count >= MIN_SHARE]
    return {"filed": dict(filed), "against": dict(against), "reports": dict(reports), "template": template,
            "reports_against": dict(reports_against), "topics": dict(topics)}


def build_from_train() -> dict:
    with gzip.open(config.TRAIN_PATH, "rt", encoding="utf-8") as f:
        return build(json.loads(line) for line in f)


def approval(counts: Counter) -> float | None:
    decided = sum(counts.get(k, 0) for k in ("approved", "rejected", "need_evidence", "bad_evidence", "invalid_format"))
    return counts.get("approved", 0) / decided if decided else None


@lru_cache(maxsize=1)
def load() -> dict | None:
    return joblib.load(PATH) if PATH.exists() else None


def read_memory() -> dict:
    return json.loads(MEMORY_PATH.read_text(encoding="utf-8")) if MEMORY_PATH.exists() else {}


def remember(reported_hash: str | None, category: str) -> None:
    """Мини-память: новое обращение на игрока копится поверх истории и переживает перезапуск."""
    if not reported_hash:
        return
    with _lock:
        memory = read_memory()
        note = memory.setdefault(reported_hash, {"new": 0, "topics": {}})
        note["new"] += 1
        note["topics"][category] = note["topics"].get(category, 0) + 1
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=False), encoding="utf-8")


def comment(p: dict) -> tuple[list[str], str]:
    """Пометки и вывод из цифр профиля. Только факты, без оценки игрока как человека."""
    tags, parts = [], []
    confirmed = next((c["count"] for c in p["criteria"] if c["name"] == CRITERIA_NAMES["approved"]), 0)
    against = p["against"] + p["reports_against"] + p.get("new", 0)
    if p["filed"] + p["reports"] >= FREQUENT:
        tags.append("часто жалуется")
    if against >= FREQUENT:
        tags.append("на него часто жалуются")
    if p["filed"] >= MIN_FILED:
        share = confirmed / p["filed"]
        parts.append(f"Подтвердилось {confirmed} из {p['filed']} его жалоб.")
        if share >= 0.6:
            tags.append("жалобы обычно подтверждаются")
        elif share < 0.3:
            tags.append("жалобы редко подтверждаются")
    if p["against"] >= MIN_FILED:
        parts.append(f"На него подтверждено {p['against_confirmed']} из {p['against']} жалоб.")
    if p["topics"]:
        parts.append(f"Чаще всего жалуются на: {p['topics'][0]['code']}.")
    return tags, " ".join(parts) or "Истории пока мало для выводов."


@lru_cache(maxsize=1)
def demo() -> dict:
    path = config.ROOT / "examples" / "sample_profiles.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def profile(player_hash: str | None) -> dict | None:
    """Профиль игрока или None, если истории мало."""
    if not player_hash:
        return None
    note = read_memory().get(player_hash, {"new": 0, "topics": {}})
    if player_hash in demo():
        base = {"reports_against": 0, "topics": {}, **demo()[player_hash], "demo": True}
    else:
        data = load() or {"filed": {}, "against": {}, "reports": {}, "template": [], "reports_against": {}, "topics": {}}
        filed = data["filed"].get(player_hash, Counter())
        against = data["against"].get(player_hash, Counter())
        base = {"filed": filed.get("total", 0), "reports": data["reports"].get(player_hash, 0),
                "criteria": [{"name": CRITERIA_NAMES[k], "count": filed[k]} for k in data["template"] if filed.get(k)],
                "against": against.get("total", 0), "against_confirmed": against.get("approved", 0),
                "reports_against": data["reports_against"].get(player_hash, 0), "topics": dict(data["topics"].get(player_hash, {}))}
        about = base["against"] + base["reports_against"] + note["new"]
        if base["filed"] + base["reports"] < MIN_FILED and about < MIN_FILED:
            return None
    topics = Counter(base["topics"])
    topics.update(note["topics"])
    p = {**base, "new": note["new"], "total": base["filed"] + base["reports"],
         "topics": [{"code": k, "count": n} for k, n in topics.most_common(3)]}
    p["tags"], p["comment"] = comment(p)
    return p
