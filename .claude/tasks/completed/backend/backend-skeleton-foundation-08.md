---
id: backend-skeleton-foundation-08
package: backend
plan: skeleton-foundation
status: done
priority: 2
depends_on: [backend-skeleton-foundation-03, backend-skeleton-foundation-07]
estimate: 3h
actual: 1h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton capa DB + Alembic + RLS

## Description

Esqueleto de `app/infra/db/` (modelos SQLAlchemy 2 async, sesión, repos ports+stubs) y el scaffold de
Alembic, incluyendo las **políticas RLS** y el mecanismo `SET app.tenant_id`. Materializa el data-model
(03). Solo esqueleto + guión, **con avisos de riesgo explícitos**.

## Spec

- `app/infra/db/base.py` (DeclarativeBase), `session.py` (async engine + sessionmaker), `models/` (una
  clase por entidad de 03, con guión de columnas/relaciones/índices; `Embedding.vector` con dimensión de config).
- `app/domain/ports/repositories.py` (interfaces) + `app/infra/db/repositories/` (stubs) que **filtran por
  `tenant_id`** (aislamiento app-level).
- `alembic/` (env.py async, `versions/` con guión de la migración inicial + **`ENABLE ROW LEVEL SECURITY`
  + `CREATE POLICY tenant_isolation`** en las tablas de negocio; extensión `vector`; índice pgvector).
- **`SET app.tenant_id` por conexión**: guión del evento del engine async (`SET`/`SET LOCAL`, alcance
  transaccional).
  > ⚠️ **GUIÓN DE RIESGO (footgun)**: `SET app.tenant_id` sobre pool asyncpg reutiliza conexiones — usar
  > `SET LOCAL` dentro de transacción o resetear en el checkin; **exige tests de integración** contra
  > Postgres real al implementar (un mock no lo caza). Documentarlo en el propio fichero.

## Fuera de alcance

- Implementar migraciones/queries reales (solo esqueleto + guión). Tablas KB **sin RLS de tenant** (globales).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- Hay una clase-modelo por entidad de 03; las de negocio llevan `tenant_id`; las de KB no llevan RLS.
- El scaffold Alembic incluye guión de RLS (ENABLE + POLICY) + extensión vector + índice pgvector.
- El guión de `SET app.tenant_id` incluye el aviso del footgun y la exigencia de tests de integración.
- Los repos-stub filtran por `tenant_id` y respetan las interfaces de `domain/ports`.

## Provides

- `app/infra/db/*` (modelos/sesión/repos) + `alembic/` + puertos de repositorio + RLS scaffolding.
  10 (servicios) usa los puertos; 13/14/17 (ingestión/retriever/seeds) usan sesión y modelos.

## Definition of Done

- [x] Modelos/sesión/repos-stub + Alembic (env.py + 0001 guión) + RLS + `SET app.tenant_id` creados con guión (8 ficheros). `compileall` OK.
- [x] Aviso de footgun (pool asyncpg) + exigencia de tests de integración presentes en `session.py`.
- [x] KB global sin RLS; dimensión vector desde config (`EMBEDDING_DIM`); repos filtran por `tenant_id`.
- [x] `Provides` disponible para las dependientes (10 usa ports; 13/14/17 sesión+modelos).
- [x] Gate de `fact-checker` superado (sonnet): 7/8 VERIFICADO + F2 INCORRECTO (afirmación literal de grep) corregido en el fichero y re-verificado (grep sin coincidencias, compileall OK).
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-08.md`.
