---
id: backend-skeleton-foundation-07
package: backend
plan: skeleton-foundation
status: done
priority: 2
depends_on: [backend-skeleton-foundation-01]
estimate: 2h
actual: 0.75h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton core + app factory + healthcheck

## Description

Esqueleto de `app/core/` (config, security, logging, deps) y el app factory `app/main.py`, más un
endpoint `/health`. Fija los cimientos transversales que consumen routers, DB y agentes. Solo esqueleto
+ guión.

## Spec

- `app/core/config.py` — **settings inyectables** con Pydantic `BaseSettings` (DB URL, JWT, OpenAI,
  LangSmith, APP_ENV). Guión: **sin efectos secundarios en import** (no validar/crear credenciales al importar).
- `app/core/security.py` — guión de: hash argon2, emisión/verificación JWT (access+refresh), claims
  `sub/tenant_id/roles`, dependencia `get_current_subject`.
- `app/core/logging.py` — logging estructurado + **request-id** (middleware de correlación).
- `app/core/deps.py` — dependencias comunes (sesión DB, contexto de tenant `get_tenant_context`, autorización).
- `app/main.py` — factory `create_app()`: registra routers (placeholder), middleware (request-id, CORS),
  y `GET /health` que comprueba **DB + extensión pgvector** alcanzables.

## Refuerzos (scenario-coverage)

- **Throttling** de `/auth/login` y `/auth/refresh` (B.1, promovido) — middleware (in-memory/Redis).
- **Observabilidad de errores** (hook tipo Sentry) + **métricas** básicas (`/metrics`: latencia IA,
  contadores de aprobación/errores).
- Autorización: **capacidades resueltas server-side por request** (no en el token) (A1.7).
- `/health` con split **liveness/readiness**.
- `security.py`: soporte de **rotación + reuse-detection** de refresh contra `RefreshSession` (03) y
  **logout server-side** (invalidar sesión), no solo borrar cookie.

## Fuera de alcance

- Implementar la lógica (solo esqueleto + guión). Autorización RBAC completa (spec en 02; se referencia).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- Los settings son inyectables y el guión prohíbe efectos en import.
- `main.py` expone `create_app()` con middleware de request-id y `GET /health` (DB + pgvector).
- `security.py`/`deps.py` documentan JWT (access+refresh), contexto de tenant y el punto de autorización.

## Provides

- `app/core/*` + `app/main.py` + `/health`. 08 (sesión DB), 09 (LLM), 10/11/12 (deps/autorización) cuelgan de aquí.

## Definition of Done

- [x] Ficheros core (`config/security/logging/deps.py`) + `main.py` (con `/health`) creados, cada uno con su guión docstring. `compileall` OK.
- [x] Guión: settings inyectables sin efectos en import; middleware request-id; `/health` liveness/readiness comprueba DB+pgvector.
- [x] `Provides` disponible para las dependientes (08/09/10/11/12 cuelgan de core + main).
- [x] Gate de `fact-checker` superado (sonnet): 8/8 VERIFICADO.
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-07.md`.
