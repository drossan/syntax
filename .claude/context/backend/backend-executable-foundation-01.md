# Session log — backend-executable-foundation-01

Tarea: **Entorno backend ejecutable** (lockfiles reproducibles + docker db + toolchain mutmut).
Plan: `.claude/plans/active/backend/executable-foundation.md`. Rama: `plan/backend/executable-foundation`
(desde `main`). Tipo: **verificación**, no TDD (sin código de negocio).

Append-only. Registra qué se hizo + por qué + comandos y su **salida real**.

---

## 2026-08-14 — Arranque

- Plan y tarea 01 movidos a `active/`, `status: active`. Rama `plan/backend/executable-foundation` creada desde `main`.
- Modo de trabajo: tarea de tooling/entorno → el asistente propone los diffs de config; el **owner** aplica y
  ejecuta los comandos (`make install`, docker, smoke-import). **Nada ejecutado aún**: ninguna afirmación de
  "pasa/instala" está verificada hasta ver la salida real.
- Plan de acción (4 cambios de fichero + comandos):
  1. `requirements.in`: +`structlog` (runtime; lo usa la tarea 05).
  2. `requirements-dev.in`: +`mutmut`, +`pip-tools`.
  3. `Makefile` target `install`: compilar **ambos** lockfiles (runtime, luego dev con `-c requirements.txt`).
  4. `pyproject.toml`: `[tool.mutmut]` (provisional — a confirmar contra la versión pinada, F3).
  - Comandos: `make venv` (si falta `.venv`) · `make install` · `cp .env.example .env` · `docker compose up -d db` ·
    smoke-import · `mutmut --version` + registrar invocación exacta.

## 2026-08-14 — Primera ejecución del owner (hallazgos)

- Smoke-import OK: `python -c "import fastapi, pydantic, structlog, langgraph, langchain"` sin error (salida real del owner).
- `mutmut` versión **3.7.0**. Warning real: `The config paths_to_mutate is deprecated. Please rename it to source_paths`.
  → `pyproject.toml [tool.mutmut]` corregido a `source_paths = ["app/"]` (era `paths_to_mutate`; F3 materializado).
  Invocación registrada: `mutmut run` → `mutmut results`.
- **Discrepancia**: el venv era **Python 3.11** (`.venv/lib/python3.11/...`), pero el stack está fijado a **3.12**
  (`pyproject` requires-python>=3.12 / ruff py312 / mypy 3.12; Dockerfile python:3.12-slim). `make venv` usaba el
  `python3` del sistema (3.11). **Decisión del owner**: recrear el venv con 3.12. `make venv` pinado a `python3.12`.
- **No verificado aún**: salida de `make install` (compilación de ambos lockfiles) y `docker compose ps` (db healthy)
  — pendientes de ver tras recrear con 3.12.

## 2026-08-15 — Cierre

Recreado el venv con **Python 3.12.7**; `make install` compiló ambos lockfiles bajo 3.12
(`requirements.txt` 237 líneas/71 pins, `requirements-dev.txt` generado). Verificado (salida real):
- `docker compose ps` → `backend-db-1` Up (healthy).
- `make lint` → ruff "All checks passed!" + "83 files already formatted".
- `make typecheck` → mypy strict "Success: no issues found in 79 source files".
- `mutmut --version` → 3.7.0 (sin warning; `[tool.mutmut] source_paths`).
- Gate `fact-checker`: 7/7 VERIFICADO (subagente independiente), 0 INCORRECTO, 0 NO VERIFICABLE.

Decisiones: stack en **3.12** (`make venv` pinado a `python3.12`); `structlog` runtime; `mutmut 3.7.0`
con `source_paths` (fix del warning `paths_to_mutate`, F3 materializado); `make install` compila ambos
lockfiles (dev `-c requirements.txt`).

Ficheros tocados: `backend/{Makefile, pyproject.toml, requirements.in, requirements-dev.in,
requirements.txt, requirements-dev.txt}`. Sin código de negocio (tarea de entorno).

Tiempo real: ~2h (incl. fix py3.11→3.12 y source_paths).

## Follow-ups
- Tarea 03: primer `mutmut run`/`mutmut results` e2e (shakeout) sobre `config.py`; confirmar break:80.
- Tarea 02: ADR-0013 (arranque Fase 2, supersede 0012) + adr-index + nota ADR-0001.

