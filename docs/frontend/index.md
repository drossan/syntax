# Frontend · visión general

Next.js 16 (App Router) + TypeScript estricto + Tailwind v4 + shadcn/ui.

> **Estado.** El frontend se desarrolla con **código real y TDD** (a diferencia del backend, que en esta
> fase es esqueleto doc-only). El plan `frontend/helpdesk-core` está **pendiente** de arranque; su punto de
> partida es `.claude/specs/frontend/HOW-TO-START-A-TASK.md`.

## Cómo se relaciona con el backend

El frontend **no** conoce la implementación del backend: se acopla al [contrato de API](/reference/api-contract)
(OpenAPI 3.1). De ese contrato deriva:

- **Cliente tipado** (tipos generados desde el `api-contract.yaml`).
- **Mocks MSW** (éxito **y** error, a partir del envelope `problem+json`), para desarrollar y testear sin
  backend real.

Ambos tienen su propio **gate de conformidad** contra el `.yaml` (los tipos y los mocks no divergen del
contrato).

## Superficie que consume

El flujo que el frontend necesita mockear/ejercer de punta a punta:

```
login → listar/crear tickets → disparar ai-draft → cola de aprobaciones → aprobar/editar/rechazar
      → el borrador aprobado aparece como mensaje público en el ticket
```

Más: administración (tenants/usuarios/roles con role builder), KB (búsqueda), notificaciones (in-app +
polling) y dashboard de analítica. Todo definido en el [contrato de API](/reference/api-contract).

## RBAC en el cliente

El [RBAC](/reference/rbac) del frontend es **UX / defensa en profundidad** (mostrar/ocultar acciones por
capacidad); **la API es la fuente de verdad**: una acción visible que la API deniega con 403 se reconcilia
sin mutar estado.
