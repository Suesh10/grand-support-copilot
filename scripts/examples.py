"""Примеры черновиков для отчёта: make examples

Обращения придуманы командой (не из выгрузки Grand Mobile), поэтому их можно
публиковать. Результат — docs/examples.md.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from copilot.pipeline import triage_full  # noqa: E402

EXAMPLES = [
    ("Жалоба с доказательствами, русский",
     {"kind": "complaint", "messages": [{"role": "player", "attachments": 2,
      "text": "Arman_Petrov оскорблял меня и мою семью в чате, скрины есть, 2.1 ОП"}]}),
    ("Апелляция на своё наказание",
     {"kind": "complaint", "messages": [{"role": "player", "attachments": 1,
      "text": "не согласен с наказанием, бан выдан ошибочно, я не использовал читы, верните аккаунт"}]}),
    ("Жалоба на читы, узбекский",
     {"kind": "complaint", "messages": [{"role": "player", "attachments": 1,
      "text": "Bobur_Karimov cheat ishlatyapti, havoda uchib yuribdi, video bor 5.2"}]}),
    ("Репорт: застрял",
     {"kind": "report", "messages": [{"role": "player", "text": "застрял в текстурах у банка, помогите"}]}),
    ("Репорт: платёж, казахский в cp1251 (ї вместо ү)",
     {"kind": "report", "messages": [{"role": "player", "text": "донат жасадым, ГК тїспеді, кґмектесіѕізші"}]}),
    ("Репорт: взлом аккаунта",
     {"kind": "report", "messages": [{"role": "player", "text": "взломали аккаунт, сменили пароль, пропала машина"}]}),
    ("Пустой репорт",
     {"kind": "report", "messages": [{"role": "player", "text": "+"}]}),
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    out = ["# Примеры работы Support Copilot", "",
           "Обращения придуманы командой (не из данных Grand Mobile). Ответы — реальный вывод `POST /triage`.", ""]
    for title, req in EXAMPLES:
        resp, meta = triage_full(req)
        out += [f"## {title}", "", "**Запрос**", "```json", json.dumps(req, ensure_ascii=False, indent=2), "```", "",
                f"**Ответ** (источник черновика: `{meta.get('draft_source')}`"
                + (f", {meta['latency_s']:.2f} с, ${meta['cost_usd']:.5f}" if meta.get("cost_usd") else "") + ")",
                "```json", json.dumps(resp, ensure_ascii=False, indent=2), "```", ""]
        print(f"{title}: {resp['category']} / {resp['priority']} / needs_human={resp['needs_human']} / {meta.get('draft_source')}")
    path = ROOT / "docs" / "examples.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"→ {path}")


if __name__ == "__main__":
    main()
