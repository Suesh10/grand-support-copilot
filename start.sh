#!/bin/sh
# Запуск в один шаг на macOS и Linux.
cd "$(dirname "$0")" || exit 1
exec python3 run.py "$@"
