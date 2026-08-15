---
id: backend-executable-foundation-01
package: backend
plan: executable-foundation
status: done
priority: 1
depends_on: []
estimate: 3h
actual: ~2h
created: 2026-08-14
updated: 2026-08-15
---

# Entorno backend ejecutable (lockfiles reproducibles + docker db + toolchain)

## Description

Primera tarea de la Fase 2. Lleva el backend de "esqueleto doc-only" a **entorno ejecutable y
reproducible**: compila los lockfiles reales, instala las deps, levanta Postgres+pgvector y sanea el
toolchain de mutation. **No escribe código de producción ni tests** (eso empieza en la 03). Es
**verificación**, no TDD. Contexto: `backend/IMPLEMENTATION-GUIDE.md` §3, HOW-TO precondición dura.

## Spec

- **`make install` (editar el `Makefile`)**: compilar **ambos** lockfiles de forma reproducible —
  `pip-compile requirements.in -o requirements.txt` y luego `pip-compile requirements-dev.in -o
  requirements-dev.txt -c requirements.txt` (dev constreñido contra runtime → versiones compartidas) — e
  instalar `requirements-dev.txt`.
- **`requirements.in`**: añadir `structlog` (runtime; lo usa la tarea 05).
- **`requirements-dev.in`**: añadir `mutmut` y `pip-tools`.
- Compilar y **commitear** `requirements.txt` y `requirements-dev.txt` reales (reemplazan los stubs).
- `.venv` (`make venv`) + `make install` sin error; `.env` desde `.env.example` (no commitear `.env`).
- `docker compose up -d db` → healthy (`pg_isready`).
- **Smoke-import**: `python -c "import fastapi, pydantic, structlog, langgraph, langchain"` sale 0.
- **mutmut**: pinar la versión en `requirements-dev.in`, añadir `[tool.mutmut]` a `pyproject.toml`
  (`paths_to_mutate = "app/"`, runner pytest), confirmar `mutmut --version` y **registrar la invocación
  exacta** (`mutmut run` / `mutmut results`) de esa versión en el session log (el plugin marca el camino
  mutmut como "no verificado" → se sanea aquí).
- Verificar que `make lint` + `make typecheck` siguen OK sobre el esqueleto existente.

## Fuera de alcance

- Código de producción y tests (tarea 02 crea el scaffold; 03+ escriben tests reales).
- Migraciones / `make migrate` / RLS (plan de capa DB).
- Verificación **profunda** del surface de LangGraph/LangChain (`interrupt()`, `Command(resume=)`,
  `with_structured_output`, `PostgresSaver`) — aquí solo se confirma que **importan**; las firmas se pinan
  en el plan del agente.
- `structlog` en el código, `/health`, CORS, settings — sus tareas respectivas.

## Scenarios (Gherkin)

<!-- Tarea de VERIFICACIÓN, no TDD: no produce código de producción testeable. Se verifica ejecutando
     comandos y comprobando su salida real (fact-checker al cierre). Sin escenarios Gherkin ni gate de
     mutation. SDD: sin cambios de spec/CU (es infra de entorno). -->

**Verificación (no TDD)** — cada punto se comprueba con la salida real del comando:

- `make install` termina sin error y genera `requirements.txt` + `requirements-dev.txt` con pins
  **compartidos** entre runtime y dev (dev compilado con `-c requirements.txt`).
- `docker compose up -d db` deja el servicio `db` **healthy** (`docker compose ps` / `pg_isready`).
- `python -c "import fastapi, pydantic, structlog, langgraph, langchain"` sale con código 0.
- `mutmut --version` imprime la versión pinada; la invocación exacta queda registrada en el session log.
- `make lint` y `make typecheck` siguen en verde sobre el esqueleto.

## Provides

Entorno reproducible para todas las tareas siguientes: `.venv` con deps instaladas, lockfiles pineados
y commiteados, servicio `db` (Postgres+pgvector) corriendo, y toolchain de mutation (`mutmut` pinado +
`[tool.mutmut]` + invocación documentada) listo para los gates de cierre de 03–06.

## Definition of Done

- [x] `make install` compila **ambos** lockfiles (dev `-c requirements.txt`) e instala, sin error (salida real).
- [x] `structlog` en `requirements.in`; `mutmut` + `pip-tools` en `requirements-dev.in`; ambos `.txt` commiteados.
- [x] `docker compose up -d db` → healthy (salida real).
- [x] Smoke-import de `fastapi/pydantic/structlog/langgraph/langchain` OK (salida real).
- [x] `mutmut` pinado + `[tool.mutmut]` en `pyproject.toml` + invocación exacta registrada.
- [x] `make lint` + `make typecheck` OK.
- [x] Gate de `fact-checker`: afirmaciones de la sesión verificadas (INCORRECTO bloquea).
- [x] Documentación: session log (`.claude/context/backend/backend-executable-foundation-01.md`) con comandos +
      salidas + invocación mutmut; nota en `backend/README.md`/HOW-TO si cambia el flujo de `make install`.

<!-- No aplican: TDD, "1 test por escenario", gate de mutation (sin código de producción). github-tracking off. -->
