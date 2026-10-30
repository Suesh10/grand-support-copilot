"""Проверка самого проверяющего: ноль ошибок что-то значит, только если он ловит намеренные поломки."""

import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("audit", Path(__file__).parent.parent / "scripts" / "audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

TICKET = {"kind": "complaint", "reported_nick": "Arman_Petrov",
          "messages": [{"role": "player", "text": "Arman_Petrov оскорбил меня, скрин есть"}]}
GOOD = {
    "lang": "ru", "category": "complaint.insult", "priority": "p2", "is_spam_or_duplicate": False,
    "extracted": {"nickname": "Arman_Petrov", "rule_refs": ["2.1"], "has_evidence": True, "server": None},
    "draft_reply": {"lang": "ru", "text": "Здравствуйте! Жалоба принята, проверим по пункту 2.1 ОП.", "cited": ["2.1"]},
    "needs_human": True, "confidence": 0.9, "reasons": ["решение за администратором"],
}


def errors(ticket, response):
    return {code for level, code, _ in audit.check(ticket, response, {}) if level == "ERROR"}


def broken(**changes):
    r = copy.deepcopy(GOOD)
    for path, value in changes.items():
        keys = path.split("__")
        node = r
        for key in keys[:-1]:
            node = node[key]
        node[keys[-1]] = value
    return r


def test_good_answer_has_no_errors():
    assert errors(TICKET, GOOD) == set()


@pytest.mark.parametrize("change,code", [
    ({"draft_reply__cited": ["99.9"]}, "цитата не из rules.json"),
    ({"draft_reply__cited": []}, "нет цитаты там, где правила нужны"),
    ({"draft_reply__text": "Здравствуйте! Нарушен пункт 9.9 ОП правил проекта."}, "пункт в тексте не указан в cited"),
    ({"draft_reply__text": "Здравствуйте! Наказание будет снято, пункт 2.1 ОП."}, "обещание разбана или возврата"),
    ({"draft_reply__text": "Игрок Oleg_Ivanov5 нарушил пункт 2.1 ОП правил."}, "чужой ник в черновике"),
    ({"draft_reply__text": "Здравствуйте, <url> пункт 2.1 ОП проверим."}, "мусор в тексте"),
    ({"draft_reply__text": "Hello, your complaint is accepted, rule 2.1 ОП."}, "латиница в кириллическом черновике"),
    ({"needs_human": False, "draft_reply__text": "Игрок будет наказан по пункту 2.1 ОП правил."}, "наказание обещано без needs_human"),
    ({"reasons": []}, "needs_human без причины"),
    ({"category": "report.help"}, "категория не того вида"),
    ({"category": "complaint.bad"}, "категория не из taxonomy"),
    ({"priority": "p9"}, "неверный приоритет"),
    ({"confidence": 2}, "уверенность вне 0..1"),
])
def test_catches_broken_answer(change, code):
    assert code in errors(TICKET, broken(**change))


def test_catches_payment_sent_to_auto():
    ticket = {"kind": "report", "messages": [{"role": "player", "text": "задонатил, деньги списали"}]}
    r = broken(category="report.question", needs_human=False, reasons=[], priority="p3")
    r["draft_reply"] = {"lang": "ru", "text": "Здравствуйте! Вопрос принят.", "cited": []}
    assert "платёж ушёл в авто" in errors(ticket, r)
