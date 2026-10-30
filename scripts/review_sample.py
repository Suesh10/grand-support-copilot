"""Выборка черновиков для ручной оценки: как их увидят админы и носители в жюри.

Берёт обращения валидации по языкам, прогоняет через сервис и сохраняет рядом
с реальным ответом админа. Результат лежит в data/gold: это производные данные,
в репозиторий они не попадают.
"""

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot import config, llm  # noqa: E402
from copilot.pipeline import triage_full  # noqa: E402
from copilot.predict import ticket_to_request  # noqa: E402

OUT = ROOT / "data" / "gold" / "drafts_review.jsonl"
PLAN = [("ru", "complaint", 12), ("ru", "report", 3), ("uz", "complaint", 8), ("kk", "complaint", 7)]
PAUSE_S = 6  # лимит бесплатного ключа


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    llm.batch_mode()
    random.seed(7)
    tickets = [json.loads(line) for line in open(config.VALID_PATH, encoding="utf-8")]
    rows = []
    for lang, kind, n in PLAN:
        pool = [t for t in tickets if t.get("lang") == lang and t["kind"] == kind
                and len(" ".join(m["text"] for m in t["messages"] if m["role"] == "player")) >= 8]
        for t in random.sample(pool, min(n, len(pool))):
            pred, meta = triage_full(ticket_to_request(t))
            rows.append({"ticket_id": t["ticket_id"], "lang": pred["lang"], "kind": kind, "category": pred["category"],
                         "player": " | ".join(m["text"] for m in t["messages"] if m["role"] != "admin")[:400],
                         "draft": pred["draft_reply"]["text"], "cited": pred["draft_reply"]["cited"],
                         "needs_human": pred["needs_human"], "source": meta.get("draft_source"),
                         "admin": " | ".join(m["text"] for m in t["messages"] if m["role"] == "admin")[:400],
                         "real_verdict": t.get("verdict")})
            time.sleep(PAUSE_S if meta.get("draft_source") == "llm" else 0)
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print(f"Готово: {len(rows)} → {OUT}")


if __name__ == "__main__":
    main()
