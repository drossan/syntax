---
id: backend-agent-graph-07
package: backend
plan: agent-graph
status: pending
priority: 1
depends_on: [backend-agent-graph-01]
estimate: 4h
actual:
created: 2026-08-27
updated: 2026-08-27
---

# `app/agents/checkpointer.py` — `PostgresSaver`, migración Alembic, pool singleton

## Description

Implementa el guión de `app/agents/checkpointer.py` (ADR-0007): el checkpointer Postgres que hace
durable el ciclo HITL. Tres piezas nuevas, decididas en `grilling`/`design-review`: (1) una migración
Alembic (DSN superuser) que crea las 4 tablas internas de `langgraph-checkpoint-postgres` y otorga a
`syntax_app` solo SELECT/INSERT/UPDATE (sin CREATE, least-privilege); (2) un allowlist explícito en el
gate de drift existente para que esas tablas no lo rompan; (3) un pool psycopg singleton perezoso, mismo
patrón que `app/infra/db/session.py`.

## Spec

- **Migración Alembic** (`alembic/versions/0005_agent_checkpoint_tables.py` o siguiente número libre):
  ejecuta el DDL de `AsyncPostgresSaver.setup()` (las 4 tablas: `checkpoint_migrations`, `checkpoints`,
  `checkpoint_blobs`, `checkpoint_writes` — verificar el DDL exacto contra
  `langgraph.checkpoint.postgres.base` de la versión instalada, NO copiarlo de memoria) + `GRANT SELECT,
  INSERT, UPDATE ON <tablas> TO syntax_app` (sin `DELETE` ni `CREATE` — verificado en `design-review`
  que el adaptador solo hace `INSERT ... ON CONFLICT`, nunca `DELETE`).
  - **Nota de riesgo** (obligatoria en el docstring de la migración, `design-review` ajuste 10): el DDL
    de `langgraph-checkpoint-postgres` es un detalle interno **no-público** de la librería (strings
    Python crudos, no API estable). En cualquier bump de esa dependencia, **re-verificar a mano** que
    el array `MIGRATIONS` interno no cambió antes de asumir que esta migración sigue siendo correcta.
- **Allowlist en el gate de drift** (`tests/test_migration.py::test_models_do_not_drift_from_schema`):
  excluir del diff estructural las tablas cuyo nombre empiece por `checkpoint` (o el prefijo real que
  use la librería), con un comentario que remita a esta tarea y explique que las gestiona
  `langgraph-checkpoint-postgres`, no el ORM de este proyecto — NO declarar un `Table()` sin ORM
  paralelo (duplicaría el DDL interno en un segundo sitio a mantener sincronizado).
- **`app/agents/checkpointer.py`**:
  - `_checkpointer_dsn(database_url: str) -> str`: traduce `postgresql+asyncpg://...` a
    `postgresql://...` (psycopg no entiende el driver `+asyncpg`). Función pura, testeable sin Postgres.
  - `get_checkpointer_pool() -> AsyncConnectionPool` — singleton perezoso por proceso (mismo patrón que
    `get_engine()`/`get_sessionmaker()` de `session.py`; sin efectos en import).
  - `get_checkpointer() -> AsyncPostgresSaver` — construido sobre el pool anterior.
- Tests de integración (Postgres real en Docker): el pool conecta, `AsyncPostgresSaver.aput`/`aget`
  hacen roundtrip de un checkpoint sobre las tablas creadas por la migración.

## Fuera de alcance

—

## Scenarios (Gherkin)

```gherkin
Feature: Checkpointer Postgres del grafo

  Scenario: la migración crea las tablas de checkpoint sin romper el gate de drift
    Given la migración 0005 aplicada sobre una base de datos limpia
    When corre el test de drift ORM↔BD
    Then no reporta las tablas de checkpoint como drift

  Scenario: syntax_app puede leer y escribir checkpoints pero no puede borrarlos ni crear tablas
    Given las tablas de checkpoint creadas y los grants aplicados
    When syntax_app intenta INSERT/UPDATE/SELECT sobre ellas
    Then las operaciones tienen éxito
    And un intento de DELETE o CREATE TABLE adicional falla por permisos

  Scenario: el DSN se traduce al dialecto que psycopg entiende
    Given settings.database_url con el driver +asyncpg
    When se deriva el DSN del checkpointer
    Then el resultado no contiene "+asyncpg" y psycopg lo acepta

  Scenario: un checkpoint persistido se recupera íntegro
    Given un AsyncPostgresSaver conectado a Postgres real
    When se guarda un checkpoint y se recupera por su thread_id
    Then el estado recuperado es idéntico al guardado

  Scenario: el pool del checkpointer es un singleton por proceso
    Given dos llamadas sucesivas a get_checkpointer_pool()
    When se comparan las instancias devueltas
    Then son el mismo objeto (no se abre una segunda conexión)

  Scenario: dos threads distintos no mezclan sus checkpoints
    Given checkpoints guardados para thread_id="a" y thread_id="b"
    When se recupera el checkpoint de thread_id="a"
    Then no contiene datos del checkpoint de thread_id="b"

  Scenario: Postgres inalcanzable falla con un error claro
    Given un DSN de checkpointer que apunta a un Postgres inalcanzable
    When se construye el pool y se intenta una operación
    Then el fallo es un error controlado y explicable, no una excepción críptica del driver
```

## Provides

- `get_checkpointer()` — lo consume `runner.py` (tarea 08) para compilar el grafo (tarea 06) con
  persistencia real.
- Migración `0005_agent_checkpoint_tables` — deja las tablas listas en cualquier entorno que corra
  `alembic upgrade head`.

## Definition of Done
- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida; lo declarado en `Provides` queda realmente disponible para las tareas dependientes
- [ ] Lint / format / typecheck OK
- [ ] Gate de mutation testing superado (`cosmic-ray`, `break: 80`)
- [ ] Gate `sdd-lint` superado (ERROR bloquea, AVISO se reconoce)
- [ ] Gate de `fact-checker` superado (INCORRECTO bloquea; NO VERIFICABLE = aviso a reconocer)
- [ ] **SDD** — enlaza ADR-0007 (checkpointer); sin CU propio (infra pura)
- [ ] Documentación actualizada — tres capas:
  - [ ] TSDoc en el código (`get_checkpointer_pool`, `get_checkpointer`, `_checkpointer_dsn`, docstring
    de la migración con la nota de riesgo del DDL vendido)
  - [ ] Doc técnica — ADR-0007 gana una nota de "Consecuencias" sobre el riesgo del DDL no-público
  - [ ] Histórico de la tarea — session log en `.claude/context/backend/backend-agent-graph-07.md`
- [ ] Docs de dev / usuario final — no aplica
