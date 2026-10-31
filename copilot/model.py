"""Классификатор категорий: TF-IDF по символьным n-граммам + логистическая регрессия.

Символьные n-граммы устойчивы к опечаткам, транслиту и смеси языков —
ровно то, что есть в обращениях. Отдельная модель на каждый kind.
"""

from functools import lru_cache

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from . import config

MODEL_PATH = config.ARTIFACTS_DIR / "classifier.joblib"


def build_pipeline():
    return make_pipeline(
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, max_features=200_000,
                        sublinear_tf=True, lowercase=True),
        LogisticRegression(max_iter=2000, C=4.0, class_weight="balanced"),
    )


def model_input(kind: str, text: str, rule_refs_raw: str = "") -> str:
    return f"{rule_refs_raw or ''} | {text}"[:1500]


@lru_cache(maxsize=1)
def load() -> dict | None:
    """{'complaint': pipeline, 'report': pipeline} или None, если модель не обучена."""
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def predict(kind: str, text: str, rule_refs_raw: str = "") -> tuple[str, float] | None:
    """kind = complaint | report — категория; kind = verdict — вероятный исход жалобы."""
    models = load()
    if not models or kind not in models:
        return None
    pipe = models[kind]
    proba = pipe.predict_proba([model_input(kind, text, rule_refs_raw)])[0]
    best = proba.argmax()
    return pipe.classes_[best], float(proba[best])


def is_admin(player_hash: str | None) -> bool:
    """Часто ли на этого игрока подают апелляции: так выглядит администратор, выдавший наказание."""
    models = load()
    return bool(models and player_hash and player_hash in models.get("admins", ()))
