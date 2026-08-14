---
id: backend-skeleton-foundation-02
package: backend
plan: skeleton-foundation
status: done
priority: 1
depends_on: []
estimate: 2h
actual: 0.5h
issue:
created: 2026-08-11
updated: 2026-08-11
---

# Spec RBAC (capacidades + ámbito, roles custom por tenant)

## Description

Escribir `.claude/specs/backend/rbac.md`: el modelo de autorización. **rol → capacidad → ámbito**
(patrón del propio Syntax), con **roles custom por tenant** (decisión del owner, mantenida en
design-review). Fija el catálogo de capacidades, los roles semilla, el aislamiento multi-tenant y la
visibilidad de mensajes. Es la fuente de la que beben data-model (03) y api-contract (06).

## Spec

- **Capacidades**: catálogo de permisos accionables (p.ej. `ticket.read/create/reply/assign/transition`,
  `approval.decide`, `tenant.manage`, `user.manage`, `role.manage`, `kb.read`, `note.internal.read`).
- **Ámbito (scope)**: `tenant` | `global`. Soporte de Syntax actúa en `global` (cross-tenant); cliente en su `tenant`.
- **Roles semilla (sistema)**: soporte `support_admin`/`support_agent`/`support_viewer` (global);
  cliente `client_admin`/`client_agent`/`client_viewer` (tenant). Mapa rol→capacidades documentado.
- **Roles custom por tenant**: un `client_admin` compone roles a partir del catálogo de capacidades
  (role builder). Reglas: no puede conceder capacidades de ámbito `global`; no puede exceder su propio ámbito.
- **Aislamiento**: app-level (repos filtran por `tenant_id`) **+ RLS** (ver 03/08). Soporte con capacidad
  cross-tenant. Tenant-sistema `syntax` para Soporte.
- **Visibilidad de mensajes (Fase 1)**: `public` (cliente+Syntax) | `internal` (solo Syntax). Sin `developer` (Fase 2).
- **Comprobación**: `authorize(subject, capability, scope, resource)` — decide por capacidad+ámbito, no por nombre de rol.
- Matriz rol×capacidad + anti-patrones (nunca confiar en el nombre del rol; nunca ampliar por defecto).

## Refuerzos (scenario-coverage)

- Sujeto **sin ningún rol** → `authorize` **deny-all** explícito (no comportamiento implícito).
- Cambio/borrado/revocación de rol **en caliente**: las capacidades se resuelven **server-side por
  request** (no desde el token); TTL corto de access acota la obsolescencia de pertenencia; documentar la
  opción de revalidar contra BD/invalidar por cambio de rol.

## Fuera de alcance

- Implementar el motor RBAC (solo la spec).
- SSO/OIDC (Fase 2): la spec deja el hueco de dónde encajará la identidad federada.
- Visibilidad `developer` / nota al desarrollador (Fase 2).

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- La spec define capacidades, ámbitos, roles semilla y el mecanismo de roles custom por tenant, sin contradicciones.
- Cada capacidad tiene ámbito y una regla de quién la concede; la matriz rol×capacidad es completa y verificable.
- Coherente con data-model (03) y api-contract (06): los nombres de capacidades/roles se reusan tal cual.

## Provides

- `.claude/specs/backend/rbac.md`: catálogo de capacidades, roles semilla, reglas de scope/tenant y
  visibilidad `public|internal`. 03 lo materializa en tablas; 06 en endpoints; el frontend en su RBAC.

## Definition of Done

- [ ] Spec creada y coherente con 03/06 (nombres de capacidades/roles idénticos).
- [ ] Matriz rol×capacidad + reglas de ámbito + roles custom + visibilidad documentadas y verificables por bullets.
- [ ] Lo declarado en `Provides` disponible para las dependientes.
- [ ] Gate de `fact-checker` superado.
- [ ] Histórico en `.claude/context/backend/backend-skeleton-foundation-02.md`.
