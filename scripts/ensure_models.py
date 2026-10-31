"""Если моделей нет, а данные есть, обучает их. Работает в любой оболочке, поэтому make не зависит от sh."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    model = Path(os.getenv("COPILOT_ARTIFACTS_DIR", ROOT / "artifacts")) / "classifier.joblib"
    if model.exists():
        return 0
    data = Path(os.getenv("COPILOT_DATA_DIR", ROOT / "data" / "support" / "handout"))
    if (data / "tickets_train.jsonl.gz").exists():
        print(f"Модели не найдены, обучаю на {data} (~3 мин)...", flush=True)
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "train.py")], check=False).returncode
    print(f"ВНИМАНИЕ: нет моделей и данных в {data}. Работаю на правилах; укажите папку данных: DATA=путь/к/handout", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
