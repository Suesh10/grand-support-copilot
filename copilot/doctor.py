"""Самопроверка простым языком: что работает, что нет и что сделать. python -m copilot.doctor"""

import sys
import uuid

from . import config, knowledge, llm, model, retrieve, storage
from .rules import load_points


def row(name: str, state: str, text: str, fix: str = "") -> dict:
    return {"name": name, "state": state, "text": text, "fix": fix}


def can_write() -> bool:
    probe = config.ARTIFACTS_DIR / f".probe-{uuid.uuid4().hex}"
    try:
        config.ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def check(queue_size: int | None = None) -> list[dict]:
    rules = len(load_points())
    status = llm.status()["state"]
    out = [
        row("Правила", "ok", f"загружено пунктов: {rules}") if rules else
        row("Правила", "bad", "файла правил нет: цитат в черновиках не будет",
            "Положите rules.json из материалов кейса в data/support/handout и перезапустите сервис."),
        row("Модели", "ok", "обучены и загружены") if model.load() else
        row("Модели", "warn", "моделей нет: сервис работает по ключевым словам, точность ниже",
            "Положите данные кейса в data/support/handout и перезапустите: run.py обучит модели сам, около 3 минут."),
        row("Похожие случаи", "ok", "индекс загружен") if retrieve.load() else
        row("Похожие случаи", "warn", "индекса нет: блок «как решали похожие» будет пустым", "Он появится вместе с моделями."),
        row("Статьи поддержки", "ok", f"статей: {len(knowledge.articles())}") if knowledge.articles() else
        row("Статьи поддержки", "warn", "список статей не найден, ссылок в ответах не будет", "Запустите python scripts/articles.py, нужен интернет."),
    ]
    if status == "off":
        out.append(row("Gemini", "warn", "ключа нет: черновики собираются из шаблонов, сервис работает полностью",
                       "По желанию: скопируйте .env.example в .env и впишите GEMINI_API_KEY."))
    elif status == "down":
        out.append(row("Gemini", "warn", "сейчас не отвечает: сервис сам перешёл на шаблоны", "Ничего делать не нужно, он вернётся сам."))
    else:
        out.append(row("Gemini", "ok", "подключён"))
    if queue_size is not None:
        out.append(row("Очередь", "ok", f"обращений: {queue_size}") if queue_size else
                   row("Очередь", "warn", "обращений нет", "Проверьте файл examples/sample_tickets.jsonl или путь COPILOT_QUEUE."))
    out.append(row("Сохранение", "ok", "решения записываются") if can_write() else
               row("Сохранение", "bad", f"нельзя писать в {config.ARTIFACTS_DIR}: решения не сохранятся",
                   "Проверьте права на папку и свободное место на диске."))
    out += [row("Пережитый сбой", "warn", problem) for problem in storage.PROBLEMS]
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    marks = {"ok": "[ OK ]", "warn": "[ !  ]", "bad": "[СБОЙ]"}
    rows = check()
    for item in rows:
        print(f"{marks[item['state']]} {item['name']}: {item['text']}")
        if item["fix"]:
            print(f"       Что сделать: {item['fix']}")
    return 1 if any(item["state"] == "bad" for item in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
