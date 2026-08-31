# Spec — RBAC (autorización) del backend

> Fuente de verdad de autorización de Syntax. La consumen `data-model` (03, tablas),
> `api-contract` (06, endpoints) y el RBAC del frontend (capacidades/menús). Modelo:
> **rol → capacidad → ámbito** (mismo patrón que el propio Syntax, UC-API-001). Implementación en
> `app/domain/services/rbac_service.py` + dependencias de FastAPI. **Este fichero es la spec, no el código.**
>
> **SDD** — Doc de **referencia** de la capa SDD. Requisitos en [`spec.md`](./spec.md); decisiones en
> [ADR-0005](../adr/0005-rbac-por-capacidad-y-ambito.md) y
> [ADR-0006](../adr/0006-aislamiento-multi-tenant-app-level-mas-rls.md); flujos en
> [CU-BE-03](./casos-de-uso/CU-BE-03-autorizacion-y-aislamiento-tenant.md) y
> [CU-BE-09](./casos-de-uso/CU-BE-09-administracion-tenants-usuarios-roles.md).

## 1. Conceptos

- **Capacidad (`capability`)**: permiso accionable atómico (p.ej. `ticket.reply`). La unidad que un rol concede.
- **Ámbito (`scope`)**: dónde aplica una capacidad → `tenant` (un cliente/dominio) o `global` (cross-tenant, solo Syntax).
- **Rol (`role`)**: conjunto nombrado de capacidades. **De sistema** (semilla, inmutable) o **custom por tenant**.
- **Sujeto (`subject`)**: el usuario autenticado con sus roles → conjunto efectivo de `(capability, scope)`.
- **Tenant**: cliente = dominio. Existe un tenant-sistema **`syntax`** al que pertenece el personal de Soporte.

## 2. Catálogo de capacidades (v1)

Agrupadas por recurso. `scope` indica el ámbito máximo en que tienen sentido.

| Capacidad | Descripción | Ámbito |
|---|---|---|
| `ticket.read` | Ver tickets | tenant/global |
| `ticket.create` | Crear tickets | tenant/global |
| `ticket.reply` | Responder (mensaje `public`) | tenant/global |
| `ticket.transition` | Cambiar estado (cualquier destino válido) | tenant/global |
| `ticket.reopen` | Reabrir un ticket `resolved`/`closed` — acotada por el servicio a ese único destino (`reopened`), no da acceso a `ticket.transition` | tenant |
| `ticket.assign` | Asignar a un agente | tenant/global |
| `ticket.update` | Editar campos (`subject`/`priority`/`category`/`csat`) sin cambiar de estado | tenant/global |
| `note.internal.read` | Ver mensajes `internal` (Syntax) | global |
| `note.internal.write` | Escribir notas `internal` | global |
| `approval.decide` | Aprobar/editar/rechazar drafts IA | global |
| `agent.trigger` | Disparar generación de draft IA | tenant/global |
| `kb.read` | Buscar/leer la base de conocimiento | tenant/global |
| `tenant.manage` | CRUD de tenants (clientes) | global |
| `tenant.settings.manage` | Gestiona `TenantSettings` (`auto_approve`) del PROPIO tenant | tenant |
| `user.manage` | Alta/baja/invitación de usuarios | tenant/global |
| `role.manage` | Asignar roles y componer roles custom | tenant/global |
| `analytics.read` | Ver el dashboard | tenant/global |

> El catálogo es **extensible**; nuevas capacidades se añaden aquí y a la seed. El **nombre** es el
> contrato: frontend y api-contract lo referencian literal.

## 3. Roles semilla (de sistema)

Dos familias. La numeración normaliza el brief (1,2,4 → 1,2,3).

**SOPORTE (siempre Syntax · ámbito `global` / cross-tenant):**
- `support_admin` (sub-rol 1) — **todas** las capacidades en `global`: gestión completa de clientes y tickets,
  aprobaciones, notas internas, `tenant/user/role.manage`, `analytics`.
- `support_agent` (sub-rol 2) — gestión de **tickets** cross-tenant: `ticket.*`, `note.internal.*`,
  `approval.decide`, `agent.trigger`, `kb.read`, `analytics.read`. **No** `tenant/user/role.manage`.
- `support_viewer` (sub-rol 3) — solo lectura cross-tenant: `ticket.read`, `note.internal.read`, `kb.read`, `analytics.read`.

**CLIENTE (ámbito `tenant` = su dominio):**
- `client_admin` — sobre su tenant: `ticket.*` (sin `note.internal.*`), `user.manage`, `role.manage`,
  `kb.read`, `analytics.read`, `agent.trigger`. **Nunca** ve `internal`/`developer` ni gestiona otros tenants.
- `client_agent` (usuario normal) — `ticket.create`, `ticket.reply`, `ticket.read`, `ticket.reopen` (de su tenant), `kb.read`, `agent.trigger`.
- `client_viewer` — `ticket.read`, `kb.read` (solo lectura de su tenant).

### Matriz rol × capacidad (resumen)

| capacidad \ rol | sup_admin | sup_agent | sup_viewer | cli_admin | cli_agent | cli_viewer |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| ticket.read | ✅g | ✅g | ✅g | ✅t | ✅t | ✅t |
| ticket.create/reply | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |
| ticket.transition/assign/update | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ |
| ticket.reopen | ✅ | ❌* | ❌ | ❌* | ✅ | ❌ |
| note.internal.* | ✅ | ✅ | read | ❌ | ❌ | ❌ |
| approval.decide / agent.trigger | ✅ | ✅ | ❌ | ❌* / ✅ | ❌ / ✅ | ❌ |
| kb.read / analytics.read | ✅ | ✅ | ✅ | ✅ | ✅r | ❌ |
| tenant.manage | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| user.manage / role.manage | ✅ | ❌ | ❌ | ✅t | ❌ | ❌ |

`g`=global · `t`=acotado al tenant · `r`=solo lectura · `*` (fila `approval.decide/agent.trigger`) la
decisión de aprobación es de Syntax (soporte) · `*` (fila `ticket.reopen`) no tienen la capacidad
`ticket.reopen` en sí, pero ya pueden reabrir por `ticket.transition` (capacidad más amplia que ya
poseen) vía el endpoint genérico — `ticket.reopen` es una capacidad NUEVA y estrecha, pensada para
`client_agent` (que no tiene `ticket.transition`), no una que se reparte a quien ya tiene la general.

## 4. Roles custom por tenant

- Un sujeto con `role.manage` en un tenant compone roles a partir del **catálogo de capacidades**.
- **Invariantes** (fail-closed):
  - No puede conceder capacidades de ámbito `global` (`note.internal.*`, `approval.decide`, `tenant.manage`).
  - No puede conceder una capacidad que **él mismo no posee** (no escalada de privilegios).
  - El rol custom es **tenant-scoped**: solo asignable a usuarios de su tenant.
- Los roles de sistema son **inmutables** (no se editan/borran; se clonan a un custom si hace falta variar).

## 5. Aislamiento multi-tenant (app-level + RLS)

- **App-level (primario)**: toda query pasa por repos que filtran por `tenant_id` del contexto (`get_tenant_context`).
- **RLS (defensa en profundidad, día 1)**: políticas Postgres + `SET app.tenant_id` por conexión (ver 08).
- **Soporte cross-tenant**: capacidad de ámbito `global` → el repo no aplica el filtro (o aplica el tenant
  elegido en el switcher para escribir en nombre de un cliente). Soporte vive en el tenant `syntax`.
- **KB global**: las tablas de KB **no** llevan RLS de tenant (documentación de Syntax, compartida read-only).

## 6. Visibilidad de mensajes (Fase 1)

`public` (cliente + Syntax) · `internal` (solo Syntax, requiere `note.internal.read`). **Sin `developer`** (Fase 2
diferida). El filtro de visibilidad es transversal: se aplica en el backend (query/serialización) **y** el
frontend nunca renderiza lo que no corresponde (defensa en profundidad).

## 7. Contrato de comprobación

```
authorize(subject, capability, scope, resource) -> Allow | Deny
```
- Decide por **capacidad + ámbito**, **nunca por el nombre del rol**.
- **Capacidades resueltas server-side por request** desde la BD (no desde el JWT): un cambio/revocación de
  rol surte efecto en la siguiente request; el TTL corto del access acota la obsolescencia de pertenencia.
- **Acotadas por la sesión activa** (11): `effective_capabilities(user_id, tenant_id)` se resuelve para
  el `tenant_id` de la sesión — un usuario con roles distintos en dos tenants NUNCA ve las capacidades
  del otro tenant en su sesión activa (fix de seguridad de `scenario-coverage`, no una decisión
  discrecional).
- `get_tenant_context` decide `tenant_scope`/`global_scope` por el **ámbito concedido de la capacidad
  requerida** (no por un flag fijo del `Subject`): si `(cap, "global") in subject.capabilities` →
  `global_scope()`; si no, `tenant_scope(subject.tenant_id)`. Con la misma capacidad en ambos ámbitos,
  gana `global`.
- **`resource`** aporta el `tenant_id`/dueño para validar el ámbito (p.ej. `ticket.reply` en `scope=tenant`
  solo aplica a tickets de ESE tenant).
- **Deny → HTTP 403** con el envelope de error estándar (ver 06).

## 8. Refuerzos (scenario-coverage) y anti-patrones

- **Sujeto sin ningún rol → deny-all explícito** (no comportamiento implícito).
- **Fail-closed**: si las capacidades no se pueden resolver, se deniega todo (nunca "abrir por defecto").
- **Nunca** confiar en el nombre del rol para autorizar; **nunca** ampliar permisos por defecto.
- El RBAC del cliente es UX/defensa en profundidad; **la API es la fuente de verdad** (una acción visible que
  la API deniega con 403 se reconcilia sin mutar estado).
- SSO/OIDC (Fase 2): la identidad federada mapeará a un `subject` con los mismos roles/capacidades; este
  contrato no cambia (solo el origen de la identidad).
