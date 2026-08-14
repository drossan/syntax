---
id: backend-skeleton-foundation-01
package: backend
plan: skeleton-foundation
status: done
priority: 1
depends_on: []
estimate: 2h
actual: 1h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Scaffold del proyecto + tooling

## Description

Crear la raíz del proyecto `backend/` y su tooling: gestión de dependencias (pip-tools + venv),
calidad (ruff, mypy strict, pytest), contenedores (Dockerfile, docker-compose con Postgres+pgvector)
y ficheros de arranque. Es la base sobre la que cuelgan todas las demás tareas. **Solo esqueleto +
guión**: no se implementa lógica.

## Spec

- `backend/requirements.in` + `requirements.txt` (pip-compile) con el guión de dependencias (comentadas
  por grupo): fastapi, uvicorn[standard], pydantic, pydantic-settings, sqlalchemy[asyncio], asyncpg,
  alembic, pgvector, langchain, langgraph, langgraph-checkpoint-postgres, langsmith, langchain-openai,
  argon2-cffi, pyjwt (o python-jose), httpx. `requirements-dev.in` (ruff, mypy, pytest, pytest-asyncio).
- `pyproject.toml` (metadata + config de ruff/mypy/pytest) o ficheros equivalentes; `mypy` en **strict**.
- `Dockerfile` (python 3.12-slim, venv, non-root) y `docker-compose.yml` con servicio `db`
  (`pgvector/pgvector:pg16`, volumen, `healthcheck`) y `api` (build local). `.dockerignore`.
- `Makefile` con targets: `venv`, `install`, `run`, `migrate`, `ingest`, `seed`, `lint`, `typecheck`, `test`.
- `.env.example` (DATABASE_URL, OPENAI_API_KEY, JWT_SECRET, JWT_*_TTL, LANGSMITH_*, APP_ENV).
- `README.md` (cómo levantar) y `.gitignore`.
- `app/__init__.py` y subpaquetes vacíos con `__init__.py` + guión que apunta a la tarea que los rellena
  (`core`, `api/v1`, `domain`, `infra/{db,vector,llm,langsmith}`, `agents`, `ingestion`, `rag`).

## Fuera de alcance

- Implementar código de negocio (solo esqueleto + guión).
- Fijar versiones exactas/lockfile reproducible más allá del guión (se afina al instalar de verdad).

## Scenarios (Gherkin)

<!-- Doc-only: sin código testeable. Se sustituyen los escenarios por verificación. -->
**Verificación (doc-only):**
- `docker-compose config` valida sin error y define `db` con imagen pgvector + healthcheck.
- `requirements.in` está bien formado (agrupado + comentado); `pip-compile` produciría `requirements.txt`.
- `make` lista los targets previstos; `.env.example` incluye todas las variables que consumen otras tareas.
- El árbol `app/` existe con `__init__.py` y cada subpaquete lleva su guión-puntero a la tarea que lo rellena.

## Provides

- Raíz `backend/` con tooling, contenedores (Postgres+pgvector), Makefile, `.env.example` y el **árbol
  de paquetes vacío** sobre el que trabajan 07–18. Toda tarea posterior asume esta estructura y estas deps.

## Definition of Done

- [x] Estructura/ficheros creados donde el plan indica, con nombres correctos.
- [x] Cada fichero de esqueleto lleva su guión (propósito, qué implementar, contrato, dependencias, pasos, anti-patrones).
- [x] `docker-compose config` valida (exit 0, sin warnings); `requirements.in`/`pyproject` bien formados (tomllib parsea).
- [x] Lo declarado en `Provides` queda disponible para las tareas dependientes (árbol `app/` + tooling + `.env.example`).
- [x] Gate de `fact-checker` superado (no-negociable).
- [x] Doc técnica (README) + histórico en `.claude/context/backend/backend-skeleton-foundation-01.md`.
