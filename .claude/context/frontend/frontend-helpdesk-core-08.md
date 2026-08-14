# Session log — frontend-helpdesk-core-08 (Alta de ticket)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [07] en `done`; rama del plan.
- Baseline verde heredado de 07: 96 tests / 20 files.

### Decisiones de diseño
- Contrato `TicketCreate` = `{ subject* , body?, priority? }` — **NO incluye `domain`** (la clasificación de dominio es backend; ya está en "Fuera de alcance: Clasificación IA"). El form envía solo subject/body/priority; no se inventa `domain` en el request (gap de contrato reconocido). El Gherkin "y dominio válidos" se cumple vía asunto/descr/prioridad; el dominio lo asigna el backend.
- Lógica en `.ts` (mutación): `ticket-create-schema.ts` (Zod + `toTicketCreateBody` que omite body vacío), `use-create-ticket.ts` (useMutation → `POST /tickets`, invalida `["tickets"]` en éxito — cross-cutting §6: creación = invalidación, no optimistic).
- Presentación `.tsx`: `ticket-create-form.tsx` (RHF+Zod, mapea 422 → fieldErrors vía `problemToUi`), página `app/(app)/tickets/new/page.tsx` guard `ticket.create`.
- Enlace "Nuevo ticket" en la bandeja (07) tras `<Can capability="ticket.create">`.
- `tenant_id`: no va en el body (contrato no lo pide); el server lo deriva del sujeto/tenant activo.

## 2026-08-13 — cierre
- **Nuevos**: `src/features/tickets/{ticket-create-schema.ts, use-create-ticket.ts, ticket-create-form.tsx}` + tests; `app/(app)/tickets/new/{page.tsx,page.test.tsx}`. **Modificados**: `tickets-inbox.tsx` (+enlace "Nuevo ticket" con `<Can ticket.create>`), `tickets-inbox.test.tsx` (+2 tests del enlace), `messages/{es,en}.json` (namespace `ticketCreate` + `tickets.new`).
- **Tests (salida real)**: `pnpm test` → **113 passed / 24 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `ticket-create-schema.ts` + `use-create-ticket.ts` → **100%** (24 killed / 0 survived). Requirió test unitario del hook con `renderHook` (asserta body enviado + invalidación `["tickets"]` + rechazo en 422) y casos de trim en el schema.
- **Fact-checker** (sonnet, independiente): **10/10 VERIFICADO**.
- **Tiempo real**: ~1h. **Follow-ups**: la navegación a `/tickets/${id}` apunta al detalle que crea la 09.
