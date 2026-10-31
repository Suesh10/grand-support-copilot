import json

import pytest
from fastapi.testclient import TestClient

from copilot import pipeline, predict
from copilot.api import app
from copilot.normalize import detect_lang, normalize
from copilot.rules import filter_valid, parse_refs

client = TestClient(app)

CONTRACT_KEYS = {"lang", "category", "priority", "is_spam_or_duplicate", "extracted",
                 "draft_reply", "needs_human", "confidence", "reasons"}


def test_contract_example_from_tz():
    req = {"kind": "complaint", "messages": [{"role": "player", "attachments": 2,
           "text": "Arman_Petrov оскорблял меня и мою семью в чате, скрины есть, 2.1 ОП"}]}
    r = client.post("/triage", json=req)
    assert r.status_code == 200
    body = r.json()
    assert CONTRACT_KEYS <= body.keys()
    assert body["lang"] == "ru"
    assert body["category"] == "complaint.insult"
    assert body["extracted"]["nickname"] == "Arman_Petrov"
    assert body["extracted"]["rule_refs"] == ["2.1"]
    assert body["draft_reply"]["cited"] == ["2.1"]
    assert body["extracted"]["has_evidence"] is True
    assert body["needs_human"] is True


def test_cp1251_kazakh_letters_restored():
    assert normalize("ќалай кґмек") == "қалай кғмек"
    assert detect_lang("маѕан кґмектесіѕізші") == "kk"


@pytest.mark.parametrize("text,server,lang", [
    ("қайда", None, "kk"),  # короткий текст, одна казахская буква
    ("он маған қарсы келді, ақша бермеді, ол мені алдады", None, "kk"),  # «он» не делает текст русским
    ("сегодня он меня оскорбил в чате, это қ случайно попала в текст, прошу разобраться", None, "ru"),
    ("допоможіть будь ласка", None, "ru"),
    ("sababsiz ban berildi", None, "uz"),
    ("salom", "uz", "uz"),  # текст не говорит ничего, сервер подсказывает
    ("salom", None, "und"),
    ("помогите", "uz", "ru"),  # русский текст на узбекском сервере остаётся русским
])
def test_language_of_short_and_mixed_texts(text, server, lang):
    assert detect_lang(text, server) == lang


def test_bare_rule_number_defaults_to_general_rules():
    assert parse_refs("нарушил 2.1") == ["2.1 ОП"]
    assert parse_refs("1.2 GZ") == ["1.2 GZ"]


def test_hallucinated_refs_are_dropped():
    assert filter_valid(["2.1 ОП", "99.9 ОП", "2.1 XYZ"]) == ["2.1 ОП"]


def test_payment_always_needs_human():
    req = {"kind": "report", "messages": [{"role": "player", "text": "задонатил 5000, деньги не пришли"}]}
    body = client.post("/triage", json=req).json()
    assert body["needs_human"] is True


def test_empty_report_is_spam():
    body = client.post("/triage", json={"kind": "report", "messages": [{"text": "+"}]}).json()
    assert body["is_spam_or_duplicate"] is True
    assert body["category"] == "report.offtopic"


def test_complaints_always_cite_a_rule():
    for text, ref in [("он читер, летает", "5.2"), ("обманул на машину, не отдал деньги", "4.1")]:
        body = client.post("/triage", json={"kind": "complaint", "messages": [{"text": text, "attachments": 1}]}).json()
        assert body["draft_reply"]["cited"], text
        assert body["category"] in ("complaint.cheat", "complaint.scam")


def test_rag_finds_rule_by_meaning():
    from copilot.rag import search
    refs = [r for r, _ in search("продаёт игровую валюту за реальные деньги", k=5)]
    assert "4.4 ОП" in refs


def test_duplicate_complaint_same_pair_within_an_hour():
    from copilot.dedupe import Deduper
    d = Deduper()
    t = {"reporter_hash": "a", "reported_hash": "b", "created_at": "2026-10-01T10:00:00", "messages": []}
    assert d.is_duplicate(t) is False
    assert d.is_duplicate({**t, "created_at": "2026-10-01T10:40:00"}) is True
    assert d.is_duplicate({**t, "created_at": "2026-10-01T15:00:00"}) is False
    assert d.is_duplicate({**t, "reporter_hash": "c"}) is False


def test_duplicate_flag_reaches_contract():
    body = client.post("/triage", json={"kind": "complaint", "reporter_hash": "x", "reported_hash": "y",
                                        "messages": [{"text": "оскорбил меня, скрин", "attachments": 1}]}).json()
    assert body["is_spam_or_duplicate"] is False
    body = client.post("/triage", json={"kind": "complaint", "reporter_hash": "x", "reported_hash": "y",
                                        "messages": [{"text": "оскорбил меня, скрин", "attachments": 1}]}).json()
    assert body["is_spam_or_duplicate"] is True


def test_predict_survives_broken_lines(tmp_path, monkeypatch):
    src = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    lines = [
        json.dumps({"ticket_id": "ok", "kind": "report", "messages": [{"role": "player", "text": "застрял в текстурах"}]}),
        "{битый json",
        "[1, 2]",
        json.dumps({"ticket_id": "null-text", "kind": "report", "reporter_hash": "a", "messages": [{"role": "player", "text": None}]}),
        json.dumps({"ticket_id": "no-messages", "kind": "complaint", "messages": None}),
        json.dumps({"ticket_id": "bad-images", "kind": "complaint", "images_count": "много", "messages": [{"role": "player", "text": "скрин"}]}),
    ]
    src.write_text("\n".join(lines), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["predict", "--in", str(src), "--out", str(out)])
    predict.main()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["ticket_id"] for r in rows] == ["ok", "null-text", "no-messages", "bad-images"]
    assert all({"lang", "category", "priority", "draft_reply", "needs_human"} <= set(r) for r in rows)
    assert rows[3]["needs_human"] is True


def test_failure_returns_contract_for_human(monkeypatch):
    def boom(_):
        raise RuntimeError("сбой")
    monkeypatch.setattr(pipeline, "triage_full", boom)
    resp = pipeline.triage({"kind": "complaint", "messages": [{"text": "x"}]})
    assert resp["needs_human"] is True and resp["category"] == "complaint.other" and resp["reasons"]


def report(text, reporter="a", at="2026-10-30T12:00:00"):
    return {"reporter_hash": reporter, "created_at": at, "messages": [{"role": "player", "text": text}]}


def test_similar_reports_within_an_hour_are_one_problem():
    from copilot.dedupe import Deduper
    d = Deduper()
    assert d.is_duplicate(report("застрял в текстурах")) is False
    assert d.is_duplicate(report("помогите застрял в текстурах", at="2026-10-30T12:10:00")) is True
    assert d.is_duplicate(report("застрял в текстурах", reporter="b")) is False  # другой игрок
    assert d.is_duplicate(report("как устроиться в полицию", at="2026-10-30T12:20:00")) is False  # другая проблема
    assert d.is_duplicate(report("застрял в текстурах", at="2026-10-30T14:00:00")) is False  # окно прошло
