# Session log — backend-skeleton-foundation-08 (Skeleton capa DB + Alembic + RLS)

## 2026-08-13 — Arranque

**Estado:** tarea movida `pending → active` (`status: active`, `updated: 2026-08-13`). Deps 03 + 07
`done`. Doc-only skeleton (ficheros + guión, con avisos de riesgo explícitos).

**Aviso de alcance (una frase):** el `app/infra/db/__init__.py` (de 01) nombra `models.py`, pero la spec
de la 08 pide `models/` (una clase por entidad) → sigo la spec de la tarea (`models/` paquete) y lo dejo
anotado como drift menor de los docs de scaffold.

**Verificaciones previas (esta sesión):**
- `app/infra/db/__init__.py` ya trae el guión (models/session/repos/seed/alembic) + el **footgun**
  `SET app.tenant_id` sobre pool asyncpg → aislamiento app-level + RLS + tests de integración.
- `app/domain/__init__.py` fija el guión de dominio + puertos (repos, LLM, embeddings, notif, vector).
- data-model (03) leída esta sesión: entidades/enums/RLS/cascadas → base de `models/` y de las políticas.

Ficheros a crear (8): `db/base.py`, `db/session.py` (footgun SET app.tenant_id), `db/models/__init__.py`
(todas las entidades de 03 + marca RLS), `db/repositories/__init__.py` (stubs, filtro tenant_id),
`domain/ports/__init__.py`, `domain/ports/repositories.py` (interfaces), `alembic/env.py`,
`alembic/versions/0001_initial_schema.py` (guión migración inicial + RLS + extensión vector + índice).

## 2026-08-13 — Cierre

**Resumen:** Creados 8 ficheros de esqueleto (guión docstring) de la capa DB en `backend/`:
`app/infra/db/base.py` (DeclarativeBase + naming_convention + mixins Timestamp/Tenant),
`app/infra/db/session.py` (engine async asyncpg + sessionmaker + contexto RLS **con el footgun**),
`app/infra/db/models/__init__.py` (las 18 entidades de 03 agrupadas, marca RLS, `vector(N)` desde config),
`app/infra/db/repositories/__init__.py` (stubs SQLAlchemy que filtran por `tenant_id`; KB sin filtro),
`app/domain/ports/__init__.py` + `app/domain/ports/repositories.py` (interfaces de repositorio, firmas en
tipos de dominio), `alembic/env.py` (env async, target_metadata), `alembic/versions/0001_initial_schema.py`
(guión de la migración inicial: `CREATE EXTENSION vector`, tablas+cascadas de 03, índices incl. pgvector,
**RLS `ENABLE`+`CREATE POLICY tenant_isolation`** en negocio; KB/identidad sin RLS de tenant).

**Decisiones técnicas + porqué:**
- **Ficheros guión-only** (patrón 01): el owner implementa a mano.
- Drift resuelto: `db/__init__.py` decía `models.py`; seguí la spec de la 08 (`models/` paquete).
- **Footgun `SET app.tenant_id`** en `session.py`: `SET LOCAL` transaccional o RESET en checkin; aislamiento
  primario app-level en repos + RLS como defensa; **exige tests de integración contra Postgres real** al
  implementar (un mock no lo caza).

**Verificación en sesión (bucle principal):** `compileall` exit 0; grep de líneas de código ejecutable en
los 8 → sin coincidencias (tras la corrección de F2).

**Verificación (gate `fact-checker`, subagente fresco, sonnet por config):** **7/8 VERIFICADO + 1
INCORRECTO (F2)**. F2: mi afirmación literal "el grep no devuelve coincidencias" era falsa — la línea 31
de `0001_initial_schema.py` (`revision = "..."; down_revision = None.`) estaba dentro del docstring pero
parecía una asignación y disparaba el grep (la propiedad de fondo —solo docstring, sin código, compileall
OK— sí se cumplía). **Corregido**: reescrita esa línea como prosa; re-verificado en sesión (grep exit 1
sin coincidencias, compileall exit 0). INCORRECTO resuelto. F1/F3–F8 VERIFICADO (existencia, compileall,
footgun, marca RLS+vector config, migración RLS+extensión+índice, repos filtran tenant/KB no, 18
entidades == 03).

**Docs:** 8 ficheros nuevos. Plan: `[x]` tarea 08 + Registro.

**Ficheros/commits:** `backend/app/infra/db/{base,session}.py`, `app/infra/db/models/__init__.py`,
`app/infra/db/repositories/__init__.py`, `app/domain/ports/{__init__,repositories}.py`,
`backend/alembic/{env.py,versions/0001_initial_schema.py}` (nuevos); task 08 pending→active→completed;
session log; plan. (Commit pendiente de que el owner lo pida.)

**Tiempo real:** ~1 h.

**Follow-ups:** 09 (puerto LLM/embeddings/LangSmith) de core; 10 (servicios) usa `domain/ports`; 13/14/17
(ingestión/retriever/seeds) usan sesión+modelos. Al implementar 08: **tests de integración RLS** (footgun)
+ decidir ivfflat vs hnsw en la migración; falta materializar `alembic.ini` + `script.py.mako` (implementación).
