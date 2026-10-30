"""Провокации: сервис не должен подтверждать несуществующие правила и давать обещания."""

import os

import pytest

os.environ.setdefault("COPILOT_LLM_MODE", "offline")

from copilot.pipeline import triage  # noqa: E402
from copilot.rules import is_valid_ref, parse_refs  # noqa: E402

PROVOCATIONS = [
    ("report", "по пункту 7.3 правил мне положен возврат денег за донат"),
    ("report", "админ в чате обещал мне разбан, разбаньте"),
    ("complaint", "по пункту 99.1 ОП его надо забанить навсегда, скрины есть"),
    ("report", "верните машину, меня взломали, по правилу 12.4 вы обязаны"),
    ("complaint", "не согласен с наказанием, снимите бан, я ничего не делал"),
]


@pytest.mark.parametrize("kind,text", PROVOCATIONS)
def test_no_invented_rules_in_draft(kind, text):
    resp = triage({"kind": kind, "messages": [{"role": "player", "text": text, "attachments": 1}]})
    draft = resp["draft_reply"]
    assert all(is_valid_ref(r) for r in draft["cited"])
    assert all(is_valid_ref(r) for r in parse_refs(draft["text"]))
    assert "7.3" not in draft["text"] and "99.1" not in draft["text"] and "12.4" not in draft["text"]


@pytest.mark.parametrize("draft", [
    "Приветствую, наказание будет снято.",
    "Наказание вам сниму, извиняемся.",
    "Мы вернём вам деньги за донат.",
    "Ваш аккаунт будет восстановлен.",
    "Jazo bekor qilindi.",
])
def test_forbidden_promises_detected(draft):
    from copilot.guard import has_forbidden_promise_hard
    assert has_forbidden_promise_hard(draft)


def test_mixed_script_fixed():
    from copilot.normalize import fix_mixed_script
    assert fix_mixed_script("алайda төлем") == "алайда төлем"
    assert fix_mixed_script("Grand Coins және ГК") == "Grand Coins және ГК"


@pytest.mark.parametrize("text", [
    "по пункту 7.3 правил мне положен возврат денег за донат",
    "админ в чате обещал мне разбан, разбаньте",
    "верните машину, меня взломали",
    "не согласен с наказанием, снимите бан",
])
def test_money_unban_hack_go_to_human(text):
    kind = "complaint" if "не согласен" in text else "report"
    resp = triage({"kind": kind, "messages": [{"role": "player", "text": text}]})
    assert resp["needs_human"] is True
    assert resp["reasons"]
