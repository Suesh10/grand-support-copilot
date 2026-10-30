# Support Copilot — команды проекта.
# Быстрый старт: make install && make predict IN=tickets.jsonl OUT=pred.jsonl

ifeq ($(OS),Windows_NT)
  VENV_PY := .venv/Scripts/python.exe
else
  VENV_PY := .venv/bin/python
endif
PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),python3)

IN ?= $(COPILOT_DATA_DIR)/tickets_valid.jsonl
OUT ?= artifacts/pred.jsonl
PORT ?= 8000

.PHONY: install train serve predict test

install:
	python -m venv .venv
	$(VENV_PY) -m pip install -q --upgrade pip
	$(VENV_PY) -m pip install -q -r requirements.txt

train:
	$(PY) scripts/train.py

serve:
	$(PY) -m uvicorn copilot.api:app --host 0.0.0.0 --port $(PORT)

predict:
	@mkdir -p $(dir $(OUT))
	$(PY) -m copilot.predict --in $(IN) --out $(OUT)

test:
	$(PY) -m pytest -q
