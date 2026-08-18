---
id: backend-domain-services-03
package: backend
plan: domain-services
status: pending
priority: 1
depends_on: [backend-domain-services-02]
estimate: 2h
actual:
issue:
created: 2026-08-18
updated: 2026-08-18
---

# rbac_service.authorize (capacidad+ámbito, fail-closed, roles custom)

## Description

`authorize(subject, capability, scope, resource) -> Allow | Deny(reason)`: decide por **capacidad +
ámbito**, nunca por el nombre del rol (`rbac.md §7`). A diferencia del resto de servicios de este plan
(que lanzan excepciones, `backend-domain-services-02`), `authorize` **devuelve** — un "deny" es el camino
esperado de la mitad de las llamadas, no un error (decisión de grilling). `Deny` lleva un **discriminante**
(`DenyReason.no_capability`→403, `DenyReason.out_of_scope`→404, CU-BE-03/FR-011/FR-014 — sin él, "no
revelar existencia" del recurso de otro tenant no es representable). Guión: `app/domain/services/
rbac_service.py`. Spec: FR-010/011/012/037, `rbac.md`.

## Spec

- `authorize(subject: Subject, capability: str, scope: Literal["tenant","global"], resource: Resource) ->
  Allow | Deny`: `Allow`/`Deny` son valores (no excepciones); `Deny.reason: DenyReason`.
- **Fail-closed**: `subject` sin ningún rol, o capacidades no resolubles → `Deny(no_capability)` — nunca
  abrir por defecto.
- **Nunca por nombre de rol**: la decisión mira el conjunto efectivo `(capability, scope)` de `subject`,
  no `role.name`.
- `resource.tenant_id` fuera del tenant de `subject` (y `subject` sin capacidad `scope=global`) →
  `Deny(out_of_scope)`.
- **Roles custom por tenant** (`rbac.md §4`): función de validación de invariantes al componer un rol —
  rechaza conceder ámbito `global`, rechaza conceder una capacidad que el propio componedor no posee.
- **KB global** (`rbac.md §5`, CU-BE-03 RN-3): `resource.tenant_id` puede ser `None` (recurso global, p.ej.
  KB) — en ese caso `authorize` **no** compara tenant (no aplica `out_of_scope`); solo exige la capacidad.
- Sin efectos en import; puertos por inyección de constructor (`RoleRepository`).

## Fuera de alcance

- `deps.get_tenant_context`/`get_current_subject`/`require_capability` (orquestación FastAPI) → plan 11/12.
- El mapeo `Deny.reason` → status HTTP concreto → routers (11/12); aquí solo se produce el discriminante.
- Administración de tenants/usuarios/roles (alta, CU-BE-09) → no es esta tarea.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-BE-03 — Autorización por capacidad y aislamiento tenant](../../../specs/backend/casos-de-uso/CU-BE-03-autorizacion-y-aislamiento-tenant.md)

> Nota de alcance: el CU describe el flujo completo (incl. que la operación "procede" — persistencia real,
> RLS). Esta tarea prueba **solo** `authorize()` a nivel de servicio (unit, `RoleRepository` mockeado): los
> escenarios "acción permitida/denegada/deny-all/cross-tenant/global/fail-closed" se verifican como el
> valor `Allow`/`Deny(reason)` devuelto, no como el efecto de negocio completo (eso es integración, 11/12).
> Añade también, sobre el CU: la validación de invariantes de rol custom (`rbac.md §4`) y el caso de KB
> global sin `tenant_id` (RN-3, con regla pero sin Gherkin en el CU — añadido por `scenario-coverage`),
> que el CU no Gherkin-iza explícitamente:
> ```gherkin
> Scenario: kb.read no exige coincidencia de tenant en el recurso
>   Given un sujeto con capacidad kb.read en su tenant
>   When solicita un recurso de la KB (sin tenant propio)
>   Then la autorización procede sin comprobar tenant_id de recurso
> ```

## Provides

`rbac_service.authorize` en `app.domain.services.rbac_service`, consumido por el futuro
`deps.require_capability` (plan 11/12).

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (Red → Green → Refactor).
- [ ] Cada escenario del CU enlazado tiene al menos un test a nivel de `authorize()` (permitido, sin
  capacidad→403/no_capability, deny-all, cross-tenant→404/out_of_scope, global cross-tenant, fail-closed
  si no se resuelven capacidades) + invariantes de rol custom + KB global sin `tenant_id` de recurso.
- [ ] Todos los tests en verde (`make test`).
- [ ] `Provides` disponible; el dominio no importa `app.infra`.
- [ ] `ruff check` (+`S`) + `ruff format --check` + `mypy` strict OK.
- [ ] Gate de mutation `cosmic-ray` (`break: 80`) sobre `rbac_service.py`.
- [ ] Gate `/sdd-lint` sin ERROR (CU-BE-03 Gherkin bien formado, enlace válido).
- [ ] Gate de `fact-checker`.
- [ ] Documentación: docstrings (contrato, fail-closed, invariantes de rol); session log con la traza a
  CU-BE-03.
