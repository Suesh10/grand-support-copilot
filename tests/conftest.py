"""Данные кейса не лежат в репозитории: без них тесты пропускаются с понятной причиной."""

import os

import pytest

os.environ.setdefault("COPILOT_LLM_MODE", "offline")

from copilot import config  # noqa: E402


def pytest_collection_modifyitems(items):
    if config.RULES_PATH.exists():
        return
    skip = pytest.mark.skip(reason=f"нет данных кейса в {config.DATA_DIR}: запустите make test DATA=путь/к/handout")
    for item in items:
        item.add_marker(skip)
