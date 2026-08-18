# Session log — backend-database-foundation-02

Tarea: `app/infra/db/base.py` — `Base(DeclarativeBase)` + `naming_convention` + mixins
`TimestampMixin`/`TenantMixin`. Nivel: **unit** (metadata). Mutation: **N/A** (declarativo).

## Resumen

`base.py` deja de ser doc-only. Implementado:
- `NAMING_CONVENTION` (dict con plantillas `ix`/`uq`/`ck`/`fk`/`pk`) — exportado para reutilizar en tests.
- `Base(DeclarativeBase)` con `metadata = MetaData(naming_convention=NAMING_CONVENTION)`.
- `TimestampMixin`: `created_at`/`updated_at` `DateTime(timezone=True)`, `server_default=func.now()`,
  `updated_at` con `onupdate=func.now()`, ambos NOT NULL.
- `TenantMixin`: `tenant_id: Mapped[uuid.UUID]` NOT NULL, `ForeignKey("tenant.id")`.

## Decisiones técnicas + porqué

- **`naming_convention` en la metadata** (no en cada modelo): Alembic la usa para generar nombres
  deterministas → diffs de migración estables (evita el churn de nombres autogenerados).
- **Plantilla `fk` incluye `%(table_name)s`** (tabla origen): dos tablas de negocio con `tenant_id`
  generan FKs con nombres distintos (`fk_ticket_tenant_id_tenant` ≠ `fk_message_tenant_id_tenant`) → no
  colisionan. Verificado en test.
- **Mixins como clases planas** (no heredan de `Base`): SQLAlchemy declarative recoge sus `mapped_column`;
  cada modelo elige qué mixins compone. `TenantMixin` es el marcador semántico de "tabla de negocio + RLS".
- **`Mapped[uuid.UUID]` → tipo `Uuid`** (mapeo por anotación de SQLAlchemy 2.0; nativo UUID en Postgres).
- **Aislamiento de test**: los modelos de prueba viven en un `_ProbeBase` con su propia `MetaData` (misma
  convención) para NO registrarse en `Base.metadata` real → no rompen el drift `compare_metadata` (06).

## Tests corridos + resultado

- TDD: 9 tests RED (ImportError) → GREEN. `tests/test_base.py` (9): naming_convention, TimestampMixin,
  TenantMixin, Scenario Outline de las 5 plantillas (pk/fk/uq/ix/ck vía DDL compilado a dialecto PG), no
  colisión de FK. Suite completa `pytest -q` verde (97 tests).
- `ruff check` OK · `ruff format --check` OK (tras format) · `mypy app` strict Success (79 files).
- **Mutation: N/A** — `base.py` es declarativo (sin ramas/condicionales de comportamiento); mutarlo
  produce mutantes de bajo valor (M4 del plan excluye modelos/DDL/base del gate).
- `/sdd-lint`: sin cambios SDD (infra ORM). Checks mecánicos limpios (ver log 01). PASA.
- `fact-checker` (subagente sonnet): **9/9 VERIFICADO, 0 INCORRECTO, 0 NO VERIFICABLE**. Confirmó también
  `strict = true` en `pyproject.toml:41` y la regla hexagonal (`app.domain` no importa `app.infra`, vacuo:
  esqueletos doc-only). Gate limpio.

## Docs actualizadas

- `app/infra/db/base.py`: docstrings de módulo, `Base`, mixins y `NAMING_CONVENTION` (incl. el anti-patrón
  hexagonal: el dominio no importa este módulo).
- Session log (este fichero).
