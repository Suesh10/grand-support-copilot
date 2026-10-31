"""Служебные файлы смены: испорченный файл не должен останавливать работу.

Битый файл не удаляется, а откладывается рядом с пометкой .broken: данные можно будет восстановить.
Запись идёт через временный файл, поэтому сбой посреди записи не портит прежнюю версию.
"""

import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger(__name__)
PROBLEMS: list[str] = []  # что сервис пережил сам: показывается в справке админки
MAX_PROBLEMS = 50
REPLACE_TRIES = 5  # на Windows файл бывает занят читателем доли секунды


def note(problem: str) -> None:
    log.warning(problem)
    if problem not in PROBLEMS:
        PROBLEMS[:] = [*PROBLEMS, problem][-MAX_PROBLEMS:]


def quarantine(path: Path, why: str) -> None:
    aside = path.with_name(f"{path.name}.broken-{int(time.time())}")
    try:
        path.replace(aside)
        note(f"Файл {path.name} был испорчен ({why}). Сервис продолжил работу, копия лежит рядом: {aside.name}.")
    except OSError:
        note(f"Файл {path.name} испорчен ({why}), отложить его не удалось.")


def read_json(path: Path, default):
    """Содержимое файла или default, если файла нет или он испорчен."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except OSError:
        return default
    except ValueError:
        quarantine(path, "не читается")
        return default
    if not isinstance(data, type(default)):
        quarantine(path, "неверный формат")
        return default
    return data


def read_jsonl(path: Path) -> list[dict]:
    """Строки-объекты файла: одна битая строка, например после сбоя питания, не стоит всей смены."""
    path = Path(path)
    rows, broken = [], 0
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    broken += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    broken += 1
    except OSError:
        return []
    if broken:
        note(f"В файле {path.name} пропущено битых строк: {broken}.")
    return rows


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if attempt == REPLACE_TRIES - 1:
                raise
            time.sleep(0.05)
