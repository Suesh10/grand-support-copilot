"""Данные кейса не лежат в репозитории: без них тесты пропускаются с понятной причиной."""

import os

import pytest

os.environ.setdefault("COPILOT_LLM_MODE", "offline")

from copilot import config  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Ни один тест не пишет в настоящий artifacts/: там живое состояние интерфейса."""
    from copilot import admin, learn, llm, reputation

    monkeypatch.setattr(admin, "ARCHIVE_PATH", tmp_path / "archive.json")
    monkeypatch.setattr(admin, "DELETED_PATH", tmp_path / "deleted_tickets.json")
    monkeypatch.setattr(admin, "FEEDBACK_PATH", tmp_path / "feedback.jsonl")
    monkeypatch.setattr(learn, "LESSONS_PATH", tmp_path / "lessons.json")
    monkeypatch.setattr(llm, "CACHE_PATH", tmp_path / "llm_cache.json")
    monkeypatch.setattr(reputation, "NOTES_PATH", tmp_path / "admin_notes.json")
    monkeypatch.setattr(reputation, "MEMORY_PATH", tmp_path / "memory.json")


def pytest_collection_modifyitems(items):
    if config.RULES_PATH.exists():
        return
    skip = pytest.mark.skip(reason=f"нет данных кейса в {config.DATA_DIR}: запустите make test DATA=путь/к/handout")
    for item in items:
        item.add_marker(skip)
