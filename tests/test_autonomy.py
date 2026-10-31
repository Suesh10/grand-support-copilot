"""Сервис работает без помощи команды: битые файлы, пустая очередь, занятый порт."""

import importlib.util
import json
import socket
from pathlib import Path

from fastapi.testclient import TestClient

from copilot import admin, config, doctor, reputation, storage
from copilot.api import app

client = TestClient(app)
ROOT = Path(__file__).parent.parent


def load_run():
    spec = importlib.util.spec_from_file_location("run", ROOT / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_broken_json_is_set_aside_not_lost(tmp_path):
    path = tmp_path / "archive.json"
    path.write_text("{обрыв записи", encoding="utf-8")
    assert storage.read_json(path, []) == []
    assert not path.exists()
    kept = list(tmp_path.glob("archive.json.broken-*"))
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8") == "{обрыв записи"


def test_wrong_format_counts_as_broken(tmp_path):
    path = tmp_path / "notes.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    assert storage.read_json(path, []) == []


def test_bad_lines_are_skipped(tmp_path):
    path = tmp_path / "feedback.jsonl"
    path.write_text('{"a": 1}\nобрыв\n[1]\n{"a": 2}\n', encoding="utf-8")
    assert [r["a"] for r in storage.read_jsonl(path)] == [1, 2]


def test_write_leaves_no_temp_file(tmp_path):
    path = tmp_path / "deep" / "x.json"
    storage.write_json(path, [1])
    assert storage.read_json(path, []) == [1] and [p.name for p in path.parent.iterdir()] == ["x.json"]


def test_service_survives_every_broken_state_file():
    for path in (admin.ARCHIVE_PATH, admin.DELETED_PATH, reputation.NOTES_PATH, reputation.MEMORY_PATH):
        path.write_text("{обрыв", encoding="utf-8")
    admin.FEEDBACK_PATH.write_text("обрыв\n", encoding="utf-8")
    for url in ("/api/queue", "/api/archive", "/api/stats", "/api/diagnostics"):
        assert client.get(url).status_code == 200, url
    assert client.post("/api/feedback", json={"ticket_id": "demo-06", "action": "send", "category": "report.help"}).status_code == 200


def test_bad_queue_lines_do_not_empty_the_queue(tmp_path, monkeypatch):
    path = tmp_path / "queue.jsonl"
    good = {"ticket_id": "ok-1", "kind": "report", "messages": [{"role": "player", "text": "застрял в текстурах"}]}
    path.write_text(f'{json.dumps(good)}\nобрыв\n[1]\n{{"ticket_id": "bad", "messages": 5}}\n', encoding="utf-8")
    monkeypatch.setattr(admin, "QUEUE_PATH", str(path))
    admin.raw_tickets.cache_clear(), admin._load_queue.cache_clear()
    try:
        assert [i["id"] for i in client.get("/api/queue").json()["items"]] == ["ok-1"]
    finally:
        monkeypatch.undo()
        admin.raw_tickets.cache_clear(), admin._load_queue.cache_clear()


def test_missing_queue_file_gives_an_empty_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(admin, "QUEUE_PATH", str(tmp_path / "нет.jsonl"))
    admin.raw_tickets.cache_clear(), admin._load_queue.cache_clear()
    try:
        assert client.get("/api/queue").json()["items"] == []
        checks = {c["name"]: c for c in client.get("/api/diagnostics").json()["checks"]}
        assert checks["Очередь"]["state"] == "warn" and checks["Очередь"]["fix"]
    finally:
        monkeypatch.undo()
        admin.raw_tickets.cache_clear(), admin._load_queue.cache_clear()


def test_every_problem_comes_with_a_fix(monkeypatch):
    monkeypatch.setattr(doctor, "load_points", lambda: {})
    monkeypatch.setattr(doctor.model, "load", lambda: None)
    monkeypatch.setattr(doctor, "can_write", lambda: False)
    rows = doctor.check(0)
    assert all(r["fix"] for r in rows if r["state"] == "bad")
    assert {r["name"] for r in rows if r["state"] == "bad"} == {"Правила", "Сохранение"}


def test_diagnostics_never_show_the_key(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "секретный-ключ")
    assert "секретный-ключ" not in client.get("/api/diagnostics").text


def test_launcher_skips_a_busy_port():
    run = load_run()
    with socket.socket() as busy:
        busy.bind((run.HOST, 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert run.free_port(port) > port


def test_launcher_finds_data_in_any_subfolder(tmp_path, monkeypatch):
    run = load_run()
    monkeypatch.delenv("COPILOT_DATA_DIR", raising=False)
    monkeypatch.setattr(run, "ROOT", tmp_path)
    assert run.find_data() is None
    folder = tmp_path / "data" / "из архива"
    folder.mkdir(parents=True)
    (folder / "rules.json").write_text("{}", encoding="utf-8")
    assert run.find_data() == folder
