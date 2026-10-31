"""Предложение новых шаблонов по кластерам похожих обращений (бонус ТЗ).

Обращения группируются по тексту, и для каждой группы смотрим, как отвечали админы.
Шаблон стоит предложить, если группа большая, админы отвечают в ней одинаково,
а такого ответа ещё нет среди шаблонов категории. Решение принимает админ, текст
проходит те же проверки, что и обычный черновик. Результат лежит в artifacts/:
это производные данных кейса, в репозиторий они не попадают.
"""

import gzip
import json
import re
from collections import Counter, defaultdict

from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from . import config, retrieve
from .draft import INVENTED_FACT_RE, PUNISH_TERM_RE
from .guard import FORBIDDEN_RE, PROMISE_RE
from .labels import admin_text, player_text, weak_label
from .normalize import detect_lang, normalize
from .rules import load_points, parse_refs

CANDIDATES_PATH = config.ARTIFACTS_DIR / "template_candidates.json"
CLUSTERS = 60
MIN_SIZE = 100  # меньше такого объёма шаблон не окупится
MIN_SHARE = 0.04  # доля ответа в группе: ниже админы отвечают каждый по-своему
TOP = 8
STOP_WORDS = {"что", "как", "это", "мне", "меня", "мой", "моя", "вас", "вы", "где", "там", "тут", "уже", "или", "для", "url", "digits"}
NICK_RE = re.compile(r"\b[A-Z][a-z]+_[A-Z][a-z]+\d{0,3}\b")
WORD_RE = re.compile(r"[а-яёa-zәғқңөұүһі']{3,}", re.I)


def clean_reply(reply: str) -> str:
    return re.sub(r"\s+", " ", reply).strip()


def fits(reply: str) -> bool:
    """Шаблон не должен содержать чужих деталей, сроков и обещаний."""
    if not 15 <= len(reply) <= 300 or NICK_RE.search(reply) or "<" in reply:
        return False
    if INVENTED_FACT_RE.search(reply) or PUNISH_TERM_RE.search(reply) or FORBIDDEN_RE.search(reply) or PROMISE_RE.search(reply):
        return False
    return all(ref in load_points() for ref in parse_refs(reply))


def build(tickets=None) -> list[dict]:
    if tickets is None:
        with gzip.open(config.TRAIN_PATH, "rt", encoding="utf-8") as f:
            tickets = [json.loads(line) for line in f]
    rows = []
    for t in tickets:
        if t["kind"] != "report":
            continue
        text, reply = normalize(player_text(t)), clean_reply(admin_text(t))
        if len(text) >= 5 and reply:
            rows.append((text, reply, weak_label(t)))
    vectors = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=5, max_features=50_000, sublinear_tf=True).fit_transform(r[0][:200] for r in rows)
    labels = MiniBatchKMeans(n_clusters=CLUSTERS, n_init=3, random_state=42, batch_size=2048).fit_predict(vectors)

    groups = defaultdict(list)
    for row, label in zip(rows, labels):
        groups[int(label)].append(row)
    current = set()
    index = retrieve.load() or {}
    for items in index.get("report_templates", {}).values():
        current.update(clean_reply(reply).rstrip(".!").lower() for reply, _ in items[:1])

    out = []
    for group in groups.values():
        if len(group) < MIN_SIZE:
            continue
        replies = Counter(reply.rstrip(".!") for _, reply, _ in group)
        reply, count = next(((r, c) for r, c in replies.most_common(20) if fits(r) and r.lower() not in current), (None, 0))
        share = count / len(group)
        if not reply or share < MIN_SHARE:
            continue
        words = Counter(w.lower() for text, _, _ in group for w in set(WORD_RE.findall(text)) if w.lower() not in STOP_WORDS)
        category = Counter(label for _, _, label in group if label).most_common(1)
        out.append({"size": len(group), "share": round(share, 3), "category": category[0][0] if category else "report.question",
                    "terms": [w for w, _ in words.most_common(6)], "reply": reply + ".", "lang": detect_lang(reply)})
    out.sort(key=lambda x: -x["size"] * x["share"])
    # Один ответ на несколько групп: предлагаем его один раз, для самой крупной.
    unique = {}
    for item in out:
        unique.setdefault((item["category"], item["reply"]), item)
    out = [{**x, "id": i + 1} for i, x in enumerate(list(unique.values())[:TOP])]
    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(f"Предложено шаблонов: {len(build())} → {CANDIDATES_PATH}")
