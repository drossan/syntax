# Referencia · RBAC (autorización)

**Fuente canónica:** `.claude/specs/backend/rbac.md`. Modelo: **rol → capacidad → ámbito**.

## Conceptos

- **Capacidad**: permiso accionable atómico (p.ej. `ticket.reply`). Es la unidad que un rol concede.
- **Ámbito (scope)**: `tenant` (un cliente/dominio) o `global` (cross-tenant, solo Syntax/Soporte).
- **Rol**: conjunto de capacidades. **De sistema** (semilla, inmutable) o **custom por tenant**.
- **Tenant**: cliente = dominio. Soporte vive en el tenant-sistema `syntax`.

## Roles semilla

**Soporte (ámbito `global`)**: `support_admin`, `support_agent`, `support_viewer`.
**Cliente (ámbito `tenant`)**: `client_admin`, `client_agent`, `client_viewer`.

## Reglas clave

- **`authorize(subject, capability, scope, resource)`** decide por **capacidad + ámbito**, **nunca por el
  nombre del rol**.
- **Capacidades resueltas server-side por request** desde BD (no desde el JWT): un cambio/revocación de rol
  surte efecto en la siguiente request.
- **Fail-closed**: sujeto sin rol → **deny-all**; si no se pueden resolver capacidades → denegar todo.
- **Roles custom por tenant**: se componen del catálogo con invariantes — no conceder ámbito `global`, no
  conceder lo que el propio sujeto no posee, tenant-scoped; roles `system` inmutables.
- **Deny → HTTP 403** con el envelope estándar. En el frontend el RBAC es UX/defensa en profundidad; la
  **API es la fuente de verdad**.

## Visibilidad de mensajes (Fase 1)

`public` (cliente + Syntax) · `internal` (solo Syntax, requiere `note.internal.read`). Sin `developer`
(Fase 2 diferida).
