# Session log — backend-database-foundation-08

Tarea: `BaseRepository` tenant-aware (CRUD con filtro app-level por `tenant_id`). Nivel:
**integración** (Postgres real). Mutation: código de comportamiento (filtro tenant).
Ficheros: `app/infra/db/repositories/base.py` + `__init__.py`.

## Resumen

`BaseRepository[T: TenantScoped]` (genérico, sintaxis PEP 695):
- `get(id, tenant_id) -> T | None`: filtra por id **y** tenant_id (no revela filas de otro tenant).
- `list(tenant_id) -> list[T]`: solo del tenant, orden determinista por `id` (asertado).
- `add(entity) -> T`: `session.add` + `flush` (surfacea IntegrityError); commit lo hace el llamante.
- `delete(id, tenant_id) -> bool`: borra solo dentro del tenant; `RETURNING id` → True/False.
- `TenantScoped` (Protocol con `id`/`tenant_id: Mapped[UUID]`) como bound del genérico.

## Nota de alcance (design-review L5)

Es una primitiva **aceptada como especulativa**: los repos concretos que implementan los puertos de
dominio nacen en el **plan 10** y **pueden remodelar** esta base. Aquí se prueba contra el modelo ORM
real (`Ticket`), no como contrato final hacia el dominio (esa frontera la fija el plan 10).

## Decisiones técnicas + porqué

- **Filtro app-level explícito** en get/list/delete, POR ENCIMA de RLS (1ª línea; RLS es defensa en
  profundidad). Los tests usan `superuser_engine` (**RLS desactivada**) a propósito: así el único filtro
  activo es el `WHERE tenant_id` del repo → prueba que aísla por sí solo, independiente de RLS.
- **`delete` con `RETURNING id` + `scalar_one_or_none()`** en vez de `result.rowcount`: `rowcount` no está
  tipado en `Result` (mypy strict lo rechazaba) y `RETURNING` es limpio y typed.
- **PEP 695 `class BaseRepository[T: TenantScoped]`** (ruff UP046, target py312) en vez de `Generic[T]`.
- **`Protocol` para el bound**: los 7 modelos de negocio (con `TenantMixin`) satisfacen estructuralmente
  `id`/`tenant_id: Mapped[UUID]` → mypy strict verifica el acceso a columnas sin el plugin de SQLAlchemy.
- **Orden determinista por `id`**: UUID en Postgres ordena byte-wise == orden por int de Python, así que
  `sorted(uuids)` (Python) coincide con `ORDER BY id` → aserción de orden explícita y estable.

## Tests corridos + resultado

- TDD (integración): 9 tests en `tests/test_repository.py` — get propio, get ajeno→None, get inexistente
  →None, list filtrado+orden, list vacío→[], add persiste+recuperable, add PK duplicada→IntegrityError,
  delete ajeno→False (no borra), delete propio→True + 2º delete→False (idempotente-seguro).
- Suite completa `pytest -q` verde (196 tests). `ruff check` OK (tras UP046→PEP695 + orden imports) ·
  `ruff format --check` OK · `mypy app` strict Success (85 files).
- **Mutation** `cosmic-ray` sobre `repositories/base.py` (break 80): **survival 0.00%** (47 mutantes, 0
  supervivientes) — filtro tenant totalmente cubierto.
- `/sdd-lint`: sin cambios de artefactos SDD (infra de persistencia) → PASA.
- `fact-checker` (sonnet): **10/10 VERIFICADO, 0 INCORRECTO**. Confirmó el 0% de mutation leyendo el
  `session.sqlite` en disco (47 jobs, 0 supervivientes) sin re-ejecutar. Gate limpio.

## Docs actualizadas

- Docstrings de `base.py`/`__init__.py` (incl. anti-patrón "confiar solo en RLS" y la nota "especulativo,
  puede remodelarse en plan 10"). Session log (este fichero).
