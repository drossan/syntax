# 0005. RBAC por capacidad + ámbito (nunca por nombre de rol) con roles custom por tenant

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; `grilling` backend (rama 3); `design-review` **#1 mantener**.

## Contexto y planteamiento del problema

Multi-tenant con dos familias de actores (Soporte cross-tenant y Cliente por su dominio) y necesidad de
que cada tenant componga roles a medida. ¿Sobre qué se autoriza —el **nombre del rol** o una unidad más
fina— y cómo se evita la escalada de privilegios al permitir roles custom?

## Decision drivers

- Autorizar sin acoplar la lógica al nombre de un rol (frágil, no auditable).
- Permitir **roles custom por tenant** sin abrir escalada de privilegios.
- Ámbito claro: `tenant` (un cliente) vs `global` (cross-tenant, solo Syntax).

## Opciones consideradas

- **Opción 1** — Modelo **rol → capacidad → ámbito**; `authorize(subject, capability, scope, resource)`
  decide por **capacidad + ámbito**; roles de sistema inmutables + roles custom por tenant con invariantes.
- **Opción 2** — Autorización por **nombre de rol** (`if role == "admin"`).
- **Opción 3** — Solo roles de sistema fijos, sin composición por tenant.

## Resultado de la decisión

Elegida: **Opción 1**. La unidad es la **capacidad** (`ticket.reply`, `approval.decide`, …) con un
**ámbito** (`tenant|global`); `authorize(...)` decide por capacidad+ámbito, **nunca** por el nombre del
rol. Roles de **sistema** (semilla) inmutables; **roles custom por tenant** compuestos del catálogo, con
**invariantes fail-closed**: no conceder capacidades `global`, no conceder una capacidad que el
componedor no posee (no escalada), rol custom solo asignable a usuarios de su tenant. Sujeto **sin rol →
deny-all** explícito; si las capacidades no se resuelven → **fail-closed**.

### Confirmación

`rbac.md` (catálogo v1, matriz rol×capacidad, invariantes §4); `app/domain/services/rbac_service.py`
(guión `authorize` + deny-all fail-closed); consumido por `data-model.md`, `api-contract` y el RBAC de
cliente (defensa en profundidad, la API es la fuente de verdad: deny→403).

## Consecuencias

- **Buenas**: autorización auditable y fina; roles custom sin escalada; deny-all por defecto.
- **Malas / coste**: catálogo de capacidades a mantener; el nombre de la capacidad es **contrato literal**
  (frontend y `api-contract` lo referencian tal cual).

## Pros y contras de las opciones

- **Opción 1**: 👍 fino, auditable, extensible · 👎 catálogo + invariantes que mantener.
- **Opción 2**: 👍 trivial de leer · 👎 frágil, no auditable, imposible de componer sin tocar código.
- **Opción 3**: 👍 sin riesgo de escalada · 👎 rígido; los tenants no pueden adaptar permisos.
