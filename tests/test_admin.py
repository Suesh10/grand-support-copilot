"""Интерфейс админа: очередь, серии и сохранение действий как обучающего сигнала."""

import json
import os

os.environ.setdefault("COPILOT_LLM_MODE", "offline")

from fastapi.testclient import TestClient  # noqa: E402

from copilot import admin, llm  # noqa: E402
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
    data = reputation.build([{"kind": "complaint", "reporter_hash": "a", "reported_hash": "b", "verdict": "approved", "violation": "2.1 ОП", "messages": []}])
    assert data["filed"]["a"]["approved"] == 1 and data["against"]["b"]["total"] == 1


def test_profile_never_changes_the_answer():
    from copilot.pipeline import triage
    req = {"kind": "complaint", "messages": [{"text": "оскорбил меня, скрин", "attachments": 1}]}
    assert triage(req) == triage({**req, "reporter_hash": "demo-reporter-2"})


def test_profile_separates_own_and_against_and_comment_adds_new_info():
    from copilot import reputation
    p = reputation.profile("demo-reporter-2")
    assert p["total"] == 43 and p["against_total"] == 9
    assert p["comment"].startswith("Его жалобы редко подтверждаются.")
    assert not any(ch.isdigit() for ch in p["comment"])
    accused = reputation.profile("demo-accused-1")
    assert accused["comment"] == "Жалобы на него обычно подтверждаются."
    assert accused["topics"][0] == {"code": "complaint.insult", "count": 11}


def test_appeal_is_not_counted_against_player():
    from copilot import reputation
    t = {"kind": "complaint", "reporter_hash": "a", "reported_hash": "admin", "verdict": "appeal_rejected", "messages": []}
    assert "admin" not in reputation.build([t])["against"]


def test_memory_accumulates_and_survives(tmp_path, monkeypatch):
    from copilot import reputation
    monkeypatch.setattr(reputation, "MEMORY_PATH", tmp_path / "memory.json")
    for _ in range(5):
        reputation.remember("new-player", "complaint.insult")
    p = reputation.profile("new-player")
    assert p["new"] == 5 and p["topics"][0] == {"code": "complaint.insult", "count": 5}


def test_admin_type_goes_to_profile(tmp_path, monkeypatch):
    from copilot import reputation
    monkeypatch.setattr(reputation, "MEMORY_PATH", tmp_path / "memory.json")
    monkeypatch.setattr(admin, "FEEDBACK_PATH", tmp_path / "feedback.jsonl")
    body = {"ticket_id": "x", "action": "send", "category": "complaint.cheat", "ai_category": "complaint.dm", "reported_hash": "h1"}
    client.post("/api/feedback", json=body)
    assert reputation.read_memory()["h1"]["topics"] == {"complaint.cheat": 1}
    client.post("/api/feedback", json={**body, "action": "escalate", "reported_hash": "h2"})
    assert "h2" not in reputation.read_memory()


def test_admin_notes_template(tmp_path, monkeypatch):
    from copilot import reputation
    monkeypatch.setattr(reputation, "NOTES_PATH", tmp_path / "notes.json")
    r = client.post("/api/notes", json={"nick": "Arman_Petrov", "category": "complaint.insult", "status": "Наблюдение", "comment": "тест"})
    note = r.json()
    assert note["id"] == 1 and client.get("/api/queue").json()["notes"][0]["nick"] == "Arman_Petrov"
    assert client.post("/api/notes", json={"nick": "x", "category": "c", "status": "s"}).status_code == 422
    client.delete(f"/api/notes/{note['id']}")
    assert client.get("/api/queue").json()["notes"] == []


def test_saving_profile_looks_up_player(tmp_path, monkeypatch):
    from copilot import reputation
    monkeypatch.setattr(reputation, "NOTES_PATH", tmp_path / "notes.json")
    note = {"category": "complaint.insult", "status": "Наблюдение"}
    found = client.post("/api/notes", json={**note, "nick": "arman_petrov"}).json()["lookup"]
    assert found["found"] is True and found["profile"]["against"] == 14
    assert "уже есть обращения: 11" in found["summary"]
    other = client.post("/api/notes", json={**note, "nick": "Arman_Petrov", "category": "complaint.scam"}).json()["lookup"]
    assert "не было" in other["summary"]
    missing = client.post("/api/notes", json={**note, "nick": "Nobody_Known"}).json()["lookup"]
    assert missing == {"found": False, "summary": "Данных об этом игроке нет."}


def test_archive_review_time_and_delete_request(tmp_path, monkeypatch):
    import time
    monkeypatch.setattr(admin, "FEEDBACK_PATH", tmp_path / "f.jsonl")
    monkeypatch.setattr(admin, "ARCHIVE_PATH", tmp_path / "a.json")
    body = {"ticket_id": "demo-06", "action": "send", "category": "report.help", "nick": "Oleg_Ivanov", "review_seconds": 42}
    client.post("/api/feedback", json=body)
    data = client.get("/api/archive").json()
    assert data["items"][0]["review_seconds"] == 42 and data["to_delete"] == []
    assert "demo-06" not in [i["id"] for i in client.get("/api/queue").json()["items"]]
    old = admin.read_archive()
    old[0]["closed_at"] = time.time() - 31 * 86400
    admin.write_archive(old)
    assert client.get("/api/archive").json()["to_delete"] == ["demo-06"]
    assert len(admin.read_archive()) == 1  # сам сайт не удаляет
    assert client.delete("/api/archive/demo-06").json()["ok"] is True
    assert admin.read_archive() == []
    assert client.delete("/api/archive/demo-06").status_code == 404


def test_undo_returns_ticket_to_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(admin, "FEEDBACK_PATH", tmp_path / "f.jsonl")
    monkeypatch.setattr(admin, "ARCHIVE_PATH", tmp_path / "a.json")
    body = {"ticket_id": "demo-06", "action": "send", "category": "report.help"}
    client.post("/api/feedback", json=body)
    client.post("/api/feedback", json={**body, "action": "undo"})
    assert "demo-06" in [i["id"] for i in client.get("/api/queue").json()["items"]]


def test_deleted_ticket_does_not_return_to_queue():
    client.post("/api/feedback", json={"ticket_id": "demo-06", "action": "send", "category": "report.help"})
    assert client.delete("/api/archive/demo-06").json()["ok"] is True
    assert "demo-06" not in [i["id"] for i in client.get("/api/queue").json()["items"]]


def test_escalated_stays_in_archive_and_cannot_be_deleted():
    import time
    client.post("/api/feedback", json={"ticket_id": "demo-06", "action": "escalate", "category": "report.help"})
    old = admin.read_archive()
    old[0]["closed_at"] = time.time() - 31 * 86400
    admin.write_archive(old)
    data = client.get("/api/archive").json()
    assert data["items"][0]["deletable"] is False and data["to_delete"] == []
    assert client.delete("/api/archive/demo-06").status_code == 409
    assert len(admin.read_archive()) == 1


def test_merged_can_be_deleted():
    client.post("/api/feedback", json={"ticket_id": "demo-06", "action": "merge", "category": "report.help"})
    assert client.get("/api/archive").json()["items"][0]["deletable"] is True


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


def test_accused_reply_becomes_appeal():
    ticket = {"ticket_id": "t1", "messages": [{"role": "player", "text": "обманул"}, {"role": "reported_player", "text": "нет"}],
              "reported_nick": "Oleg_Smirnov", "attachments": [{"url": "a.png"}, {"url": "b.png", "from": "reported_player"}]}
    appeal = admin.appeal_from(ticket)
    assert appeal["ticket_id"] == "t1-appeal" and appeal["appeal_of"] == "t1"
    assert [m["text"] for m in appeal["messages"]] == ["нет"]
    assert [f["url"] for f in appeal["attachments"]] == ["b.png"]
    assert admin.appeal_from({"ticket_id": "t2", "messages": [{"role": "player", "text": "x"}]}) is None
    item = next(x for x in admin.load_queue() if x["appeal_of"])
    assert item["triage"]["category"] == "complaint.admin" and item["triage"]["needs_human"]
    assert item["triage"]["draft_reply"]["cited"] == []


def test_feedback_saved_with_edit_flag(tmp_path, monkeypatch):
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(admin, "FEEDBACK_PATH", path)
    body = {"ticket_id": "demo-01", "action": "send", "draft_before": "a", "draft_after": "b"}
    assert client.post("/api/feedback", json=body).json()["ok"] is True
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["edited"] is True
    stats = client.get("/api/stats").json()
    assert (stats["sent"], stats["edited"], stats["escalated"]) == (1, 1, 0)


def test_generate_under_admin_verdict():
    r = client.post("/api/generate/demo-01", json={"verdict": "need_evidence"})
    body = r.json()
    assert r.status_code == 200 and body["draft_reply"]["text"]
    assert client.post("/api/generate/demo-01", json={"verdict": "ban_everyone"}).status_code == 422
    assert client.post("/api/generate/nope", json={"verdict": "approved"}).status_code == 404


def test_llm_cache_saves_quota(tmp_path, monkeypatch):
    calls = []

    class Models:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return type("R", (), {"text": "перевод"})()

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "_CLIENT", type("C", (), {"models": Models()})())
    monkeypatch.setattr(llm, "CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(llm, "_cache_on", True)
    assert llm.translate("salom") == "перевод" and llm.translate("salom") == "перевод"
    assert len(calls) == 1


def test_llm_outage_is_visible(monkeypatch):
    class Models:
        def generate_content(self, **kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm, "enabled", lambda: True)
    monkeypatch.setattr(llm, "_CLIENT", type("C", (), {"models": Models()})())
    monkeypatch.setattr(llm, "_cache_on", False)
    monkeypatch.setattr(llm, "_health", {"ok": 0, "errors": 0, "last_error": None, "last_error_at": None, "last_ok_at": None})
    assert llm.translate("salom") is None
    assert llm.status()["state"] == "down" and "429" in llm.status()["last_error"]
    assert client.get("/health").json()["llm"]["state"] == "down"


def test_unknown_action_is_rejected():
    assert client.post("/api/feedback", json={"ticket_id": "x", "action": "взломать"}).status_code == 422


def test_facts_are_marked_in_text():
    from copilot.extract import spans
    text = "Arman_Petrov нарушил 2.1 ОП и 99.1, видео есть, сервер 5"
    marks = {text[m["start"]:m["end"]]: m["kind"] for m in spans(text)}
    assert marks["Arman_Petrov"] == "nick" and marks["видео"] == "proof"
    assert "2.1 ОП" in marks and not any("99.1" in k for k in marks)
    proof = "вот доказательства"
    assert [proof[m["start"]:m["end"]] for m in spans(proof) if m["kind"] == "proof"] == ["доказательства"]


def test_history_shows_only_counts():
    item = next(x for x in client.get("/api/queue").json()["items"] if x["id"] == "demo-11")
    history = item["history"]
    assert history is None or (history["n"] >= 5 and all(isinstance(n, int) for _, n in history["outcomes"]))
    assert history is None or set(history) == {"n", "outcomes", "punishment"}  # тексты обращений наружу не выходят


def test_edit_teaches_similar_ticket_and_undo_forgets(monkeypatch):
    from copilot.pipeline import triage_full
    client.get("/api/queue")
    source = next(t for t in admin.raw_tickets() if t.get("ticket_id") == "demo-11")
    twin = {**source, "ticket_id": "twin", "reported_nick": "Oleg_Smirnov",
            "messages": [{**m, "text": m["text"].replace("Arman_Petrov", "Oleg_Smirnov")} for m in source["messages"]]}
    monkeypatch.setattr(admin, "raw_tickets", lambda: (source, twin))
    reply = "Приветствую. Игрок Arman_Petrov будет наказан по пункту 2.1 ОП за мат в чате."
    body = {"ticket_id": "demo-11", "action": "send", "draft_before": "старый", "draft_after": reply,
            "category": "complaint.insult", "nick": "Arman_Petrov"}
    learned = client.post("/api/feedback", json=body).json()["learned"]
    assert [x["id"] for x in learned] == ["twin"] and "Oleg_Smirnov" in learned[0]["draft"]
    assert learn_has("demo-11")
    client.post("/api/feedback", json={"ticket_id": "demo-11", "action": "undo"})
    assert not learn_has("demo-11")
    resp, meta = triage_full({"kind": "complaint", "messages": [{"text": source["messages"][0]["text"], "attachments": 1}]})
    assert meta["draft_source"] != "lesson"


def learn_has(ticket_id):
    from copilot import learn
    return any(x["ticket_id"] == ticket_id for x in learn._read())


def test_lesson_with_invented_rule_is_ignored():
    from copilot import learn
    from copilot.pipeline import triage_full
    client.get("/api/queue")
    text = "Arman_Petrov оскорблял меня в чате, скрин есть"
    learn.add("x", text, "Игрок наказан по пункту 99.9 ОП.", "complaint.insult", "ru", None)
    _, meta = triage_full({"kind": "complaint", "messages": [{"text": text, "attachments": 1}]})
    assert "99.9" not in meta.get("cited_full", [])


def test_stats_count_only_what_stayed_closed():
    body = {"ticket_id": "demo-06", "action": "send", "draft_before": "a", "draft_after": "a", "category": "report.help", "review_seconds": 40}
    client.post("/api/feedback", json=body)
    client.post("/api/feedback", json={**body, "ticket_id": "demo-09", "draft_after": "b", "review_seconds": 80})
    stats = client.get("/api/stats").json()
    assert stats["sent"] == 2 and stats["edited"] == 1 and stats["median_seconds"] == 80
    client.post("/api/feedback", json={"ticket_id": "demo-09", "action": "undo"})
    stats = client.get("/api/stats").json()
    assert stats["sent"] == 1 and stats["edited"] == 0
    assert all(isinstance(n, int) for _, n in stats["open_by_category"])


def test_accepted_template_becomes_a_lesson(tmp_path, monkeypatch):
    from copilot import clusters
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps([{"id": 1, "size": 500, "share": 0.1, "category": "report.help", "lang": "ru",
                                 "terms": ["застрял", "текстуры"], "reply": "Приветствую, вытащу вас через минуту."}], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(clusters, "CANDIDATES_PATH", path)
    assert client.get("/api/templates").json()["items"][0]["decision"] is None
    assert client.post("/api/templates/9", json={"decision": "accepted"}).status_code == 404
    assert client.post("/api/templates/1", json={"decision": "accepted"}).json()["ok"] is True
    from copilot import learn
    assert learn.lessons()[0]["ticket_id"] == "template-1"
    client.post("/api/templates/1", json={"decision": "rejected"})
    assert client.get("/api/templates").json()["items"] == []


def test_clusters_refuse_unsafe_replies():
    from copilot.clusters import fits
    assert fits("Приветствую, спешу на помощь.")
    assert not fits("Приветствую, вернём вам деньги за донат.")
    assert not fits("Игрок Arman_Petrov будет наказан.")
    assert not fits("Мут 30 минут по пункту 99.9 ОП, готово.")


def test_blind_review_hides_author_until_scored(tmp_path):
    review = [{"ticket_id": f"t{i}", "lang": "ru", "player": "текст", "draft": "ЧЕРНОВИК", "admin": "АДМИН"} for i in range(2)]
    admin.REVIEW_PATH.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in review), encoding="utf-8")
    item = client.get("/api/review").json()["item"]
    assert {item["a"], item["b"]} == {"ЧЕРНОВИК", "АДМИН"} and "source" not in item and "draft" not in item
    draft_side = "a" if item["a"] == "ЧЕРНОВИК" else "b"
    saved = client.post("/api/review", json={"ticket_id": item["ticket_id"], "a": 5 if draft_side == "a" else 3, "b": 3 if draft_side == "a" else 5}).json()
    assert saved["draft_was"] == draft_side
    data = client.get("/api/review").json()
    assert data["done"] == 1 and data["summary"]["draft"] == 5 and data["summary"]["admin"] == 3
    assert client.post("/api/review", json={"ticket_id": "t0", "a": 9, "b": 1}).status_code == 422


def test_review_is_hidden_without_local_set():
    assert client.get("/api/review").json() == {"available": False}


def test_every_player_has_a_mini_profile():
    from copilot import reputation
    new = reputation.mini_profile("no-such-player")
    assert new["filed"] == 0 and new["comment"] == "Новый игрок: обращений пока нет."
    assert reputation.mini_profile(None)["comment"] == "Данных об этом игроке нет."
    reputation.remember("rare-player", "complaint.insult")
    rare = reputation.mini_profile("rare-player")
    assert rare["against_total"] == 1 and rare["comment"] == "Обращений мало, выводы делать рано."
    assert reputation.profile("no-such-player") is None  # выводы по-прежнему только при достаточной истории
    assert all(x["profiles"]["reporter"] for x in client.get("/api/queue").json()["items"])


def test_only_one_llm_client_under_parallel_load(monkeypatch):
    import threading
    import time
    made = []

    def build():
        time.sleep(0.02)
        made.append(object())
        return made[-1]

    monkeypatch.setattr(llm, "_CLIENT", None)
    monkeypatch.setattr(llm, "_client", build)
    threads = [threading.Thread(target=llm._shared_client) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(made) == 1
