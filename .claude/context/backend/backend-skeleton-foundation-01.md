# Session log — backend-skeleton-foundation-01 (Scaffold del proyecto + tooling)

## 2026-08-13 — Arranque

**Tarea:** crear la raíz `backend/` y su tooling (doc-only: esqueleto + guión, sin código de negocio).
Base sobre la que cuelgan las tareas 07–18. Rama `plan/backend/skeleton-foundation`.

**Estado del entorno (verificado en sesión):** Python 3.14.2, Docker Compose v2.40.3, **sin
`pip-compile`** → no se genera lockfile real (`requirements.txt` queda como guión-stub, coherente con
el "fuera de alcance: fijar versiones exactas se afina al instalar de verdad").

**Plan de ejecución:** scaffolding (requirements.in/-dev.in agrupados, pyproject ruff/mypy-strict/pytest,
Dockerfile non-root, docker-compose db pgvector+healthcheck, Makefile, .env.example, README, .gitignore)
+ árbol `app/` con `__init__.py` + guión-puntero por subpaquete. Verificación doc-only: `docker compose
config`, parseo `pyproject.toml`, árbol completo.

## 2026-08-13 — Ejecución y cierre

**Ficheros creados (18):**
- Tooling: `requirements.in`, `requirements-dev.in`, `requirements.txt` (guión-stub, sin pin), `pyproject.toml`.
- Contenedores: `Dockerfile` (multi-stage, venv, non-root, HEALTHCHECK), `docker-compose.yml`
  (`db` pgvector/pgvector:pg16 + healthcheck pg_isready + volumen; `api` build local, `depends_on` sano),
  `.dockerignore`.
- Arranque/DX: `Makefile` (venv/install/run/migrate/ingest/seed/lint/typecheck/test), `.env.example`,
  `README.md`, `.gitignore`.
- Árbol `app/` (13 `__init__.py`): raíz + `core`, `api`+`api/v1`, `domain`, `infra`+`infra/{db,vector,llm,langsmith}`,
  `agents`, `ingestion`, `rag`. Cada uno con guión (propósito/qué implementar/contrato/deps/anti-patrones)
  y **puntero a la tarea** que lo rellena (07/08/09/10/11/12/13/14/15/16/17).

**Decisiones técnicas + porqué:**
- **Deps en `requirements.in` (pip-tools), NO en `pyproject`**: pyproject queda para metadata + config de
  tooling. `requirements.txt` es placeholder porque no hay `pip-compile` en el entorno y fijar versiones
  está fuera de alcance (se compila al instalar de verdad; el Dockerfile recompila desde `.in`).
- **`docker compose config` limpio sin `.env`**: interpolación `${VAR:-default}` en `db` + `env_file`
  con `required: false` en `api`. Sin clave `version:` (obsoleta en Compose v2).
- **mypy strict** con override `ignore_missing_imports` para libs sin stubs (pgvector/langgraph/langsmith).
- **Guardarraíl hexagonal** documentado en los guiones (dominio no importa infra) y anotado en ruff
  (flake8-tidy-imports) para endurecer con código real.
- `.env.example` incluye `EMBEDDING_DIM=1536` (fuente de `vector(N)`) y throttling B.1 comentado
  (lo consumen 07/11/12) — no especulo su forma final.

**Verificación (doc-only, bucle principal — comandos ejecutados en sesión):**
- `docker compose -f docker-compose.yml config` → **exit 0, sin warnings**; `db` = `pgvector/pgvector:pg16`
  con `healthcheck` (`pg_isready -U syntax -d syntax`); `api` con `condition: service_healthy`.
- `python3 -c tomllib.load(pyproject.toml)` → parse OK (`mypy.strict = True`, `requires-python = >=3.12`).
- `python3 -m compileall app` → OK (13 módulos válidos). `__pycache__` limpiados tras la comprobación.
- `make help` → lista los 10 targets. Árbol `app/` completo (todos los `__init__.py` presentes).

**Nota honesta:** NO se ejecutó `pip install`/`pip-compile` (fuera de alcance + no disponible en entorno);
`make run/migrate/ingest/seed` apuntan a entry-points que crean tareas posteriores (07/08/13/17) y hoy
fallarían a propósito — está declarado en sus guiones. Verificación de imports = `compileall` (sintaxis),
NO import en runtime de FastAPI/SQLAlchemy (no instaladas; doc-only).

**Gate `fact-checker`:** ejecutado (subagente, sonnet por config) — ver resultado abajo.

**Tiempo real:** ~1 h.

**Follow-ups:** 07 crea `app/main.py` + `/health` + `Settings`; 08 la capa DB + Alembic + RLS (footgun
`SET app.tenant_id` ya avisado en el guión de `infra/db`); el resto de subpaquetes tienen su puntero.
