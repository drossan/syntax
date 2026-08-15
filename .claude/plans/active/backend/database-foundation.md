---
id: backend-database-foundation
package: backend
status: active
branch: plan/backend/database-foundation
created: 2026-08-15
updated: 2026-08-15
---

# Backend — Capa de datos + RLS multi-tenant + readiness (schema · migración · session · repos base · /health/ready)

## Contexto y problema

El plan `executable-foundation` (cerrado) dejó el backend **ejecutable** con las primitivas transversales
(config, security, logging, app factory, `/health/live`). La **capa de datos sigue en esqueleto doc-only**:
`app/infra/db/*` y `alembic/*` son guiones sin código, `Settings` no tiene `DATABASE_URL`, Alembic no está
configurado (faltan `alembic.ini` + `script.py.mako`) y `/health/ready` + alias `/health` responden 404 (el
`HEALTHCHECK` del servicio `api` de Docker está rojo por eso). Sin capa DB no hay dónde persistir ni cómo
aislar tenants.

Este es el **plan 2 del roadmap** (build-order `IMPLEMENTATION-GUIDE.md §2`, "tarea 08"): materializa el
schema real, las **políticas RLS de aislamiento multi-tenant día 1** (ADR-0006), la sesión async con el
manejo correcto del **footgun `SET app.tenant_id` en pool asyncpg**, unos **repos base tenant-aware**, la
migración inicial Alembic y el **readiness** que comprueba DB + extensión pgvector.

> **Modo de trabajo** (heredado): el código lo escribe el owner con TDD (o el asistente si el owner lo pide);
> el asistente redacta tareas/escenarios, guía, propone diffs, redacta docs/ADRs y corre los gates.

## Objetivos

1. **Configuración de DB inyectable (dos identidades de conexión).**
   - *Criterio de éxito*: `Settings` expone `database_url` (runtime, rol **`syntax_app`** no-superuser),
     `migration_database_url` (superuser, para Alembic + bootstrap del rol) y `embedding_dim` (leídos de
     `.env`, hoy ignorados por `extra="ignore"`); un test inyecta los tres sin tocar `.env`.

2. **Modelo de datos ORM completo y determinista.**
   - *Criterio de éxito*: `Base(DeclarativeBase)` con `naming_convention` (diffs estables) + mixins
     (`TimestampMixin`, `TenantMixin`); las **18 entidades** del `data-model.md` (identidad/RBAC + negocio +
     KB) con sus enums, FKs/cascadas y `embedding.vector = vector(EMBEDDING_DIM)`. El dominio no importa
     SQLAlchemy (hexagonal, NFR-003).

3. **Sesión async con contexto RLS seguro.**
   - *Criterio de éxito*: `create_async_engine` (asyncpg) + `async_sessionmaker(expire_on_commit=False)` sin
     efectos en import; un helper fija el contexto de tenant con **`SET LOCAL app.tenant_id`** (alcance
     transaccional) y lo resetea, de modo que una conexión reutilizada del pool **no** filtra entre tenants.

4. **Migración inicial real (Alembic) con RLS.**
   - *Criterio de éxito*: `alembic upgrade head` sobre una DB limpia crea la **extensión `vector`**, las 18
     tablas + enums + índices (unicidad/compuestos; **sin índice ANN**, diferido a RAG), y habilita **RLS +
     `CREATE POLICY tenant_isolation`** en las **7 tablas de negocio** (KB e identidad/RBAC **sin** RLS).

5. **Aislamiento multi-tenant verificado con integración (footgun).**
   - *Criterio de éxito*: contra Postgres real y **conectando como `syntax_app`** (no-superuser → RLS aplica),
     con el contexto en tenant A una query de negocio solo ve filas de A; una **conexión reutilizada del pool**
     para tenant B no ve datos de A; el ámbito `global` (Soporte) opera cross-tenant **activando el GUC de
     bypass por transacción** (`SET LOCAL`); KB e identidad no filtran por tenant. NFR-002 / ADR-0006.

6. **Repos base tenant-aware (defensa en profundidad app-level).**
   - *Criterio de éxito*: un `BaseRepository` genérico ofrece CRUD (get/list/add/delete) **filtrado por
     `tenant_id`** (primera línea de defensa, sobre RLS); probado contra la DB de test con una entidad real.

7. **Readiness fiable.**
   - *Criterio de éxito*: `GET /health/ready` (y alias `GET /health`) → **200** si DB alcanzable **y**
     extensión `vector` presente; **503 problem+json** si no; `/health/live` sigue sin tocar DB.

## Alcance y fuera de alcance

### Dentro del alcance
- `app/core/config.py`: `database_url` (rol `syntax_app`) + `embedding_dim`, **ambos con default** (DSN dev de
  `syntax_app` + `1536`) para no romper los tests/boot existentes (L2). **`MIGRATION_DATABASE_URL` NO va en
  `Settings`** — lo lee `alembic/env.py` directo del entorno (least-privilege: el proceso API no arranca con
  credenciales superuser que no usa) (L1).
- **Bootstrap del rol (fuera de Alembic)**: `syntax_app` (NOSUPERUSER NOBYPASSRLS) se crea en un **init script**
  (`docker-entrypoint-initdb.d/*.sql` para local + paso ops documentado para prod); su **password se fija
  out-of-band** (`ALTER ROLE`, desde env), no en una migración; rotación = paso explícito (M1/M2).
- `.env.example` + `docker-compose.yml` (`api`): `DATABASE_URL` apunta a **`syntax_app`** (no al superuser), o
  `make run`/compose correría con RLS apagado (H1). El superuser queda solo para migraciones/bootstrap.
- `app/infra/db/base.py`: `DeclarativeBase` + `naming_convention` + mixins `TimestampMixin`/`TenantMixin`.
- `app/infra/db/models/`: las 18 entidades + 13 enums + FKs/cascadas + `vector(EMBEDDING_DIM)` (3 tareas por
  frontera RLS: identidad/RBAC · negocio · KB).
- `app/infra/db/session.py`: engine async (runtime `syntax_app`) + `async_sessionmaker(expire_on_commit=False)`
  + `get_session()` + **helper de contexto RLS** (`SET LOCAL app.tenant_id`; y el GUC de bypass por
  transacción para el ámbito global). Sin efectos en import.
- `app/infra/db/repositories/`: `BaseRepository` genérico tenant-aware (CRUD con filtro `tenant_id`).
- `app/core/deps.py` (**mínimo**): `get_db_session` (dependency que cede `AsyncSession`) — solo lo que necesitan
  `/health/ready`, los repos base y los tests; `get_tenant_context`/`get_current_subject`/`require_capability`
  (RBAC) → plan 10.
- Alembic real: `alembic.ini` + `alembic/env.py` (online async, lee `MIGRATION_DATABASE_URL` del entorno) +
  `script.py.mako` + `0001_initial_schema.py` (corre como **superuser**): **GRANTs DB-scoped a `syntax_app`**
  (el rol ya existe, se creó en el bootstrap), `CREATE EXTENSION vector`, las 18 tablas + enums + índices
  (unicidad/compuestos, **sin índice ANN**), la columna `embedding.vector` con **literal `vector(1536)`** (no
  `EMBEDDING_DIM` en runtime — misma revisión = mismo schema; cambiar dim = migración nueva, M3), y **ENABLE
  RLS + `CREATE POLICY`** en las **7 tablas de negocio**. **Predicado exacto de la política** (H2):
  `USING (current_setting('app.bypass_rls', true) = 'on' OR tenant_id = current_setting('app.tenant_id', true)::uuid)`
  con el **mismo `WITH CHECK`** (forma de 2 args `missing_ok=true` → fail-closed si el GUC no está, no lanza).
- `app/main.py`: `GET /health/ready` + alias `GET /health` (DB alcanzable + extensión `vector` + **dimensión de
  la columna viva == `settings.embedding_dim`**, M3) → 200, o **503 problem+json** con `detail` del chequeo que falló.
- **Infra de test de integración** (dos estrategias, H5): (a) tests de integración ordinarios → **rollback por
  transacción** (compatible con `SET LOCAL`); (b) **suite RLS/footgun** → conexión como **`syntax_app`** con
  filas **commiteadas** y limpieza por **`TRUNCATE`** (una transacción envolvente haría el test vacuo y pasaría
  incluso con el bug `SET` de sesión). Fixture session-scoped crea/migra `syntax_test` (superuser) una vez; si
  `db` no está alcanzable, los tests de integración **fallan con error claro**. Sin dependencias nuevas.
- **Gates de invariante de esquema/RLS** (H3/H4): (i) test de **drift** `compare_metadata` (autogenerate →
  diff vacío) modelos↔`syntax_test`; (ii) test que, para **cada** tabla con `tenant_id`, asserta
  `pg_class.relrowsecurity = true` + existe policy `tenant_isolation` (y que KB/identidad **no** la tienen).
- **ADR-0016**: aplicación de RLS vía rol dedicado no-superuser + GUC de bypass por transacción (refina ADR-0006).

### Fuera de alcance
- **Repos concretos que implementan los puertos de dominio** y la **lógica de negocio** → **plan de dominio (10)**
  (aquí solo el `BaseRepository` genérico; los puertos aún no existen).
- **`deps.py` RBAC completo** (`get_current_subject` con capacidades server-side, `require_capability`) → plan 10.
- **Lógica de auth** (rotación/reuse-detection de `refresh_session`, canje de `auth_token`) → plan de auth. Sus
  **tablas sí** se crean aquí (van en la migración inicial).
- **Índice ANN de pgvector** (ivfflat/hnsw) y **poblado de embeddings/KB** → plan RAG (13/14). Aquí solo la
  extensión + la columna `vector(N)`.
- **Seeds** (`app/infra/db/seed.py`) → tarea 17.
- Dominio/servicios (10), routers (11/12), agente/checkpointer HITL (15/16), scheduler SLA (18).
- **`testcontainers`**: descartado (no añadir dependencia); se usa el `db` de docker-compose + DB de test dedicada.

> **Nota de churn (M6/L3, design-review)**: aunque las 18 tablas van en una migración inicial (el grafo de FKs
> lo justifica: no hay `ticket` sin `tenant`/`user`), las más propensas a **migraciones de seguimiento** son
> `agent_run` (forma de `sources` JSONB), `embedding.vector(N)` (cambiar dimensión = migración nueva + re-embed)
> y las `kb_*` (features 13/14/15/16); además el **`PostgresSaver` de LangGraph crea sus propias tablas** fuera
> de esta migración (plan del agente). Los **enums nativos** que crecen (`message_visibility` gana `developer`;
> `notification_type`/capacidades extensibles) se amplían con `ALTER TYPE ADD VALUE` (con sus restricciones en
> transacción). El schema **no** se declara "cerrado día 1".

## Recursos externos

- Build-order: `backend/IMPLEMENTATION-GUIDE.md` (§2 tarea 08, §3 entorno `DATABASE_URL`/`EMBEDDING_DIM`, §6
  footgun RLS + coste de cambiar `EMBEDDING_DIM`).
- Specs: `.claude/specs/backend/data-model.md` (18 entidades, §6 RLS `:172-185`, §8 dimensión pgvector, §9
  índices), `.claude/specs/backend/rbac.md §5` (app-level + RLS + `SET app.tenant_id`), `.claude/specs/backend/
  spec.md` (**FR-013/014/015**, **NFR-002**, **NFR-003**, **SC-001**), `.claude/specs/general/testing.md` (§4
  niveles, §5 determinismo — puerto `clock`), `.claude/specs/general/coding-standards.md`.
- ADRs: **0006** (aislamiento app-level + RLS día 1, KB global sin RLS), **0010** (pgvector, dimensión desde
  config), 0013 (arranque Fase 2). `/health/ready` es deliverable de **ops/guión** (no hay FR/NFR ni entrada de
  contrato): `IMPLEMENTATION-GUIDE.md:126`, `main.py` docstring, plan anterior.
- Infra: `docker-compose.yml` (`db: pgvector/pgvector:pg16` + healthcheck), `Dockerfile` (HEALTHCHECK → `/health`),
  `Makefile` (`migrate`/`seed`/`run`). Deps ya instaladas: sqlalchemy 2.0.52, asyncpg 0.31.0, alembic 1.19.1,
  pgvector 0.5.0.

## Estimación global

- **Tareas**: ~8 (config · base · models · session+test-infra · alembic+migración · RLS integración · repos base
  · /health/ready). El nº y el corte fino de `models` se cierran en `grilling`/`design-review`.
- **Esfuerzo**: ~4–5 sesiones. Riesgo concentrado en: (1) el footgun RLS y su test de integración (pool async);
  (2) Alembic async + migración con RLS/extensión; (3) la fixture de test-DB con rollback compatible con `SET LOCAL`.
- **Recursos**: owner (o asistente) + Docker local con `db` levantado (integración obligatoria); sin cloud.

## Criterios de calidad y verificación

- **TDD** con test rojo 1:1 del Gherkin. **Niveles** (testing.md §4 / HOW-TO): config → unit; base/models →
  unit (metadata/estructura); **session, migración, RLS, repos base, /health/ready → integración** contra
  Postgres+pgvector Docker (RLS **obligatoria**, footgun no cazable con mocks).
- **Gates de cierre por tarea**: `make test` verde · `ruff` (+`S`) + `ruff format --check` · `mypy` strict ·
  **cosmic-ray `break: 80`** · `/sdd-lint` · `fact-checker`. **Alcance de la mutation gate** (M4): solo el
  **código de comportamiento** (helper de contexto RLS de `session.py`, filtro `tenant_id` del `BaseRepository`,
  chequeo de `/health/ready`); los ficheros **declarativos** (`models/*.py`, `0001_*.py`, `base.py`) quedan
  **fuera** (mutantes de bajo valor + rerun de integración carísimo por mutante) — se documenta el N/A por tarea.
- **Determinismo** (testing.md §5): tiempo vía puerto `clock`; el orden del contrato se **asserta**, no se asume.
- **Precondición de integración**: `docker compose up -d db` + DB de test `syntax_test` migrada. Definir el
  arranque (target Make o fixture) para que `make test` no dependa de estado manual.
- **Hexagonal**: `app.domain` no importa `app.infra`; RLS es defensa en profundidad, el filtro app-level en repos
  es la primera línea; cero secretos en código.
- **SDD**: hay CU de actor para el aislamiento (**CU-BE-03**, autorización y aislamiento tenant) → las tareas de
  RLS **trazan/enlazan** a CU-BE-03; el resto (infra pura: config/base/models/session/alembic/health) → Gherkin
  local "sin cambios de spec/CU". Sin inventar CUs para infra.

## Tasks

*(Materializadas tras grilling; el Gherkin definitivo se endurece con `scenario-coverage`.)*

- [x] `backend-database-foundation-01` (P1) — Settings `database_url` (syntax_app, con default) + `embedding_dim` (default 1536) + `.env.example`/compose a `syntax_app`; `MIGRATION_DATABASE_URL` solo en entorno · depends_on: —
- [x] `backend-database-foundation-02` (P1) — `base.py`: DeclarativeBase + naming_convention + mixins Timestamp/Tenant · depends_on: 01
- [ ] `backend-database-foundation-03` (P1) — Modelos identidad/RBAC (8 tablas, sin RLS) + enums · depends_on: 02
- [ ] `backend-database-foundation-04` (P1) — Modelos negocio (7 tablas, TenantMixin/RLS-marked) + enums · depends_on: 03
- [ ] `backend-database-foundation-05` (P1) — Modelos KB (3 tablas + `vector(1536)` literal; modelo `vector(EMBEDDING_DIM)`) + enums · depends_on: 04
- [ ] `backend-database-foundation-06` (P1) — Init script (rol `syntax_app`) + Alembic (config + env async + `script.py.mako`) + migración `0001` (GRANTs + extensión + tablas/índices no-ANN + RLS-policy con bypass en 7 negocio) + fixture test-DB + **test drift `compare_metadata`** + **smoke `relrowsecurity`** (7 negocio true / KB+identidad false) · depends_on: 05
- [ ] `backend-database-foundation-07` (P1) — `session.py` (engine `syntax_app` + sessionmaker + helper contexto RLS + GUC bypass) + tests de aislamiento (footgun/global: conexión `syntax_app`, commit + `TRUNCATE`) · depends_on: 06 · **traza CU-BE-03**
- [ ] `backend-database-foundation-08` (P1) — `BaseRepository` tenant-aware (CRUD + filtro `tenant_id`) · depends_on: 07
- [ ] `backend-database-foundation-09` (P1) — `/health/ready` + alias `/health` (DB + pgvector + dim viva == settings) + `deps.get_db_session` · depends_on: 07

> Orden: 01 → 02 → 03 → 04 → 05 → 06 → 07 → (08, 09). Una sola tarea `active` por plan.

## Notas de arranque

- **Rama**: `plan/backend/database-foundation` desde `main` (convención de facto del repo; `executable-foundation`
  ya está en `main`).
- **ADRs**: **ADR-0016** (aplicación de RLS con rol dedicado no-superuser `syntax_app` + GUC de bypass por
  transacción para el ámbito global; refina ADR-0006) — se redacta en la tarea de migración/session (06/07).
  0010 ya cubre pgvector.
- **Docker**: la integración exige `docker compose up -d db`; el plan define el arranque de la DB de test.

## Registro de cambios del plan

- 2026-08-15: creado (draft para aprobación). Decisiones de arranque (owner): (1) test-DB **dedicada
  `syntax_test` + rollback por transacción** (sin `testcontainers`); (2) **incluir repos base CRUD** tenant-aware
  además de schema/session/RLS; (3) **diferir el índice ANN** de pgvector al plan RAG (solo extensión + columna
  `vector(N)` aquí).
- 2026-08-15: refinado con `grilling` (6 decisiones). **Hecho clave**: el rol `POSTGRES_USER` (`syntax`) es
  superusuario → salta RLS; con la app conectando como `syntax` las políticas no filtrarían nada. Decisiones:
  (D1) **rol `syntax_app` no-superuser** para el runtime (RLS aplica de verdad); (D2) ámbito global vía **GUC de
  bypass por transacción** (`SET LOCAL`), cableado RBAC → plan 10; (D3) **`CREATE ROLE syntax_app` + GRANTs en la
  migración `0001`** (DO block idempotente, password por env); (D4) config con **`DATABASE_URL`** (syntax_app) +
  **`MIGRATION_DATABASE_URL`** (superuser); (D5) **fixture test-DB auto** (crea+migra `syntax_test`) + rollback
  por transacción, **falla claro** si `db` no está arriba; (D6) modelos en **3 tareas** por frontera RLS. Neto:
  **9 tareas**; **ADR-0016** (refina 0006). Defaults fijados: enums nativos, sin `FORCE RLS` (rol no-propietario),
  migración a mano, `deps` = solo `get_db_session`, `/health/ready` 503 problem+json. **Aviso operativo**: la
  mutation gate de las tareas de integración corre contra Postgres real por mutante → más lenta (posible subir
  `timeout` en `cosmic-ray.toml`).
- 2026-08-15: endurecido con `design-review` (subagente opus; verdicto: sólido pero con 5 huecos correctness-
  blocking). **Aplicados HIGH**: (H1) `.env.example`+compose `api` → `syntax_app` (si no, `make run`/compose con
  RLS apagado); (H2) predicado de política exacto con **bypass GUC** + `current_setting(...,true)` de 2 args +
  mismo `WITH CHECK`; (H3) test de **drift** `compare_metadata`; (H4) test de invariante **`relrowsecurity`** por
  tabla con `tenant_id`; (H5) suite RLS/footgun con estrategia **distinta** (conexión `syntax_app` + commit +
  `TRUNCATE`), separada del rollback-por-transacción genérico. **MEDIUM/LOW**: (M3) migración con literal
  `vector(1536)` + `/health/ready` asserta dim viva; (M4) mutation gate **solo** sobre código de comportamiento
  (excluye modelos/DDL); (M5) smoke de `relrowsecurity` en la 06; (M6) nota de churn; (L1) `MIGRATION_DATABASE_URL`
  solo en entorno (no en `Settings`); (L2) defaults en los settings de DB. **Reabiertas y decididas por owner**:
  **revertida D3** → el rol `syntax_app` se crea **fuera de Alembic** (init script + password out-of-band); en la
  migración solo GRANTs (M1/M2). `BaseRepository` **se mantiene** (especulativo aceptado, puede remodelarse en el
  plan 10) (L5). **Resiste** (validado por el reviewer): ANN diferido, sin `FORCE RLS`, `deps` limitado, orden de
  dependencias, `/health/ready` 200/503, reúso de `db` de compose.
- 2026-08-15: endurecido con `scenario-coverage` (subagente QA sonnet, 8 dimensiones sobre las 9 tareas).
  **(A) Dentro de alcance — incorporados**: **07** reset del GUC `bypass_rls` entre conexiones del pool (footgun
  espejo), `WITH CHECK` rechaza escritura cross-tenant, `tenant_id` malformado → error controlado, GUC descartado
  en ROLLBACK, solo `'on'` activa el bypass, y **corrección técnica**: `SET LOCAL` no admite bind params → usar
  `set_config(...,true)` + validar UUID; **06** idempotencia (upgrade x2, downgrade→upgrade, rol sobrevive, init
  idempotente), `rolsuper/rolbypassrls=false`, GRANTs en las 18, `MIGRATION_DATABASE_URL` ausente → error claro,
  drift meta-test que confirma detección de cambio de dimensión, fixture reutiliza `syntax_test`, CHECK de rango;
  **05** `Vector(1536)` **literal** (evita acoplamiento import-time + falso negativo de drift), `uc_id` único
  (FR-032), `embedding` 1:1, enums exactos; **03/04** unicidades, `parent_id` self-FK, enums de **conjunto exacto**
  (no "contiene"), índices §9, cascadas completas; **01** `embedding_dim` `gt=0` + DSN vacío; **09** extensión
  ausente/no-migrada → 503, alias propaga 503, timeout; **02** plantillas fk/pk + sin colisión de FK; **08** lista
  vacía, doble delete idempotente, IntegrityError. **Decisiones owner**: modelo `Vector(1536)` literal; **CHECK**
  de rango en la migración (`csat` 1..5, `confidence` 0..1, `role.tenant_id` NULL sii system).
  **(B) Fuera de alcance — mantenidos diferidos** (nota owner): paginación de `list` (plan 10), autorización de la
  rama `global`/bypass (RBAC plan 10), lógica auth/reuse-detection (plan auth), transiciones/idempotencia de
  dominio (10+), ANN (RAG). **Nota de secuencia**: los seeds (tenant-sistema + roles `system`) son la tarea 17
  pero el plan de dominio (10) los necesita para probar RBAC e2e → dependencia de orden entre planes.
