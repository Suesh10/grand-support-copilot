"""Пути и настройки. Всё переопределяется через переменные окружения или .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Данные кейса не лежат в репозитории (условие Grand Mobile): путь задаётся снаружи.
DATA_DIR = Path(os.getenv("COPILOT_DATA_DIR", ROOT / "data" / "support" / "handout"))
RULES_PATH = DATA_DIR / "rules.json"
TAXONOMY_PATH = DATA_DIR / "taxonomy.json"
TRAIN_PATH = DATA_DIR / "tickets_train.jsonl.gz"
VALID_PATH = DATA_DIR / "tickets_valid.jsonl"

# Артефакты обучения (модели, индексы) — генерируются командой `make train`.
ARTIFACTS_DIR = Path(os.getenv("COPILOT_ARTIFACTS_DIR", ROOT / "artifacts"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LLM_MODEL = os.getenv("COPILOT_LLM_MODEL", "gemini-3.5-flash-lite")
# offline — черновик без LLM (из шаблонов), auto — LLM если есть ключ.
LLM_MODE = os.getenv("COPILOT_LLM_MODE", "auto")
