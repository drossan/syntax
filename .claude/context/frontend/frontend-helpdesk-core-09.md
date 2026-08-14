# Session log — frontend-helpdesk-core-09 (Ticket detalle: hilo + visibilidad, lectura)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [07, backend-03, backend-06] en `done`; rama del plan. Baseline 113 tests.

### Decisiones de diseño
- Endpoints: `GET /tickets/{id}` (cabecera) + `GET /tickets/{id}/messages` (hilo, orden `created_at asc`).
- **Filtro de visibilidad = defensa en profundidad**: el server ya filtra `internal` por capacidad, pero el cliente **también** filtra según `note.internal.read` (rbac: scope global → un cliente nunca lo tiene). Aunque el payload traiga una nota interna, el cliente NUNCA la muestra sin la capacidad.
- Lógica pura en `.ts` (mutación): `message-visibility.ts` → `filterByVisibility(messages, canSeeInternal)`, `sortChronologically(messages)`, `prepareThread(...)`. Hooks en `use-ticket.ts`: `useTicket(id)` + `useTicketMessages(id)`.
- Presentación `.tsx`: `ticket-header.tsx` (read-only; mutaciones en 10), `ticket-thread.tsx` (texto inerte anti-XSS, autor/fecha/badge visibilidad+IA), `ticket-detail.tsx` (contenedor + estados). Página `app/(app)/tickets/[id]/page.tsx` (`params: Promise`, Next 16) guard `ticket.read`.
- Ticket inaccesible (404/403) → estado no-encontrado/sin-acceso sin filtrar datos (no renderiza hilo/cabecera).

## 2026-08-13 — cierre
- **Nuevos**: `src/features/tickets/{message-visibility.ts, use-ticket.ts, ticket-header.tsx, ticket-thread.tsx, ticket-detail.tsx}` + tests; `app/(app)/tickets/[id]/{page.tsx,page.test.tsx}`; `messageFixture`/`messagePageFixture` en `mocks/fixtures.ts`. **Modificados**: `messages/{es,en}.json` (namespace `ticketDetail`).
- **Decisiones técnicas**: `sortChronologically` usa `localeCompare` sobre ISO (orden lexicográfico == cronológico, sin `Date.parse`); queryKeys extraídos a funciones puras (`ticketKey`/`ticketMessagesKey`) para testear el aislamiento por tenant; página dinámica tipada `{ params: Promise<{id}> }` explícito (no `PageProps<T>`, que exige la ruta en `.next/types` regenerado).
- **Tests (salida real)**: `pnpm test` → **132 passed / 28 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `message-visibility.ts` + `use-ticket.ts` → **92.31% ≥ 80**. 2 survivors en `use-ticket.ts` (`if(error) throw error`) = equivalentes: react-query v5 también convierte un `return undefined` en error → mismo `isError`.
- **Fact-checker** (sonnet, independiente): **10/10 VERIFICADO**.
- **Tiempo real**: ~1.2h. **Follow-ups**: mutaciones (10), adjuntos (11), SLA/timeline (12) cuelgan de este detalle.
