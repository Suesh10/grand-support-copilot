"""Обучение классификатора на слабой разметке: make train

Печатает охват разметки и качество на отложенной части (это согласие со
слабыми метками, а не настоящая точность — её меряем на ручной разметке в eval).
"""

import gzip
import json
import random
import sys
from collections import Counter

import joblib
from sklearn.metrics import accuracy_score, classification_report

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from copilot import config  # noqa: E402
from copilot.labels import player_text, weak_label  # noqa: E402
from copilot.model import MODEL_PATH, build_pipeline, model_input  # noqa: E402
from copilot.normalize import normalize  # noqa: E402

MAX_PER_CLASS = 6000  # ограничение доминирующих классов (оскорбления, оффтоп)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    random.seed(42)
    tickets = [json.loads(line) for line in gzip.open(config.TRAIN_PATH, "rt", encoding="utf-8")]
    models = {}
    for kind in ("complaint", "report"):
        data = []
        for t in tickets:
            if t["kind"] != kind:
                continue
            label = weak_label(t)
            if label:
                text = normalize(" \n".join(m.get("text", "") for m in t["messages"] if m.get("role") != "admin"))
                data.append((model_input(kind, text, t.get("rule_refs_raw")), label))
        total = sum(t["kind"] == kind for t in tickets)
        print(f"\n== {kind}: размечено {len(data)} из {total} ({len(data) / total:.0%})")

        by_class: dict[str, list] = {}
        for x, y in data:
            by_class.setdefault(y, []).append((x, y))
        data = [s for items in by_class.values() for s in random.sample(items, min(len(items), MAX_PER_CLASS))]
        random.shuffle(data)
        print("классы:", dict(Counter(y for _, y in data).most_common()))

        split = int(len(data) * 0.9)
        train, test = data[:split], data[split:]
        pipe = build_pipeline()
        pipe.fit([x for x, _ in train], [y for _, y in train])
        pred = pipe.predict([x for x, _ in test])
        gold = [y for _, y in test]
        print(f"согласие со слабой разметкой: {accuracy_score(gold, pred):.3f}")
        print(classification_report(gold, pred, zero_division=0, digits=3))

        pipe.fit([x for x, _ in data], [y for _, y in data])
        models[kind] = pipe

    config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(models, MODEL_PATH, compress=3)
    print(f"Модель сохранена: {MODEL_PATH}")


if __name__ == "__main__":
    main()
