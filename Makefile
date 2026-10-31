# Support Copilot — команды проекта.
# Быстрый старт: make install && make predict IN=tickets.jsonl OUT=pred.jsonl

ifeq ($(OS),Windows_NT)
  VENV_PY := .venv/Scripts/python.exe
else
  VENV_PY := .venv/bin/python
endif
PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),python3)

DATA ?= $(or $(COPILOT_DATA_DIR),data/support/handout)
export COPILOT_DATA_DIR := $(DATA)
IN ?= examples/sample_tickets.jsonl
OUT ?= artifacts/pred.jsonl
PORT ?= 8000
# Входа в админку нет, поэтому наружу она не открывается. В закрытой сети: make serve HOST=0.0.0.0
HOST ?= 127.0.0.1
MODEL := artifacts/classifier.joblib

.PHONY: install train models serve predict eval examples audit test

install:
	python -m venv .venv
	$(VENV_PY) -m pip install -q --upgrade pip
	$(VENV_PY) -m pip install -q -r requirements.txt

train:
	$(PY) scripts/train.py

# Модели обучаются на данных кейса, которые нельзя класть в репозиторий.
# Если моделей нет, а данные есть — обучаем автоматически (~3 мин), иначе работаем на правилах.
models:
	@if [ ! -f $(MODEL) ]; then \
	  if [ -f "$(DATA)/tickets_train.jsonl.gz" ]; then \
	    echo "Модели не найдены, обучаю на $(DATA) (~3 мин)..."; $(PY) scripts/train.py; \
	  else \
	    echo "ВНИМАНИЕ: нет моделей и данных в $(DATA). Работаю на правилах; укажите DATA=путь/к/handout"; \
	  fi; \
	fi

serve: models
	$(PY) -m uvicorn copilot.api:app --host $(HOST) --port $(PORT)

predict: models
	@mkdir -p $(dir $(OUT))
	$(PY) -m copilot.predict --in $(IN) --out $(OUT)

LLM_SAMPLE ?= 100
eval:
	$(PY) scripts/eval.py --llm-sample $(LLM_SAMPLE)

examples:
	$(PY) scripts/examples.py

audit:
	$(PY) scripts/audit.py

test:
	$(PY) -m pytest -q
