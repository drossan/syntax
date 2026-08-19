# Session log — backend-routers-core-04

Tarea: adaptadores SQLAlchemy de identidad (`Tenant`/`User`/`UserTenantMembership`/`Role`/
`RefreshSession`/`AuthToken`), primeros adaptadores REALES contra Postgres de los puertos de
`domain-services`. Nivel: integración (Postgres real, primera vez que se ejercita el CAS de
`rotate_if_active` con DB de verdad, no un fake).

## Entradas

- 2026-08-19 — Arranque. Tarea 04 `active`. Depends_on 01+03 (ambas `done`).

## Resumen

`app/infra/db/repositories/{tenant,user,user_tenant,role,refresh_session,auth_token}.py`: seis
adaptadores nuevos, exportados desde `app/infra/db/repositories/__init__.py`. Ninguno usa
`BaseRepository` (no aplica: identidad es cross-tenant por diseño, sin `TenantMixin`/RLS). Todos
envuelven cualquier excepción (`except Exception`, no solo `SQLAlchemyError` — ver decisión abajo)
en `PortError`. `rotate_if_active` es el único CAS real: una sentencia `UPDATE ... WHERE
token_hash=... AND status='active' ... RETURNING`, con un `SELECT` de diagnóstico SOLO si el UPDATE
no afectó filas (para distinguir `Reused` de `NotFound`, fuera de la ventana de carrera). Amplía el
puerto (`app/domain/ports/repositories.py`): `PageResult[T]` genérico nuevo;
`UserTenantMembershipRepository.list_by_user`/`list_by_tenant` (paginado); `RoleRepository.list`/
`update`/`delete` + `effective_capabilities(user_id, tenant_id)` (antes solo `user_id`);
`TenantRepository.update`/`list` (paginado).

## Decisiones técnicas + porqué

- **Renombrado `UserTenantMembershipRepository.list_for_user` → `list_by_user`** (ya existía desde
  la tarea 02/fusión con 01, con nombre distinto al que esta tarea especifica) — se propagó el
  rename a `auth_service.py`/`test_auth_service.py`. La tarea 02 había creado una versión mínima del
  puerto por necesidad (sin `list_by_tenant`, sin paginación); esta tarea la amplía con el nombre y
  la forma que el plan siempre tuvo previstos para ella.
- **Puente de enums (`_enum_bridge.py`, nuevo) — bug real descubierto por `mypy`, no solo un tipo
  cosmético.** Los enums de dominio (`app.domain.entities.enums`) y los del ORM
  (`app.infra.db.models.enums`) son clases `enum.Enum` DISTINTAS a propósito (NFR-003, el dominio no
  importa el ORM). Como no son `str`-mixin, un miembro de una clase no es igual, ni construible por
  valor, a un miembro de la otra aunque compartan `.value` — asignar directamente un enum de dominio
  a una columna ORM (o viceversa al leer) produce un `ValueError` en tiempo de ejecución (confirmado
  con tests reales, no solo hipótesis: el primer borrador de `tenant.py`/`user_tenant.py` fallaba a
  la escritura, `mypy` ya lo había marcado como error de tipos). Fix: `to_orm`/`to_domain` en
  `_enum_bridge.py`, conversión por `.value` en ambas direcciones, usadas en los 5 adaptadores que
  tocan un campo enum.
- **Bug de scoping de Python descubierto en `app/domain/ports/repositories.py`**: nombrar un método
  `list` dentro de un `Protocol` vincula ese nombre en el namespace del CUERPO de la clase — sombrea
  el builtin `list` para cualquier anotación `list[...]` que aparezca DESPUÉS en el mismo cuerpo
  (`TypeError: 'function' object is not subscriptable` al importar). Afectó a `RoleRepository`
  (`list` declarado antes de `list_capabilities`); solucionado declarando `list` al FINAL de la
  clase, con el porqué documentado en su propio docstring para que no se reintroduzca.
- **`except Exception` en vez de `except SQLAlchemyError`, en los 6 adaptadores.** El Gherkin de la
  tarea pide explícitamente que "un fallo de infra real (p.ej. conexión caída)" llegue como
  `PortError` — probado con un engine apuntando a un puerto inalcanzable, el fallo de conexión de
  `asyncpg`/`asyncio` llega como `OSError` crudo ANTES de que SQLAlchemy lo traduzca a
  `SQLAlchemyError` (ocurre en el `connect()` del pool, no en la ejecución de una sentencia ya
  conectada). Capturar solo `SQLAlchemyError` habría dejado pasar exactamente el caso que el propio
  escenario pide cubrir.
- **`await self._session.refresh(row)` tras `flush()` en `tenant.py`/`user.py` `update()` — bug real
  encontrado por el primer test que ejercitó el camino completo.** `updated_at` (`onupdate=func.now()`,
  `TimestampMixin`) no se repuebla automáticamente en el objeto Python tras un `UPDATE` (a diferencia
  de un `INSERT`, que sí usa `RETURNING` implícito); acceder a `row.updated_at` justo después de
  `flush()` sin refrescar dispara un intento de lazy-load SÍNCRONO sobre una `AsyncSession`
  (`MissingGreenlet`). `UserTenant`/`Role`/`AuthToken` no lo necesitan: sus entidades de dominio no
  exponen (o no tienen) un campo `updated_at` generado por `onupdate`.
- **`effective_capabilities`: incluye asignaciones `user_role.tenant_id IS NULL`** (ámbito global,
  Soporte) además de las del tenant exacto — decisión de diseño, no solo lo literal del Gherkin (que
  solo prueba el caso tenant-vs-tenant): un rol asignado en ámbito global debe aplicar en cualquier
  sesión, no solo cuando `tenant_id` coincide.
- **`RoleRepository.update` solo persiste `name`/`description`** — `kind`/`tenant_id` son de
  identidad y no se reasignan. El Gherkin menciona "descripción O sus capacidades" pero el `## Spec`
  de la tarea no añade un método de gestión de asociaciones `role_capability`; se interpretó como
  ampliación narrativa, no un método nuevo fuera del `## Spec` explícito (decisión de alcance, no
  fallo de cobertura).
- **UUIDs deterministas (`uuid.UUID(int=N)`) en varios tests** para que el objetivo de la
  comparación quede ENTRE otros dos valores — mismo patrón ya usado en `domain-services`: con UUIDs
  aleatorios, una mutación de operador (`==`→`<=`/`>=`/`!=`) sobrevive porque el resultado da igual
  con valores no ordenados a propósito.

## Tests corridos + resultado

- `tests/test_repositories_identity.py` (nuevo): **24 tests**, cubre los 13 escenarios Gherkin de la
  tarea + refuerzos de mutación (revoke/revoke_family/revoke_by_hash antes sin cubrir,
  list_capabilities antes sin cubrir, delete sobre id inexistente, ambas direcciones de
  comparación con UUIDs deterministas donde aplica).
- Ficheros existentes actualizados por el rename/ampliación del puerto: `tests/test_auth_service.py`
  (`list_for_user`→`list_by_user`), `tests/test_domain_errors_and_ports.py` (`_FakeTenantRepository`
  ampliado con `update`/`list` para seguir satisfaciendo `TenantRepository` estructuralmente).
- Suite completa del backend (`pytest -q`): **verde**, sin regresiones.
- `ruff check .` / `ruff format --check .`: OK (salvo el drift pre-existente no relacionado de
  `docs/domain-services-explicado.md`). `mypy app` (strict): sin issues.
- Mutation (`cosmic-ray`, uno detrás de otro, `test-command`: `test_repositories_identity.py`):
  - `refresh_session.py`: primera pasada 62.26% survival (33 survivors, `revoke*` sin tests propios)
    → tras añadir tests de `revoke`/`revoke_family`/`revoke_by_hash`/duplicado de `token_hash` →
    18.87% → tras UUIDs deterministas bidireccionales en `revoke`/`revoke_family` → **15.09%
    survival (84.9% score)**. 8 supervivientes aceptados: 6 handlers `except Exception` (requieren
    inyectar un fallo de infra real DENTRO de una transacción ya abierta sin romper el resto del
    test — desproporcionado); 1 mutante EQUIVALENTE genuino (`status <= active` en el CAS: `active`
    es el primer valor declarado del enum nativo, así que `<=` y `==` son indistinguibles para
    cualquier fila real); 1 mutante de orden sobre `token_hash` (SHA-256, no controlable
    deterministamente sin buscar preimágenes).
  - `role.py`: primera pasada 39.47% survival (30 survivors: `list_capabilities` sin test propio,
    `delete` sobre id inexistente sin cubrir, filtros `tenant_id`/`user_id`/`role_id` sin un segundo
    valor que los discrimine) → tras añadir esos tests + UUIDs deterministas → **13.16% survival
    (86.8% score)**. 10 supervivientes aceptados: 8 handlers `except Exception` (mismo criterio) + 2
    mutantes de comparación (`user_id >=`, join `role_id >=`) que necesitarían un tercer usuario/rol
    con id mayor Y menor simultáneamente para las dos comparaciones anidadas — coste desproporcionado
    frente al margen ya obtenido sobre el umbral (86.8% vs 80%).
  - Ambos muy por encima del umbral `break: 80` del Makefile.
- `/sdd-lint`: N/A (declarado en la tarea — sin cambios de spec/CU, son adaptadores de un contrato ya
  especificado en `domain-services`).
- `fact-checker`: ver informe en la respuesta al usuario de esta sesión.

## Docs actualizadas

- Docstrings de los 6 adaptadores (por qué no usan `BaseRepository`, el CAS de `rotate_if_active`
  como sentencia única, por qué `except Exception` y no solo `SQLAlchemyError`).
- Docstring de `_enum_bridge.py` (el porqué del puente, con referencia al test de drift de valores).
- Docstring de `RoleRepository.list` explicando el footgun de scoping de Python (método `list`
  sombreando el builtin dentro del cuerpo de la clase) para que no se reintroduzca.
- Este session log.

## Ficheros / commits

- `backend/app/infra/db/repositories/{tenant,user,user_tenant,role,refresh_session,auth_token,
  _enum_bridge}.py` (nuevos), `backend/app/infra/db/repositories/__init__.py` (actualizado).
- `backend/app/domain/ports/repositories.py` (`PageResult`, ampliaciones de los 3 puertos).
- `backend/app/domain/services/auth_service.py` (rename `list_for_user`→`list_by_user`).
- `backend/tests/test_repositories_identity.py` (nuevo), `backend/tests/test_auth_service.py`
  (rename), `backend/tests/test_domain_errors_and_ports.py` (fake ampliado).
- `backend/cosmic-ray.toml` (apunta a `role.py`, último módulo mutado).

## Tiempo real

- `estimate: 4h` → real: sesión propia dentro del mismo tramo de trabajo continuo del plan (01+02+03
  ya cerradas antes de empezar esta). Los dos bugs reales encontrados (enums, scoping de `list`)
  añadieron tiempo no estimado pero evitaron dejarlos para la tarea 05 (que ya los habría consumido
  como adaptadores reales, no como fakes).

## Follow-ups

- Ninguno propio. `RoleRepository.update` no gestiona el conjunto de `role_capability` de un rol —
  si el role builder (tarea 06/admin_roles) necesita actualizar capacidades de un rol existente
  (no solo crearlo), hará falta un método nuevo en el puerto (fuera del `## Spec` de esta tarea).
