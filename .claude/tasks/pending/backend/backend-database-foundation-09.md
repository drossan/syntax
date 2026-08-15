---
id: backend-database-foundation-09
package: backend
plan: database-foundation
status: pending
priority: 1
depends_on: [backend-database-foundation-07]
estimate: 2h
actual:
created: 2026-08-15
updated: 2026-08-15
---

# /health/ready + alias /health (DB + pgvector + dimensión) + deps.get_db_session

## Description

Cierra el readiness diferido en el plan anterior: `GET /health/ready` (y alias `GET /health`) comprueba que
la **DB es alcanzable**, la **extensión `vector` está instalada** y la **dimensión de la columna viva coincide
con `settings.embedding_dim`** (M3) → 200; si algo falla → **503 problem+json** con el `detail` del chequeo
que falló. `GET /health/live` sigue sin tocar DB. Resuelve el `HEALTHCHECK` rojo del servicio `api`. Añade
`deps.get_db_session` (dependency mínima que cede `AsyncSession`). Guión: `app/main.py`, `app/core/deps.py`.
Spec: `IMPLEMENTATION-GUIDE.md:126`, envelope problem+json (`api-contract.md`), NFR-003.

## Spec

- `app/core/deps.py`: `get_db_session()` → dependency FastAPI que cede una `AsyncSession` (de `session.py`) y
  la cierra. (Solo esto; `get_tenant_context`/RBAC → plan 10.)
- `GET /health/ready` (y alias `GET /health`): 200 `{status:"ready", ...}` si DB alcanzable **y** extensión
  `vector` presente **y** dimensión de `embedding.vector` == `settings.embedding_dim`; si no, **503**
  `application/problem+json` con `detail` del chequeo fallido (usa el envelope existente en `main.py`).
- `GET /health/live` **no cambia** (no toca DB). El middleware request-id sigue etiquetando estas respuestas.
- Montado en `create_app()` (sin efectos en import).
- **Timeout** acotado en la comprobación de DB (una DB colgada no debe hacer que `/health/ready` cuelgue
  indefinidamente → 503) — QA.

## Fuera de alcance

- Métricas / `/metrics`, hook Sentry → planes posteriores.
- `get_tenant_context`/`get_current_subject`/`require_capability` (RBAC) → plan 10.

## Scenarios (Gherkin)

<!-- SDD: infra/composición → Gherkin LOCAL, "sin cambios de spec/CU". Integración con httpx.ASGITransport +
     DB real (fixture). El caso de "DB caída" se simula (settings/engine apuntando a una DB inalcanzable). -->

```gherkin
Feature: readiness que comprueba la base de datos

  Scenario: ready con DB y pgvector correctos
    Given la DB migrada (extensión vector + dimensión 1536) alcanzable
    When se hace GET /health/ready
    Then el código es 200 And el cuerpo indica estado listo

  Scenario: el alias /health se comporta como /health/ready
    Given la DB migrada alcanzable
    When se hace GET /health
    Then el código es 200 (mismo comportamiento que /health/ready)

  Scenario: DB inalcanzable devuelve 503 problem+json
    Given una DB no alcanzable
    When se hace GET /health/ready
    Then el código es 503 And el cuerpo es application/problem+json con detail del fallo

  Scenario: dimensión de vector distinta a la configurada devuelve 503
    Given la columna embedding.vector con dimensión != settings.embedding_dim
    When se hace GET /health/ready
    Then el código es 503 (problem+json indicando el desajuste de dimensión)

  Scenario: liveness sigue sin tocar la DB
    Given la DB no alcanzable
    When se hace GET /health/live
    Then el código es 200 (liveness no depende de la DB)

  # ── Endurecido por scenario-coverage ──

  Scenario: extensión vector ausente devuelve 503
    Given la DB alcanzable pero sin la extensión vector instalada
    When se hace GET /health/ready
    Then el código es 503 (problem+json indicando extensión ausente)

  Scenario: DB alcanzable pero no migrada devuelve 503 controlado
    Given la DB alcanzable pero sin las tablas (no migrada)
    When se hace GET /health/ready
    Then el código es 503 controlado (no un 500 por excepción no capturada)

  Scenario: el alias /health propaga también los 503
    Given una DB no alcanzable
    When se hace GET /health
    Then el código es 503 (el alias propaga el fallo, no solo el 200)

  Scenario: una DB lenta no cuelga el readiness (timeout)
    Given una DB que no responde dentro del timeout
    When se hace GET /health/ready
    Then responde 503 dentro del timeout (no cuelga indefinidamente)
```

## Provides

`GET /health/ready` + alias `GET /health` operativos (el `HEALTHCHECK` de Docker deja de estar rojo) y
`deps.get_db_session` para los routers de planes posteriores. **Cierra el plan `database-foundation`.**

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor) — integración (`httpx.ASGITransport` + DB real).
- [ ] Cada escenario Gherkin tiene al menos un test (ready 200, alias, 503 DB caída, 503 dim, live sin DB).
- [ ] Todos los tests en verde (`make test` con `docker compose up -d db`).
- [ ] `Provides` disponible; sin efectos en import; el HEALTHCHECK de Docker resuelve.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre el chequeo de readiness (**código de comportamiento** en `main.py`/`deps.py`).
- [ ] Gate `/sdd-lint` sin ERROR (SDD: sin cambios de spec/CU — infra/composición).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings; `backend/README.md` (readiness ya operativo, HEALTHCHECK verde); session log.
- [ ] Cierre del plan: última tarea → PR de `plan/backend/database-foundation` a `main` (auto-pr; git-automation).
