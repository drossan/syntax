# Session log — backend-agent-graph-01

## 2026-08-27 — arranque
- Plan `agent-graph` movido a `active/`, rama `plan/backend/agent-graph` creada desde `main` (up to date con origin).
- Tarea 01 movida a `active/`. Precondición del plan (deps LangGraph/LangChain ya instaladas) no reverificada aún en esta sesión — se verifica ahora como parte del Red de esta tarea.

## 2026-08-27 — ejecución TDD
- **Reverificado en esta sesión** (no asumido del plan): `langgraph`/`langchain`/`langchain-openai` instalados; surface real (`interrupt(value)`, `Command(resume=)`, `StateGraph.compile(checkpointer=)`, `with_structured_output(method='json_schema')`) coincide con lo que documenta el plan. `psycopg` 3.3.4 sin extras SÍ rompía con `ImportError: no pq wrapper available` al importar `AsyncPostgresSaver` — confirmado reproduciendo el error antes del fix.
- Red: añadidos tests de `agent_confidence_threshold` en `tests/test_config.py` y `tests/test_agent_stack_surface.py` nuevo (5 tests) — confirmado rojo (`ImportError` de colección + 5 fallos de `AttributeError`/`ValidationError` no lanzada).
- Green: `psycopg[binary]` añadido a `requirements.in` (comentario explicando el porqué), lockfile recompilado con `pip-compile` (`psycopg[binary]==3.3.4` + `psycopg-binary==3.3.4` en `requirements.txt`), instalado en `.venv`. `agent_confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)` añadido a `Settings` con docstring (mismo criterio que `rag_estado_weight`: default de arranque sin calibrar). `.env.example` documentado.
- Verificación: `pytest tests/test_agent_stack_surface.py tests/test_config.py` → 83 passed. Suite completa `pytest -q` → exit 0, sin regresiones. `ruff check` + `ruff format --check` + `mypy --strict` sobre ficheros tocados → limpio.
- Gate mutation (`cosmic-ray`, `module-path=app/core/config.py`): 76 jobs, 2 survivors (2.63%), `cr-rate --fail-over 20` → exit 0 (pasa el umbral break:80/fail-over 20). Los 2 survivors son `RemoveDecorator` sobre los `@classmethod` de los `field_validator` de `cors_origins`/`database_url` — preexistentes, no introducidos por esta tarea; por debajo del umbral de fallo, no se persiguen.
- `/sdd-lint`: N/A — tarea infra/config, no toca `spec.md`/CU/ADR (declarado en el Description de la tarea). Spot-check `grep -rn '\[NECESITA ACLARACIÓN'` sobre `.claude/specs/backend/` → limpio.
- `fact-checker`: subagente lanzado sobre 15 afirmaciones de la sesión. Resultado: 14 VERIFICADO, 1 NO VERIFICABLE (mutation gate no re-ejecutado por presupuesto de tiempo del verificador — reconocido; yo sí lo ejecuté con salida real en esta sesión), 0 INCORRECTO. Gate pasa.

## Cierre
- DoD completa. Tarea movida a `completed/`, `status: done`, `[x]` en el plan.
- Ficheros tocados: `backend/requirements.in`, `backend/requirements.txt`, `backend/app/core/config.py`, `backend/.env.example`, `backend/tests/test_config.py`, `backend/tests/test_agent_stack_surface.py` (nuevo), `backend/cosmic-ray.toml`.
- Follow-ups: ninguno nuevo. Sigue la tarea 02 (`app/rag/confidence.py`).
