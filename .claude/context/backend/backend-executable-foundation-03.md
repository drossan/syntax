# Session log — backend-executable-foundation-03

Tarea: **Settings inyectables + CORS_ORIGINS** (`app/core/config.py`). Primer **código real (TDD)** del
backend. Plan: `.claude/plans/active/backend/executable-foundation.md`. Rama: `plan/backend/executable-foundation`.
Modo enseñanza (owner Python básico): explicar cada concepto (pydantic-settings, lru_cache, fixtures, TDD).

Append-only.

---

## 2026-08-15 — Arranque

- Tarea movida a `active/` (`git mv`), `status: active`. depends_on: 02 (done).
- Ficheros a crear: `backend/tests/test_config.py` (tests) + `backend/app/core/config.py` (implementación).
- Ciclo TDD escenario por escenario (rojo → verde → refactor); cierre con `mutmut` (shakeout), `sdd-lint`,
  `fact-checker`. El owner escribe el código; el asistente guía/propone + explica.

## 2026-08-15 — TDD de config.py + gate de mutation

Implementado `app/core/config.py` (Settings pydantic-settings + `get_settings` lru_cache + validator CORS)
por TDD, escenario por escenario (19 tests en `tests/test_config.py`). Fixture autouse: baseline `JWT_SECRET`
+ `cache_clear` (aísla del `.env` real). Modo enseñanza (owner Python básico).

### Gate de mutation — saga (F3 materializado)
- `mutmut` 3.7.0 **no puntuó** `config.py`: su trampoline no instrumenta funciones decoradas
  (`@field_validator`/`@classmethod`, `@lru_cache`) ni campos de clase pydantic → «could not find any test
  case for any mutant». Spike (conftest raíz, debug, inspección de `mutants/`) confirmó el límite; sin fix rápido.
- Decisión owner: evaluar `cosmic-ray` → funciona (AST-based, in-place). Sobre `config.py`: 12 mutantes, 11
  muertos, **1 superviviente equivalente** (quitar `@classmethod` de un validator que no usa `cls`) → survival
  8.33% = **score 91.7% ≥ 80**. cosmic-ray destapó un hueco real: el **default** `jwt_access_ttl=900` no
  estaba testeado (el `.env` lo enmascaraba) → añadido `test_jwt_access_ttl_defaults_to_900` (`Settings(_env_file=None)`).
- **Adoptado cosmic-ray** como herramienta de mutation del backend (**ADR-0014**): `task-pipeline.yml`
  (`mutation-tool: cosmic-ray` + `mutation-command: "make mutation"`), `backend/cosmic-ray.toml`, target
  `make mutation`; `mutmut` retirado (deps + `[tool.mutmut]`). ADR de structlog renumerada 0014→0015.
- Tooling añadido en el camino: `pytest-watcher` (`make test-watch`); whitelist `S105/S106` en `tests/**`.

### Verificación (salida real)
- `make test` → 19 passed · `make lint` (ruff) verde · `make typecheck` (mypy strict) verde.
- `make mutation` → survival 8.33%, exit 0 (gate verde).

## Follow-ups
- El scope de `cosmic-ray` por tarea es **manual** (editar `module-path`/`test-command` en `cosmic-ray.toml`).
- Los tests leen el `.env` real salvo con `_env_file=None`; valorar aislarlo por defecto en el conftest.
