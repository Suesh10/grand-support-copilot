"""Интерфейс админа: очередь, серии и сохранение действий как обучающего сигнала."""

import json
import os

os.environ.setdefault("COPILOT_LLM_MODE", "offline")

from fastapi.testclient import TestClient  # noqa: E402

from copilot import admin  # noqa: E402
from copilot.api import app  # noqa: E402

client = TestClient(app)


def test_home_opens_admin():
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/admin"


def test_queue_shows_profiles_as_facts():
    items = client.get("/api/queue").json()["items"]
    item = next(i for i in items if i["id"] == "demo-11")
    assert item["profiles"]["reporter"]["filed"] == 31
    assert item["profiles"]["reported"]["against_confirmed"] == 9


def test_short_history_has_no_profile():
    from copilot import reputation
    assert reputation.profile("no-such-player") is None
    data = reputation.build([{"kind": "complaint", "reporter_hash": "a", "reported_hash": "b", "verdict": "approved", "messages": []}])
    assert data["filed"]["a"]["approved"] == 1 and data["against"]["b"]["total"] == 1


def test_profile_never_changes_the_answer():
    from copilot.pipeline import triage
    req = {"kind": "complaint", "messages": [{"text": "оскорбил меня, скрин", "attachments": 1}]}
    assert triage(req) == triage({**req, "reporter_hash": "demo-reporter-2"})


def test_admin_page_served():
    r = client.get("/admin")
    assert r.status_code == 200 and "Support Copilot" in r.text


def test_queue_sorted_by_priority_with_series():
    items = client.get("/api/queue").json()["items"]
    order = [i["triage"]["priority"] for i in items]
    assert order == sorted(order)
    assert any(i["series"] == 3 for i in items)


def test_queue_rules_have_real_punishments():
    items = client.get("/api/queue").json()["items"]
    card = next(r for i in items for r in i["rules"] if r["ref"] == "2.1 ОП")
    assert any("MUTE" in p for p in card["punishments"])


def test_feedback_saved_with_edit_flag(tmp_path, monkeypatch):
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(admin, "FEEDBACK_PATH", path)
    body = {"ticket_id": "demo-01", "action": "send", "draft_before": "a", "draft_after": "b"}
    assert client.post("/api/feedback", json=body).json()["ok"] is True
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["edited"] is True
    assert client.get("/api/stats").json() == {"total": 1, "sent": 1, "edited": 1, "escalated": 0}


def test_generate_under_admin_verdict():
    r = client.post("/api/generate/demo-01", json={"verdict": "need_evidence"})
    body = r.json()
    assert r.status_code == 200 and body["draft_reply"]["text"]
    assert client.post("/api/generate/demo-01", json={"verdict": "ban_everyone"}).status_code == 422
    assert client.post("/api/generate/nope", json={"verdict": "approved"}).status_code == 404
