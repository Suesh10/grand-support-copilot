#!/usr/bin/env python3
"""Запуск в один шаг на любой системе: python run.py (на Windows двойной щелчок по start.bat).

Сам ставит зависимости, находит данные, обучает модели, выбирает свободный порт, открывает
браузер и перезапускает сервис, если тот упал. Нужен только Python 3.10 или новее.
Сервер слушает только этот компьютер: входа в админку нет, поэтому наружу её не открываем.

python run.py --check      только самопроверка
python run.py --no-browser без открытия браузера
"""

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
HOST = "127.0.0.1"
FIRST_PORT = 8000
PORTS_TO_TRY = 20
READY_TIMEOUT_S = 180
MAX_RESTARTS = 3
HEALTHY_RUN_S = 60  # проработал столько: следующий сбой считается новым, а не продолжением старого
NEEDED = "import fastapi, uvicorn, sklearn, joblib, dotenv, numpy, google.genai"


def say(text: str) -> None:
    print(text, flush=True)


def stop(text: str) -> None:
    say(f"\nНЕ ПОЛУЧИЛОСЬ: {text}")
    sys.exit(1)


def ready_to_import() -> bool:
    return VENV_PY.exists() and subprocess.run([str(VENV_PY), "-c", NEEDED], capture_output=True, check=False).returncode == 0


def install() -> None:
    if ready_to_import():
        return
    say("Первый запуск: ставлю зависимости, около 2 минут...")
    if not VENV_PY.exists() and subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=False).returncode:
        stop("не удалось создать окружение. Проверьте, что Python установлен полностью.")
    steps = subprocess.run([str(VENV_PY), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], check=False)
    if steps.returncode:
        stop("зависимости не установились. Проверьте интернет и запустите ещё раз.")


def find_data() -> Path | None:
    """Папка с rules.json: заданная явно, стандартная или любая внутри data/."""
    wanted = os.getenv("COPILOT_DATA_DIR")
    places = [Path(wanted)] if wanted else [ROOT / "data" / "support" / "handout"]
    if not wanted:
        places += [p.parent for p in sorted((ROOT / "data").glob("**/rules.json"))]
    return next((p for p in places if (p / "rules.json").exists()), None)


def prepare_models(env: dict) -> None:
    code = subprocess.run([str(VENV_PY), str(ROOT / "scripts" / "ensure_models.py")], env=env, check=False).returncode
    if code:
        say("Обучить модели не удалось: сервис запустится по ключевым словам, причина будет в справке.")


def free_port(first: int = FIRST_PORT) -> int:
    for port in range(first, first + PORTS_TO_TRY):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex((HOST, port)):
                return port
    stop(f"все порты с {first} по {first + PORTS_TO_TRY - 1} заняты. Закройте лишние программы.")


def wait_ready(url: str, open_browser: bool, done: threading.Event) -> None:
    deadline = time.time() + READY_TIMEOUT_S
    while time.time() < deadline and not done.is_set():
        try:
            urllib.request.urlopen(f"{url}/health", timeout=2).close()
        except OSError:
            time.sleep(1)
            continue
        say(f"\nГотово: {url}/admin\nЧтобы остановить, нажмите Ctrl+C или закройте это окно.")
        if open_browser:
            webbrowser.open(f"{url}/admin")
        return


def serve(port: int, env: dict, open_browser: bool) -> None:
    url = f"http://{HOST}:{port}"
    command = [str(VENV_PY), "-m", "uvicorn", "copilot.api:app", "--host", HOST, "--port", str(port), "--log-level", "warning"]
    crashes = 0
    while True:
        done = threading.Event()
        threading.Thread(target=wait_ready, args=(url, open_browser, done), daemon=True).start()
        started = time.time()
        server = subprocess.Popen(command, cwd=ROOT, env=env)
        try:
            code = server.wait()
        except KeyboardInterrupt:
            done.set()
            server.terminate()
            say("\nСервис остановлен.")
            return
        done.set()
        open_browser = False  # браузер уже открыт, после перезапуска страница подключится сама
        crashes = 1 if time.time() - started > HEALTHY_RUN_S else crashes + 1
        if crashes > MAX_RESTARTS:
            stop(f"сервис падает при запуске (код {code}). Причина выше. Проверить всё: python run.py --check")
        say(f"Сервис остановился (код {code}), перезапускаю. Попытка {crashes} из {MAX_RESTARTS}.")
        time.sleep(2)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Запуск Support Copilot в один шаг")
    parser.add_argument("--check", action="store_true", help="только самопроверка")
    parser.add_argument("--no-browser", action="store_true", help="не открывать браузер")
    parser.add_argument("--port", type=int, default=FIRST_PORT, help="с какого порта начинать поиск свободного")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        stop(f"нужен Python 3.10 или новее, сейчас {sys.version.split()[0]}. Скачать: python.org/downloads")
    install()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    data = find_data()
    if data:
        env["COPILOT_DATA_DIR"] = str(data)
        say(f"Данные: {data}")
    else:
        say("Данных кейса нет: запускаю демо на примерах. Без файла правил цитат не будет, это видно в справке.")
    if args.check:
        sys.exit(subprocess.run([str(VENV_PY), "-m", "copilot.doctor"], cwd=ROOT, env=env, check=False).returncode)
    prepare_models(env)
    port = free_port(args.port)
    if port != args.port:
        say(f"Порт {args.port} занят, беру {port}.")
    serve(port, env, not args.no_browser)


if __name__ == "__main__":
    main()
