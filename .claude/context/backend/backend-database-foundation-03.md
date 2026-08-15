# Session log — backend-database-foundation-03

Tarea: 8 modelos ORM de identidad/RBAC + enums nativos. Nivel: **unit** (metadata).
Mutation: **N/A** (declarativo). Ficheros: `app/infra/db/models/{enums,identity}.py` + `__init__.py`.

## Resumen

- `enums.py`: 6 enums Python (`TenantStatus`, `UserStatus`, `CapabilityScope`, `RoleKind`,
  `RefreshSessionStatus`, `AuthTokenKind`) + helper `pg_enum(cls, name)` (enum nativo PG con
  etiquetas = VALUES vía `values_callable`).
- `identity.py`: `Tenant`, `User`, `Capability`, `Role`, `RoleCapability`, `UserRole`,
  `RefreshSession`, `AuthToken`. PKs UUID (`default=uuid.uuid4`); FKs/cascadas de §7; unicidades §9.
- `__init__.py`: re-exporta los 8 modelos (import registra en `Base.metadata`).

## Decisión de interpretación (tensión en los escenarios)

El escenario "ninguna tabla de identidad tiene `tenant_id`" **choca** con `data-model.md §4.1/§9`
(fuente de verdad), que exige `user.tenant_id` + único `(tenant_id, email)` y `role.tenant_id` +
único `(tenant_id, name)` (esto último confirmado por el escenario de unicidades de scenario-coverage).
**Resuelto a favor de la spec**: `user`/`role`/`user_role` llevan columna `tenant_id` normal, pero
**ninguna hereda `TenantMixin`** → el test asserta la ausencia del **marcador RLS** (`TenantMixin`),
que es lo que significa "no son tablas de negocio con RLS". Avisado al owner en una frase.

## Decisiones técnicas + porqué

- **`pg_enum` con `values_callable`**: fuerza que las etiquetas del tipo enum PG sean los valores
  del contrato (`"global"`), no los nombres de miembro Python (`global_`, por la palabra reservada).
- **`# noqa: S105`** en `AuthTokenKind.password_reset`: ruff-bandit lo marca como "posible password
  hardcodeada"; es una etiqueta de enum, no un secreto → suprimido con motivo.
- **`RefreshSession`/`AuthToken` sin `TimestampMixin`**: solo tienen `created_at` (no `updated_at`),
  con `last_used_at`/`used_at` nullable propios (§4.1).
- **`user_role.tenant_id` nullable**: ámbito de asignación; NULL para asignaciones de rol `system`.
- Aislamiento de test: reusa `Base.metadata` real (los modelos DEBEN registrarse ahí para el drift
  de 06); el test de tablas usa `>= _IDENTITY_TABLES` (subset) para no romperse cuando 04/05 añadan más.

## Tests corridos + resultado

- TDD: 21 tests RED (ImportError) → GREEN. `tests/test_models_identity.py`: 8 tablas registradas, sin
  TenantMixin, PK compuesta de uniones, enums de conjunto exacto (6), FK tenant RESTRICT, unicidades (5),
  parent_id self-FK nullable, CASCADE user→refresh/auth, valores string de enums, PK UUID.
- Suite completa `pytest -q` verde (118 tests). `ruff check` OK (tras `# noqa` + `--fix` de SIM300) ·
  `ruff format --check` OK · `mypy app` strict Success (81 files).
- Mutation: **N/A** (declarativo, M4). `/sdd-lint`: sin cambios SDD (infra) → PASA.
- `fact-checker` (sonnet): **12/12 VERIFICADO, 0 INCORRECTO**. Matiz reconocido: la unicidad se declara
  con dos mecanismos (`__table_args__` explícito en User/Role vs `unique=True` de columna en el resto),
  pero el resultado en metadata (objetos `UniqueConstraint`) es idéntico. Gate limpio.

## Docs actualizadas

- Docstrings de módulo/clase/enum en `enums.py` e `identity.py`; `__init__.py` con el mapa de grupos RLS.
- Session log (este fichero).
