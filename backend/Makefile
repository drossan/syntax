# ─────────────────────────────────────────────────────────────────────────────
# Makefile — atajos de desarrollo del backend.
#
# GUIÓN: cada target envuelve el comando canónico. Varios apuntan a entry-points
# que crean tareas POSTERIORES (main.py→07, alembic→08, ingestion→13, seeds→17):
# hasta entonces fallarán a propósito con un mensaje claro. Requiere el venv
# activo (`. .venv/bin/activate`) o usa el binario del venv directamente.
# ─────────────────────────────────────────────────────────────────────────────

VENV ?= .venv
PY   ?= $(VENV)/bin/python
PIP  ?= $(VENV)/bin/pip

.DEFAULT_GOAL := help
.PHONY: help venv install run migrate ingest seed lint typecheck test test-watch mutation

help: ## Lista los targets disponibles
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

venv: ## Crea el entorno virtual (.venv) — Python 3.12 (paridad con Dockerfile/pyproject)
	python3.12 -m venv $(VENV)

install: ## Compila e instala deps de desarrollo (pip-tools)
	$(PIP) install --upgrade pip pip-tools
	$(VENV)/bin/pip-compile requirements.in -o requirements.txt
	$(VENV)/bin/pip-compile requirements-dev.in -o requirements-dev.txt -c requirements.txt
	$(PIP) install -r requirements-dev.txt

run: ## Levanta la API en local con reload (entry-point: tarea 07)
	$(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate: ## Aplica migraciones Alembic, incl. políticas RLS (tarea 08)
	$(VENV)/bin/alembic upgrade head

ingest: ## Ejecuta el pipeline de ingestión de la KB (idempotente, tarea 13)
	$(PY) -m app.ingestion

seed: ## Carga seeds/fixtures idempotentes (tenant demo, roles, KB muestra — tarea 17)
	$(PY) -m app.infra.db.seed

lint: ## Ruff: lint + format check
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

typecheck: ## Mypy en modo strict
	$(VENV)/bin/mypy app

test: ## Pytest (cuando exista código real; doc-only por ahora)
	$(VENV)/bin/pytest

test-watch: ## Reejecuta pytest al guardar (modo watch, pytest-watcher)
	$(VENV)/bin/ptw . --now

mutation: ## Gate de mutation (cosmic-ray) — acota module-path/test-command en cosmic-ray.toml
	rm -f session.sqlite
	$(VENV)/bin/cosmic-ray init cosmic-ray.toml session.sqlite
	$(VENV)/bin/cosmic-ray exec cosmic-ray.toml session.sqlite
	$(VENV)/bin/cr-rate session.sqlite --fail-over 20
