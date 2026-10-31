"""Придирчивая проверка: make audit

Идёт по каждому обращению и сверяет ответ с требованиями ТЗ. Ничего не прощает:
любое нарушение печатается с примером, код возврата 1, если есть хоть одно.
Строгие правила (ERROR) — прямые требования ТЗ, WARN — вероятные проблемы качества.
Примеры с текстом игроков пишутся только в artifacts/, в репозиторий не попадают.
"""

import argparse
import json
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot import config, llm  # noqa: E402
from copilot.dedupe import Deduper  # noqa: E402
from copilot.guard import FORBIDDEN_RE, PROMISE_RE  # noqa: E402
from copilot.normalize import KK_LETTERS  # noqa: E402
from copilot.pipeline import triage_full  # noqa: E402
from copilot.predict import ticket_to_request  # noqa: E402
from copilot.rag import NEEDS_CITATION  # noqa: E402
from copilot.rules import is_contract_ref, punishments  # noqa: E402
from copilot.signals import APPEAL_RE, HACK_RE, PAYMENT_RE  # noqa: E402

TAXONOMY = json.loads(config.TAXONOMY_PATH.read_text(encoding="utf-8"))
CATEGORIES = {c["code"] for c in TAXONOMY["categories"]}
ALWAYS_HUMAN = set(TAXONOMY["needs_human_always"])
LANGS = {"ru", "kk", "uz", "en", "es", "pt", "und", "lat"}

NUMBER_RE = re.compile(r"(?<![\d.:])\d{1,2}(?:\.\d{1,2}){1,2}(?![\d:])")
NICK_RE = re.compile(r"\b[A-Z][a-z]+_[A-Z][a-z]+\d{0,3}\b")
LEFTOVER_RE = re.compile(r"<(url|digits|email|handle|nick)>|#\s*\d|\{\w*\}|\bигрок игрок\b|\s,|,\.|\.\.(?!\.)|\(ая\)", re.I)
TERM_RE = re.compile(r"\b\d+\s*(минут|мин|час|дн|день|дня|дней|kun|daqiqa|күн|минут)", re.I)
DECISION_RE = re.compile(r"одобрен|отклонен|закрыто|рассмотрена и|rad etildi|tasdiqlandi|yopildi|мақұлданды|қабылданбады", re.I)
OPEN_RE = re.compile(r"будет рассмотрен|передан\w* администрац|на рассмотрение|ожидайте|ko'rib chiqiladi|yuborildi|жіберілді", re.I)


def cyrillic_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum("а" <= c.lower() <= "я" or c in KK_LETTERS for c in letters) / max(len(letters), 1)


def check(t: dict, r: dict, meta: dict) -> list[tuple[str, str, str]]:
    """Вернуть нарушения (уровень, код, деталь)."""
    out = []
    bad = lambda level, code, detail="": out.append((level, code, detail))  # noqa: E731
    d, f = r.get("draft_reply", {}), r.get("extracted", {})
    text = d.get("text", "")
    player = " ".join(m.get("text", "") for m in t["messages"] if m.get("role") != "admin")

    # Контракт
    for key, kind in {"lang": str, "category": str, "priority": str, "is_spam_or_duplicate": bool, "extracted": dict,
                      "draft_reply": dict, "needs_human": bool, "confidence": (int, float), "reasons": list}.items():
        if not isinstance(r.get(key), kind):
            bad("ERROR", "контракт: неверное поле", key)
    for key in ("nickname", "rule_refs", "has_evidence", "server"):
        if key not in f:
            bad("ERROR", "контракт: нет поля extracted", key)
    for key in ("lang", "text", "cited"):
        if key not in d:
            bad("ERROR", "контракт: нет поля draft_reply", key)
    if r.get("category") not in CATEGORIES:
        bad("ERROR", "категория не из taxonomy", r.get("category"))
    if r.get("category", ".").split(".")[0] != t["kind"]:
        bad("ERROR", "категория не того вида", r.get("category"))
    if r.get("priority") not in ("p0", "p1", "p2", "p3"):
        bad("ERROR", "неверный приоритет", r.get("priority"))
    if r.get("lang") not in LANGS:
        bad("ERROR", "неверный язык", r.get("lang"))
    if not 0 <= r.get("confidence", -1) <= 1:
        bad("ERROR", "уверенность вне 0..1", r.get("confidence"))

    # Цитаты
    for ref in d.get("cited", []):
        if not is_contract_ref(ref):
            bad("ERROR", "цитата не из rules.json", ref)
    for ref in f.get("rule_refs", []):
        if not is_contract_ref(ref):
            bad("ERROR", "rule_refs не из rules.json", ref)
    numbers = set(NUMBER_RE.findall(text))
    for number in numbers - set(d.get("cited", [])):
        bad("ERROR", "пункт в тексте не указан в cited", number)
    if r.get("category") in NEEDS_CITATION and not d.get("cited"):
        bad("ERROR", "нет цитаты там, где правила нужны", r.get("category"))
    for ref in set(d.get("cited", [])) - numbers:
        bad("WARN", "цитата в cited не упомянута в тексте", ref)

    # Обещания и needs_human
    if FORBIDDEN_RE.search(text):
        bad("ERROR", "обещание разбана или возврата", text[:80])
    if PROMISE_RE.search(text) and not r.get("needs_human"):
        bad("ERROR", "наказание обещано без needs_human", text[:80])
    if r.get("category") in ALWAYS_HUMAN and not r.get("needs_human"):
        bad("ERROR", "категория всегда для человека ушла в авто", r.get("category"))
    for name, rx in (("платёж", PAYMENT_RE), ("взлом", HACK_RE), ("апелляция", APPEAL_RE)):
        if rx.search(player) and not r.get("needs_human"):
            bad("ERROR", f"{name} ушёл в авто", player[:80])
    if r.get("needs_human") and not r.get("reasons"):
        bad("ERROR", "needs_human без причины", "")
    if r.get("is_spam_or_duplicate") and r.get("needs_human") and r.get("category") == "report.offtopic":
        bad("WARN", "оффтоп отправлен человеку", player[:60])

    # Выдумки
    allowed_nicks = set(NICK_RE.findall(player))
    if t.get("reported_nick"):
        allowed_nicks.add(t["reported_nick"])
    for nick in set(NICK_RE.findall(text)) - allowed_nicks:
        bad("ERROR", "чужой ник в черновике", nick)
    # Срок разрешён только дословно из пункта правил, который цитирует черновик.
    allowed_terms = " ".join(p for ref in meta.get("cited_full", []) for p in punishments(ref))
    term = TERM_RE.search(text)
    if term and not TERM_RE.search(player) and not any(line.strip(" .") in text for line in re.split(r":", allowed_terms)[1:] if line):
        if term.group(0) not in allowed_terms:
            bad("ERROR", "срок наказания не из цитируемого пункта", term.group(0))
    if meta.get("proposal") and not r.get("needs_human"):
        bad("ERROR", "предложение решения без человека", text[:80])
    if DECISION_RE.search(text) and r.get("needs_human") and not meta.get("proposal"):
        bad("WARN", "черновик утверждает решение до проверки", DECISION_RE.search(text).group(0))
    if DECISION_RE.search(text) and OPEN_RE.search(text):
        bad("WARN", "противоречие: закрыто и на рассмотрении", text[:80])

    # Язык
    lang = r.get("lang")
    if lang in ("kk", "uz", "en", "es", "pt") and d.get("lang") != lang:
        bad("ERROR", "черновик не на языке игрока", f"{lang}->{d.get('lang')}")
    plain = re.sub(r"\b\d[\d.]*\s*(ОП|ЖБ|GZ|ПГО|ОПГ)\b", "", text)
    if d.get("lang") in ("uz", "en", "es", "pt") and cyrillic_share(plain) > 0.2:
        bad("ERROR", "кириллица в черновике на латинице", plain[:70])
    if d.get("lang") in ("ru", "kk") and cyrillic_share(plain) < 0.7:
        bad("ERROR", "латиница в кириллическом черновике", plain[:70])
    if d.get("lang") == "kk" and not any(c in KK_LETTERS for c in plain):
        bad("WARN", "казахский без казахских букв", plain[:70])

    # Качество текста
    if LEFTOVER_RE.search(text):
        bad("ERROR", "мусор в тексте", LEFTOVER_RE.search(text).group(0))
    if len(text) < 12:
        bad("ERROR", "пустой черновик", text)
    if len(text) > 500:
        bad("WARN", "слишком длинный черновик", str(len(text)))

    # Приоритет по taxonomy
    if r.get("category") in ("report.account", "report.payment") and r.get("priority") != "p0":
        bad("ERROR", "взлом или платёж не P0", r.get("priority"))
    if r.get("category") == "report.offtopic" and r.get("priority") != "p3":
        bad("ERROR", "оффтоп не P3", r.get("priority"))
    if r.get("category") in ("complaint.cheat", "complaint.scam", "complaint.rmt_ads") and f.get("has_evidence") \
            and r.get("priority") != "p1" and r.get("priority") != "p0":
        bad("ERROR", "читы или обман с доказательствами не P1", r.get("priority"))
    return out


def check_provocations(found: dict) -> None:
    """Придуманные опасные обращения на всех языках: данные проверяются отдельно от слов защиты."""
    for line in (ROOT / "examples" / "provocations.jsonl").open(encoding="utf-8"):
        p = json.loads(line)
        r, _ = triage_full({"kind": p["kind"], "messages": [{"role": "player", "text": p["text"]}]})
        wrong = ("human" in p and r["needs_human"] != p["human"]) or ("priority" in p and r["priority"] != p["priority"]) \
            or ("not_priority" in p and r["priority"] == p["not_priority"]) or ("category" in p and r["category"] != p["category"])
        if wrong:
            found[("ERROR", "провокация пропущена")].append((p["name"], p["text"], r["draft_reply"]["text"][:200]))


def opinion(found: dict, total: int) -> None:
    """Мнение проверяющего: выводы только из результатов проверки и из того, что он не может измерить."""
    count = lambda code: sum(len(v) for (_, c), v in found.items() if c == code)  # noqa: E731
    errors = sum(len(v) for (lvl, _), v in found.items() if lvl == "ERROR")
    dislikes, wishes = [], []
    if count("черновик утверждает решение до проверки"):
        dislikes.append(f"{count('черновик утверждает решение до проверки')} черновиков говорят о решении раньше админа: "
                        "«закрыто» или «отклонена» до того, как человек посмотрел.")
        wishes.append("Хочу, чтобы черновик с needs_human не содержал слов о закрытии.")
    if count("срок наказания назван без решения админа"):
        dislikes.append(f"{count('срок наказания назван без решения админа')} черновиков называют срок, который никто не назначал.")
        wishes.append("Хочу, чтобы срок всегда выбирал человек.")
    if count("слишком длинный черновик"):
        dislikes.append(f"{count('слишком длинный черновик')} черновиков длиннее 500 символов: админ это читать не станет.")
    if not (ROOT / "data" / "gold" / "drafts_scores.jsonl").exists():
        wishes.append("Хочу увидеть оценки людей: без них за главный критерий на 30% нельзя ручаться.")
    wishes.append("Хочу, чтобы носитель узбекского прочитал шаблоны: они написаны с LLM.")
    print("\nМНЕНИЕ ПРОВЕРЯЮЩЕГО")
    verdict = ("Сдавать нельзя: есть нарушения требований." if errors else
               "К сдаче допускаю, но не хвалю." if dislikes else
               "Формальных претензий нет, но это ещё не значит, что ответы хорошие.")
    print(f"Вердикт: {verdict}")
    if dislikes:
        print("Что мне не нравится:")
        for item in dislikes:
            print(f"  - {item}")
    print("Чего я хочу:")
    for item in wishes:
        print(f"  - {item}")
    print("Что я не могу проверить и потому не верю на слово:")
    for item in ("уместна ли цитата по смыслу: я вижу только, что пункт существует;",
                 "хорош ли ответ для живого админа;",
                 "грамотен ли казахский и узбекский;",
                 "работу LLM при запуске без ключа: эта проверка идёт в том режиме, что задан в окружении."):
        print(f"  - {item}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm-sample", type=int, default=0, help="сколько обращений прогнать через LLM: у бесплатного ключа дневной лимит")
    ap.add_argument("--llm-rpm", type=float, default=12, help="лимит запросов к LLM в минуту")
    args = ap.parse_args()
    tickets = [json.loads(line) for line in open(config.VALID_PATH, encoding="utf-8")]
    found = defaultdict(list)
    dedupe = Deduper()
    random.seed(11)
    with_llm = {t["ticket_id"] for t in random.sample(tickets, min(args.llm_sample, len(tickets)))} if llm.enabled() else set()
    mode, last_call = config.LLM_MODE, 0.0
    for t in tickets:
        config.LLM_MODE = mode if t["ticket_id"] in with_llm else "offline"
        if t["ticket_id"] in with_llm:
            time.sleep(max(0.0, last_call + 60 / args.llm_rpm - time.perf_counter()))
            last_call = time.perf_counter()
        request = ticket_to_request(t)
        request["is_duplicate"] = dedupe.is_duplicate(t)
        result, meta = triage_full(request)
        for level, code, detail in check(t, result, meta):
            found[(level, code)].append((t["ticket_id"], detail, result["draft_reply"]["text"][:200]))

    config.LLM_MODE = "offline"
    check_provocations(found)
    config.LLM_MODE = mode
    errors = sum(len(v) for (lvl, _), v in found.items() if lvl == "ERROR")
    warns = sum(len(v) for (lvl, _), v in found.items() if lvl == "WARN")
    print(f"Обращений: {len(tickets)}, из них через LLM: {len(with_llm)} · ошибок: {errors} · предупреждений: {warns}\n")
    for (level, code), items in sorted(found.items(), key=lambda x: (x[0][0], -len(x[1]))):
        print(f"[{level}] {code}: {len(items)}")
    opinion(found, len(tickets))
    out = config.ARTIFACTS_DIR / "audit.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({f"{k[0]} {k[1]}": v[:15] for k, v in found.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nПримеры: {out}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
