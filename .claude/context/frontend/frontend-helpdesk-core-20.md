# Session log — frontend-helpdesk-core-20 (Transversales: notificaciones + i18n + a11y)

## 2026-08-13 — arranque
- Gate TDD: `status: active`; depends_on [06] en `done`; rama del plan. Baseline 268 tests.

### Alcance / dependencias
- Notificaciones: `GET /notifications?unread=` (orden created_at desc) + `PATCH /notifications/{id}/read`. Polling vía `refetchInterval`.
- i18n: test de **paridad de claves** es/en (EN estructura completa aunque progresivo) + test de conmutación de idioma (los textos visibles cambian → no hardcode). No hay regla eslint i18n configurada; la paridad + el test de switch cubren la sustancia.
- **a11y en navegador real (axe)**: requiere `@axe-core/playwright` (dep **nueva** → no la añado sin aprobación del owner) + navegador real. Se **difiere** con nota explícita; la a11y por-feature (roles/labels/live-regions) ya está en la DoD de cada tarea (I4). Queda como follow-up para el owner (encaja con la infra e2e de la 21).

### Decisiones de diseño
- Lógica pura `.ts` (mutación): `notifications.ts` → `unreadCount(items)`.
- Hooks `.ts`: `use-notifications.ts` → `useNotifications(pollMs)` (refetchInterval), `useMarkRead()` (PATCH + invalida).
- Presentación `.tsx`: `notifications-bell.tsx` (campana + conteo + lista + marcar leído), integrada en `app-header.tsx` (reemplaza el placeholder).

## 2026-08-13 — cierre
- **Nuevos**: `src/features/notifications/{notifications.ts, use-notifications.ts, notifications-bell.tsx}` + tests; `src/features/shell/i18n.test.tsx`; fixture `notificationFixture`. **Modificados**: `app-header.tsx` (campana real reemplaza placeholder), `messages/{es,en}.json` (namespace `notifications`).
- **Tests (salida real)**: `pnpm test` → **274 passed / 63 files**; typecheck limpio; lint `No issues found`.
- **Mutación**: Stryker sobre `notifications.ts` + `use-notifications.ts` → **84% ≥ 80** (notifications 100%; use-notifications 80.95%).
- **i18n**: test de **paridad de claves** es↔en (idénticas) + test de **conmutación de idioma** (texto cambia → sin hardcode). ES completo; EN estructura completa (progresivo).
- **Fact-checker** (sonnet): **11/11 VERIFICADO**, incluida la confirmación de que NO se añadió ninguna dependencia.
- **PENDIENTE (qué falta y por qué)**: la **auditoría axe en navegador real** NO se ejecutó — requiere `@axe-core/playwright` (dependencia **nueva**, no la añado sin aprobación) + navegador real. Follow-up del owner; encaja en la infra e2e (21). La a11y por-feature (roles/labels/live-regions/estados) ya está cubierta en cada tarea (I4). **Tiempo real**: ~1h.
