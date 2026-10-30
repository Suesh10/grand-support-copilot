from fastapi.testclient import TestClient

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
    assert body["extracted"]["rule_refs"] == ["2.1 ОП"]
    assert body["extracted"]["has_evidence"] is True
    assert body["needs_human"] is True


def test_cp1251_kazakh_letters_restored():
    assert normalize("ќалай кґмек") == "қалай кғмек"
    assert detect_lang("маѕан кґмектесіѕізші") == "kk"


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
