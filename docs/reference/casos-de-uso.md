# Referencia · Casos de uso (SDD)

**Fuente canónica:** `.claude/specs/<package>/casos-de-uso/` (Cockburn *fully-dressed* + Gherkin). Son el
**CÓMO** del actor y el **único hogar** del Gherkin de aceptación (anti-duplicación); los **requisitos**
(QUÉ) viven en el `spec.md` de cada package, y las **decisiones** en los [ADR](/reference/adr).

## Backend — `.claude/specs/backend/casos-de-uso/`

| CU | Título |
|----|--------|
| CU-BE-01 | Autenticación y sesiones |
| CU-BE-02 | Recuperación e invitación de contraseña |
| CU-BE-03 | Autorización por capacidad y aislamiento tenant |
| CU-BE-04 | Ciclo de vida del ticket |
| CU-BE-05 | Clasificación y retrieval RAG |
| CU-BE-06 | Draft IA y aprobación HITL |
| CU-BE-07 | Ingestión de la KB |
| CU-BE-08 | Scheduler de SLA |
| CU-BE-09 | Administración de tenants, usuarios y roles |
| CU-BE-10 | Notificaciones in-app |

## Frontend — `.claude/specs/frontend/casos-de-uso/`

| CU | Título |
|----|--------|
| CU-FE-01 | Login y sesión de cliente |
| CU-FE-02 | RBAC de cliente y cambio de tenant |
| CU-FE-03 | Bandeja de tickets |
| CU-FE-04 | Alta de ticket |
| CU-FE-05 | Detalle, visibilidad y mutaciones |
| CU-FE-06 | Flujo IA — cola, draft y decisiones |
| CU-FE-07 | Base de conocimiento |
| CU-FE-08 | Administración y roles |
| CU-FE-09 | Transversales (notificaciones, i18n, estados, offline) |

> Con `features.sdd` activo, el `## Scenarios` de una tarea **nueva** enlaza a su CU en vez de copiar los
> escenarios. Las tareas ya completadas (frontend `helpdesk-core`, backend `skeleton-foundation`) conservan
> su Gherkin inline histórico y **no** se migran.
