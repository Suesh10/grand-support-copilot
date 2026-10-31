"""Поиск похожих прошлых обращений и ответов админов на них.

Админы Grand Mobile отвечают шаблонно, а черновики оценивают рядом с реальным
ответом. Поэтому лучший ориентир для черновика — как админы отвечали на
похожие обращения с тем же исходом. Индекс: TF-IDF по словам, косинусная близость.
"""

import gzip
import json
import re
from functools import lru_cache

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from . import config
from .labels import KNOWN_VERDICTS as USEFUL_VERDICTS, verdict_of
from .normalize import normalize

INDEX_PATH = config.ARTIFACTS_DIR / "cases.joblib"
NICK_RE = re.compile(r"\b[A-Z][a-z]+_[A-Z][a-z]+\d{0,3}\b")


def _texts(t: dict) -> tuple[str, str]:
    player = " ".join(m.get("text", "") for m in t["messages"] if m.get("role") != "admin")
    admin = " ".join(m.get("text", "") for m in t["messages"] if m.get("role") == "admin")
    return normalize(player), admin.strip()


def build(max_reports: int = 30000) -> dict:
    """Собрать индекс из обучающей выборки: жалобы с понятным исходом + репорты с ответом."""
    cases = []
    reports = 0
    for line in gzip.open(config.TRAIN_PATH, "rt", encoding="utf-8"):
        t = json.loads(line)
        player, admin = _texts(t)
        if not player or not admin or len(admin) < 8:
            continue
        verdict = verdict_of(t)
        if t["kind"] == "complaint" and verdict is None:
            continue
        if t["kind"] == "report":
            if reports >= max_reports:
                continue
            reports += 1
        cases.append({
            "kind": t["kind"], "lang": t.get("lang"), "verdict": verdict,
            "violation": t.get("violation"), "punishment": t.get("punishment"),
            "reported_nick": t.get("reported_nick"), "text": player[:500], "reply": admin[:1200],
        })
    vec = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=2, max_features=150_000,
                          sublinear_tf=True, token_pattern=r"(?u)\b\w[\w.]*\b")
    matrix = vec.fit_transform([c["text"] for c in cases])
    return {"vectorizer": vec, "matrix": matrix, "cases": cases, "report_templates": report_templates()}


def report_templates(top: int = 3) -> dict[str, list[tuple[str, int]]]:
    """Самые частые ответы админов на репорты каждой категории (кластеры шаблонов)."""
    from collections import Counter, defaultdict

    from .labels import weak_label

    counts: dict[str, Counter] = defaultdict(Counter)
    for line in gzip.open(config.TRAIN_PATH, "rt", encoding="utf-8"):
        t = json.loads(line)
        if t["kind"] != "report":
            continue
        label = weak_label(t)
        reply = " ".join(m.get("text", "") for m in t["messages"] if m.get("role") == "admin").strip()
        if label and reply:
            key = re.sub(r"\s+", " ", reply.rstrip(".! ").replace(",", ", ")).replace(" ,", ",")
            counts[label][re.sub(r",\s+", ", ", key) + "."] += 1
    return {label: c.most_common(top) for label, c in counts.items()}


def report_template(category: str) -> str | None:
    index = load()
    templates = (index or {}).get("report_templates", {}).get(category)
    return templates[0][0] if templates else None


@lru_cache(maxsize=1)
def load() -> dict | None:
    return joblib.load(INDEX_PATH) if INDEX_PATH.exists() else None


def similar(kind: str, text: str, k: int = 3, verdict: str | None = None, lang: str | None = None) -> list[dict]:
    """Топ-k похожих обращений того же вида (и, если задан, с тем же исходом и языком)."""
    index = load()
    if not index:
        return []
    q = index["vectorizer"].transform([normalize(text)])
    scores = (index["matrix"] @ q.T).toarray().ravel()
    cases = index["cases"]
    order = np.argsort(-scores)[:2000]

    def pick(require_lang: bool) -> list[dict]:
        out = []
        for i in order:
            c = cases[i]
            if c["kind"] != kind or (verdict and c["verdict"] != verdict):
                continue
            if require_lang and lang and c["lang"] != lang:
                continue
            out.append({**c, "score": float(scores[i])})
            if len(out) == k:
                break
        return out

    return pick(require_lang=True) or pick(require_lang=False)
