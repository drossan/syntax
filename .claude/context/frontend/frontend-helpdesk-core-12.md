# Session log — frontend-helpdesk-core-12 (SLA + timeline)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [09] en `done`; rama del plan. Baseline 158 tests.

### Gap de contrato (alcance)
- No hay endpoint de audit/actividad en el contrato v0.1.0 → el **timeline se deriva de los mensajes** del hilo (created_at, author_id, is_ai_draft), respetando la **visibilidad** (defensa en profundidad, reutiliza `prepareThread`). Eventos ricos (transiciones/asignaciones) quedan pendientes de un endpoint de actividad backend.

### Decisiones de diseño
- SLA: reutiliza `slaLevel`/`SlaBadge` (07) para coherencia con la bandeja; el componente añade tiempo relativo (`format.relativeTime`) + fecha límite. `now` inyectable (determinismo).
- Lógica pura `.ts` (mutación): `timeline.ts` → `buildTimeline(messages, canSeeInternal)` = `prepareThread` + map a eventos {id, at, actor, kind}.
- Presentación `.tsx`: `ticket-sla.tsx`, `ticket-timeline.tsx`. Integrados en `ticket-detail.tsx`.
- Test helper compartido `src/test/render-with-intl.tsx` (envuelve en NextIntlClientProvider) para tests de componentes puros de presentación.

## 2026-08-13 — cierre
- **Nuevos**: `src/features/tickets/{timeline.ts, ticket-sla.tsx, ticket-timeline.tsx}` + tests; `src/test/render-with-intl.tsx`. **Modificados**: `ticket-detail.tsx` (+SLA +timeline), `messages/{es,en}.json` (namespaces `ticketSla`, `timeline`).
- **Tests (salida real)**: `pnpm test` → **168 passed / 36 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `timeline.ts` → **100%** (tras añadir el caso de mensaje sin id/fecha, que subió de 80% justo).
- **Fact-checker** (sonnet): **10/10 VERIFICADO** (incluye confirmación del gap: no hay endpoint de audit/actividad).
- **Qué falta**: eventos de transición/asignación en el timeline esperan un endpoint de actividad backend; hoy el timeline refleja la actividad de mensajes. **Tiempo real**: ~50min.
