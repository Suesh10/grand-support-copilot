"""Пакетный прогон: make predict IN=tickets.jsonl OUT=pred.jsonl

Вход — обращения в формате выгрузки Grand Mobile, выход — по строке ответа
/triage на каждое обращение, с ticket_id.
"""

import argparse
import gzip
import json
import sys
import time

from . import llm
from .dedupe import Deduper
from .pipeline import triage


def ticket_to_request(t: dict) -> dict:
    """Обращение из выгрузки → запрос /triage. Ответ админа в запрос не попадает."""
    messages = [
        {"role": m.get("role", "player"), "text": m.get("text", "")}
        for m in t.get("messages", [])
        if m.get("role") != "admin"
    ]
    if messages:
        messages[0]["attachments"] = int(t.get("images_count") or 0)
    return {"kind": t.get("kind", "report"), "messages": messages,
            "rule_refs_raw": t.get("rule_refs_raw") or "", "reported_nick": t.get("reported_nick")}


def open_any(path: str):
    return gzip.open(path, "rt", encoding="utf-8") if path.endswith(".gz") else open(path, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    sys.stderr.reconfigure(encoding="utf-8")

    llm.batch_mode()
    n, started = 0, time.perf_counter()
    dedupe = Deduper()
    with open_any(args.inp) as fin, open(args.out, "w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip():
                continue
            ticket = json.loads(line)
            request = ticket_to_request(ticket)
            request["is_duplicate"] = dedupe.is_duplicate(ticket)
            pred = triage(request)
            fout.write(json.dumps({"ticket_id": ticket.get("ticket_id"), **pred}, ensure_ascii=False) + "\n")
            n += 1
    print(f"Готово: {n} обращений за {time.perf_counter() - started:.1f} с → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
