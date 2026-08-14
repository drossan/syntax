# Session log — backend-skeleton-foundation-17 (Skeleton seeds/fixtures)

## 2026-08-13 — Arranque

Movida `pending → active`. Deps 08/09 `done`. Doc-only.

**Drift resuelto (una frase):** la tarea dice `app/seeds/` pero el Makefile cablea `make seed` →
`python -m app.infra.db.seed` (y el `db/__init__.py` lo documenta) → uso `app/infra/db/seed.py`
(autoritativo por el Makefile).

Fichero: `app/infra/db/seed.py`.

## 2026-08-13 — Cierre

**Resumen:** 1 fichero guión `app/infra/db/seed.py` (entry-point `python -m app.infra.db.seed` = `make
seed`): 14 capacidades + 6 roles semilla (matriz 02), tenant `syntax` + cliente demo, 1 usuario por rol
(Argon2), tickets/mensajes de ejemplo (public/internal) + muestra HITL, KB de muestra. Idempotente
(upsert por claves naturales); respeta RLS (`SET app.tenant_id`). Drift resuelto: `app/infra/db/seed.py`
(Makefile autoritativo) vs `app/seeds/` (texto de la tarea).

**Verificación:** `compileall` exit 0; grep código ejecutable → sin coincidencias; `make seed` →
`$(PY) -m app.infra.db.seed` confirmado.

**Gate `fact-checker` (sonnet):** **7/7 VERIFICADO** (incl. 6 roles == rbac 02).

**Docs:** 1 fichero nuevo. Plan: `[x]` 17 + Registro. **Tiempo real:** ~0.3 h.

**Follow-ups:** habilita el ejercicio manual login→ticket→draft→aprobación; 18 usa datos similares.
