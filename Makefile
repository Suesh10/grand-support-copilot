# Support Copilot — команды проекта.
# Быстрый старт: make install && make predict IN=tickets.jsonl OUT=pred.jsonl

ifeq ($(OS),Windows_NT)
  VENV_PY := .venv/Scripts/python.exe
  SYSTEM_PY := python
else
  VENV_PY := .venv/bin/python
  SYSTEM_PY := python3
endif
PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),python3)

DATA ?= $(or $(COPILOT_DATA_DIR),data/support/handout)
export COPILOT_DATA_DIR := $(DATA)
IN ?= examples/sample_tickets.jsonl
OUT ?= artifacts/pred.jsonl
PORT ?= 8000
# Входа в админку нет, поэтому наружу она не открывается. В закрытой сети: make serve HOST=0.0.0.0
HOST ?= 127.0.0.1

.PHONY: install train models serve predict eval examples audit review test doctor

install:
	$(SYSTEM_PY) -m venv .venv
	$(VENV_PY) -m pip install -q --upgrade pip
	$(VENV_PY) -m pip install -q -r requirements.txt

train:
	$(PY) scripts/train.py

# Модели обучаются на данных кейса, которые нельзя класть в репозиторий.
# Если моделей нет, а данные есть — обучаем автоматически (~3 мин), иначе работаем на правилах.
models:
	$(PY) scripts/ensure_models.py

serve: models
	$(PY) -m uvicorn copilot.api:app --host $(HOST) --port $(PORT)

predict: models
	$(PY) -m copilot.predict --in $(IN) --out $(OUT)

LLM_SAMPLE ?= 100
eval:
	$(PY) scripts/eval.py --llm-sample $(LLM_SAMPLE)

examples:
	$(PY) scripts/examples.py

# У бесплатного ключа дневной лимит: через LLM идёт только выборка, остальное офлайн.
AUDIT_LLM ?= 0
audit:
	$(PY) scripts/audit.py --llm-sample $(AUDIT_LLM)

# Слепая оценка: готовит 30 черновиков рядом с реальными ответами, вкладка в интерфейсе админа.
review:
	$(PY) scripts/review_sample.py

test:
	$(PY) -m pytest -q

# Самопроверка простым языком: что работает и что сделать.
doctor:
	$(PY) -m copilot.doctor
