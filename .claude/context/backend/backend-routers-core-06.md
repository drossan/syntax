# Session log — backend-routers-core-06

Tarea: routers `admin_tenants` (+`/admin/settings`), `admin_users`, `admin_roles`
(+`/admin/capabilities`) sobre los adaptadores de identidad (04) y `deps`/RBAC (05), con auditoría
(`AuditLogRepository`) en toda mutación. Depends_on: 05 (`done`).

## Entradas

- 2026-08-19 — Arranque. Movida de `.claude/tasks/pending/backend/` a `active/`, `status: pending`→
  `status: active`, antes de empezar (mismo lapso que la tarea 05, corregido igual).

## Resumen

Los 3 routers eran esqueleto doc-only (solo docstring "GUIÓN") — código real completo en esta tarea.
Antes de escribirlos, hubo que cerrar **3 huecos de puerto/entidad** que el propio `## Spec` de la
tarea exige pero que no existían todavía (extensiones de `domain-services`/`database-foundation`
"que los routers necesitan de verdad", autorizadas por el plan):

1. **`AuditLogEntry` sin `tenant_id`**: la tabla `audit_log` es de NEGOCIO con RLS (`TenantMixin`,
   columna `NOT NULL`), pero la entidad de dominio (cerrada en `domain-services`, solo probada con
   fakes) nunca lo llevaba — un `AuditLogRepository` real no podía persistir una fila sin él. Añadido
   `tenant_id: uuid.UUID` (obligatorio) a `AuditLogEntry`; `ticket_service._audit` ahora pasa
   `tenant_id=ticket.tenant_id`; actualizado el único test que construía la entidad a mano
   (`test_domain_entities.py`).
2. **`RoleRepository` sin asignación `user_role` ni catálogo de capacidades completo**: solo existían
   `list_capabilities(role_id)` (capacidades de UN rol) y `effective_capabilities` (resolución RBAC).
   Añadidos `list_all_capabilities()` (catálogo completo, `GET /admin/capabilities`), `assign`/
   `unassign_all`/`list_assigned` (gestionar `roles[]` de `admin_users`) y `set_capabilities` (fijar
   las capabilities de un rol custom, `admin_roles`).
3. **`SqlAlchemyAuditLogRepository` no existía**: el puerto se declaró en `domain-services` pero
   ningún adaptador real lo implementaba (solo fakes). Nuevo `app/infra/db/repositories/audit_log.py`.

## Decisiones técnicas + porqué

- **`assign` es upsert (`ON CONFLICT DO UPDATE`), no insert puro**: el PK real de `user_role` es
  `(user_id, role_id)` — `admin_users` reemplaza `roles[]` completo en cada `PATCH`
  (`unassign_all` + `assign` de la lista nueva), así que reasignar el mismo par es el caso normal, no
  un error de unicidad.
- **`RoleCreate.capabilities` del contrato son solo nombres, sin `scope` propio**: el router resuelve
  el `scope` de cada nombre desde el CATÁLOGO (`Capability.scope`, el ámbito MÁXIMO permitido para esa
  capacidad) antes de llamar a `rbac_service.validate_role_composition` — el cliente nunca elige el
  ámbito, lo declara el catálogo.
- **Orden de checks en `_get_editable_role` (admin_roles)**: primero `role is None` (404), LUEGO
  `role.kind is system` (409), y solo DESPUÉS `role.tenant_id != subject.tenant_id` (404). Los roles
  `system` son visibles a cualquier tenant vía `GET /admin/roles` (semilla global) — comprobar el
  tenant ANTES habría dado 404 para un rol que el cliente sabe que existe (su `tenant_id` es `None`,
  que nunca coincide con `subject.tenant_id`), en vez del 409 correcto. Encontrado por el primer test
  de "editar un rol system" fallando con 404 en vez de 409 — reordenado, no fue obvio a la primera.
- **`{id}` de `PATCH /admin/users/{id}` es el `User.id` GLOBAL**: el router cruza con
  `subject.tenant_id` para localizar la `UserTenantMembership`; sin membership en ese tenant → 404
  (nunca revela que el `User` existe en otro tenant — mismo patrón de aislamiento que CU-BE-03).
- **`/admin/settings` decide el tenant por el ÁMBITO CONCEDIDO de `tenant.settings.manage`**, no por
  un flag del router: ámbito `tenant` usa `subject.tenant_id` (query param `tenant_id` ignorado);
  ámbito `global` (Soporte) exige `tenant_id` (422 si falta) — sin él no hay forma de saber a qué
  tenant se refiere. `api-contract.yaml` no documentaba este query param (decisión 18 de
  `scenario-coverage`, nunca reflejada en el contrato) — añadido en esta tarea.
- **Código muerto evitado, no introducido**: `admin_users`/`admin_tenants` usan
  `cast(UserEntity, ...)` (no `assert`) para narrowing de tipo tras invariantes de FK garantizadas
  (p.ej. toda `UserTenantMembership` referencia un `User` real) — mismo patrón que el `cast` de
  `switch_tenant` en la tarea 05, evita el `S101` de bandit y no añade superficie de mutación falsa.
- **Hallazgo de `/sdd-lint` corregido en esta sesión**: el `## Scenarios` de la tarea cubría el
  rechazo de un rol custom por ámbito `global`, pero NO el rechazo por "no-escalada" (el componedor no
  posee la capacidad, aunque sea de ámbito `tenant`) — un criterio de aceptación explícito de
  CU-BE-09 ligado a FR-037, y un invariante distinto que `rbac_service.validate_role_composition` ya
  implementaba y que SÍ tenía cobertura unit (`test_rbac_service.py`, plan anterior) pero NO
  integración a través del router. Añadido el escenario Gherkin + el test de integración
  correspondiente.

## Tests corridos + resultado

- `tests/test_repositories_admin.py` (nuevo, **15 tests**): `SqlAlchemyAuditLogRepository.add`
  (persistencia, con/sin `actor_id`), `list_all_capabilities` (catálogo completo pese al rol),
  `set_capabilities` (concede/reemplaza/revoca), `assign`/`unassign_all`/`list_assigned` — incl. 5
  tests con UUIDs deterministas (`UUID(int=N)`, objetivo ENTRE otros dos) para matar mutantes de
  comparación (`==`→`<=`/`>=`) en los filtros de `tenant_id`/`user_id`/`role_id` y en la condición del
  JOIN de `list_assigned`.
- `tests/test_router_admin.py` (nuevo, **29 tests**): los 18 escenarios Gherkin de la tarea (incl. el
  añadido de no-escalada) + refuerzos de paginación (`page`/`page_size` en sus límites exactos,
  default `page_size=20`) y del status desconocido en `PATCH /admin/users/{id}`, necesarios para
  matar los mutantes de `Query(..., ge=..., le=...)` y del `except ValueError`.
- Suite completa del backend (`pytest -q`): **514 tests, verde**, sin regresiones (incl. los 470 de
  antes de esta tarea + el ajuste de `test_domain_entities.py` por el `tenant_id` nuevo).
- `ruff check .`/`ruff format --check .`: OK (el único drift, `docs/domain-services-explicado.md`,
  preexistente, no tocado). `mypy app` (strict): `Success: no issues found in 107 source files`.
- Mutation (`cosmic-ray`, `--fail-over 20`), un fichero a la vez:
  - `admin_tenants.py`: **12.50%** survival → PASA.
  - `admin_users.py`: primera pasada **30.56%** (11 survivors: bounds de `Query`, `except ValueError`
    sin ejercitar, `for role_id in payload.roles` con lista vacía en ambos endpoints) → refuerzos →
    **2.78%** → PASA (único survivor: un mutante `*`→`/` sobre el separador keyword-only de
    `_to_schema`, EQUIVALENTE — la función solo se llama con kwargs, el separador no cambia
    comportamiento observable).
  - `admin_roles.py`: primera pasada **50.00%** (15 survivors: rol de OTRO tenant nunca probado,
    capacidad desconocida nunca probada, `DELETE`/`GET /roles` sin ningún test) → refuerzos (incl. el
    escenario de no-escalada del hallazgo de `/sdd-lint`) → **6.67%** → PASA.
  - **Extra, más allá de la DoD** (el fichero tiene lógica nueva no trivial): `role.py` (métodos
    nuevos), primera pasada **17.33%**, refuerzos con UUIDs deterministas → **10.67%** → PASA;
    `audit_log.py` (adaptador nuevo) **100%** survival, pero el único mutante posible en todo el
    fichero es el `except Exception` habitual (requiere inyección contrivada de fallo de infra,
    mismo patrón aceptado en todos los adaptadores desde la tarea 04) — documentado, no bloquea (no
    forma parte de la DoD de esta tarea, que solo exige los 3 routers).
- `/sdd-lint`: mecánico limpio. Semántico vía subagente fresco: **1 ERROR** (faltaba el escenario de
  "no escalar privilegios" en el `## Scenarios` de la tarea, criterio de aceptación de CU-BE-09 ligado
  a FR-037) — **corregido** (escenario + test añadidos, re-verificado en verde). **4 AVISO
  reconocidos, no bloqueantes**: (a) el alta de tenant (escenario principal de CU-BE-09) no tiene FR
  propio en `spec.md`; (b) la tarea no incluye un escenario dedicado de "alta de tenant" (solo listado
  y 403); (c) la extensión 3c del CU (asignar un rol custom a un usuario de OTRO tenant) no tiene
  escenario dedicado en la tarea; (d) los 5 escenarios de `/admin/settings`/`auto_approve` de la tarea
  no están reflejados como criterios de aceptación en el propio CU-BE-09 (documentados en la
  `## Description` de la tarea, pero el CU no se actualizó). Ninguno es una contradicción — son huecos
  de sincronización spec↔tarea, quedan como seguimiento nombrado.
- `fact-checker`: pendiente de lanzar tras este session log.

## Docs actualizadas

- `.claude/specs/general/api-contract.yaml`: `tenant_id` query param (opcional) en `GET`/
  `PATCH /admin/settings` — decisión 18 de `scenario-coverage` que nunca se había sincronizado al
  contrato.
- `.claude/tasks/active/backend/backend-routers-core-06.md`: añadido el escenario Gherkin de
  no-escalada (hallazgo de `/sdd-lint`, ver arriba).
- Docstrings de `app/domain/entities/business.py` (`AuditLogEntry.tenant_id`, por qué es obligatorio),
  `app/domain/ports/repositories.py` (los 5 métodos nuevos de `RoleRepository`), `app/infra/db/
  repositories/role.py`/`audit_log.py` (adaptadores), `app/api/v1/routers/admin_roles.py`
  (`_get_editable_role`, el orden de checks y por qué). Este session log.

## Ficheros / commits

- `backend/app/api/v1/routers/{admin_tenants,admin_users,admin_roles}.py` (de esqueleto a código
  real), `backend/app/api/v1/schemas/admin.py` (nuevo), `backend/app/infra/db/repositories/
  audit_log.py` (nuevo).
- `backend/app/domain/entities/business.py` (`AuditLogEntry.tenant_id`), `backend/app/domain/ports/
  repositories.py` (`RoleRepository` +5 métodos), `backend/app/domain/services/ticket_service.py`
  (`_audit` pasa `tenant_id`), `backend/app/infra/db/repositories/role.py` (+5 métodos),
  `backend/app/infra/db/repositories/__init__.py` (exporta `SqlAlchemyAuditLogRepository`),
  `backend/app/main.py` (monta los 3 routers admin).
- `backend/tests/test_repositories_admin.py` (nuevo), `backend/tests/test_router_admin.py` (nuevo),
  `backend/tests/test_domain_entities.py` (ajuste `tenant_id`).
- `backend/cosmic-ray.toml` (apunta a `app/api/v1/routers/admin_roles.py`, último módulo mutado).
- `.claude/specs/general/api-contract.yaml` (query param `tenant_id`).
- Commit: uno solo, `backend-routers-core-06: feat(backend): routers admin_tenants/admin_users/admin_roles + auditoría`.

## Tiempo real

- `estimate: 4h` → real: sesión propia, ampliada por los 3 huecos de puerto/entidad (ninguno
  hipotético — el propio `## Spec` de la tarea los exige) y por 2-3 rondas de mutation gate por
  router (patrón ya esperado: cada router es la primera vez que su lógica se ejercita de punta a
  punta contra Postgres real).

## Follow-ups

- Los 4 AVISO de `/sdd-lint` (arriba) quedan como seguimiento nombrado de sincronización spec↔tarea,
  no bloquean este cierre.
- `docs/domain-services-explicado.md` sigue con el drift preexistente de sesiones anteriores,
  intencionalmente sin tocar (fuera de alcance).
