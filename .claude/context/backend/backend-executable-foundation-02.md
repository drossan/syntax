# Session log — backend-executable-foundation-02

Tarea: **Scaffold de tests (`make test` verde) + ADR-0013 (arranque Fase 2)**.
Plan: `.claude/plans/active/backend/executable-foundation.md`. Rama: `plan/backend/executable-foundation`.
Tipo: **docs/scaffold** (el smoke test entra por el carve-out de testing.md §1; sin TDD rojo-primero).
Modo enseñanza: explicar conceptos (pytest, conftest, ADR/MADR) al owner (Python básico).

Append-only.

---

## 2026-08-15 — Arranque

- Tarea movida a `active/`, `status: active`. depends_on: 01 (done).
- Plan de acción: (1) ADR-0013 (MADR) arranque Fase 2 + supersede 0012 + `adr-index.md` + nota ADR-0001;
  (2) scaffold `backend/tests/` (`conftest.py` + `test_smoke.py`) → `make test` verde.
- Reparto: el asistente redacta ADR (doc) y propone el scaffold; el owner aplica/ejecuta. Con explicación
  didáctica de pytest/conftest/ADR.

## 2026-08-15 — Cierre

Entregables:
- **ADR-0013** (`0013-arranque-fase-2-backend-codigo-real.md`, MADR, accepted) — arranque Fase 2, supersede
  (parcial) 0012. `adr-index.md`: fila 0013 + 0012→`superseded (0013)`. `0012` status→superseded. Nota en
  `0001` (trunk-from-`main`, `dev` no adoptado, F8).
- **Scaffold tests**: `backend/tests/conftest.py` (placeholder documentado) + `test_smoke.py` (2 tests:
  Python≥3.12, `import app`). `make test` → **2 passed**.

Fix real durante el scaffold: `pytest` solo metía `tests/` en `sys.path`, no `backend/` → `import app`
fallaba (`ModuleNotFoundError`). Resuelto con `pythonpath = ["."]` en `[tool.pytest.ini_options]`
(`pyproject.toml`). El esqueleto nunca había corrido tests (era doc-only), por eso faltaba.

Gates (verificados con salida real):
- `make test` → 2 passed · `make lint` (ruff) verde (85 files) · `make typecheck` (mypy strict) verde.
- `/sdd-lint`: mecánicos limpios; semántico **0 ERROR, 1 AVISO** (`adr-index:8` fecha en bloque no cubría a
  0013) → **corregido** (acotado a 0001–0012 + línea para 0013). Gate limpio.
- `fact-checker`: **7/7 VERIFICADO** (subagente independiente).

Tiempo real: ~1h. Sin código de negocio (docs + scaffold).

## Follow-ups
- Tarea 03 (settings): añadir a `conftest.py` la fixture autouse que resetea `get_settings.cache_clear()`
  entre tests; primer `mutmut run`/`results` e2e (shakeout) sobre `config.py`.
