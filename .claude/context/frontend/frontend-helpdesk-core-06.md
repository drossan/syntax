# Session log — `frontend-helpdesk-core-06` — App shell / layout

> Append-only. Registro canónico de la tarea (task-lifecycle §Cerrar una tarea).

## 2026-08-13 — Ejecución

### Precondición

- `depends_on`: `frontend-helpdesk-core-05` (done). Reutiliza `useCan`/`<Can>` (05) para la nav,
  `TenantSwitcher` (05) y `useLogout` (03) en el header.

### Qué se hizo (TDD rojo→verde)

- **i18n conmutable**: `LocaleProvider` + `useLocaleSwitcher` (`features/shell/locale-provider.tsx`):
  estado de locale en cliente + `NextIntlClientProvider` (es/en). Sustituye el `NextIntlClientProvider`
  fijo del scaffold. Mensajes `nav.*` y `header.*` añadidos a `messages/{es,en}.json`.
- **Tema/dark**: `ThemeProvider` + `useTheme` (propio, **sin `next-themes`**): aplica la clase `dark` a
  `<html>` (Tailwind v4) y **persiste** en `localStorage` (`syntax-theme`); al montar respeta lo guardado
  o la preferencia del sistema. `ThemeToggle` (aria-label + aria-pressed).
- **`LanguageSwitcher`** (select ES/EN) cableado a `LocaleProvider`.
- **`AppNav`**: entradas derivadas de capacidades (cada una envuelta en `<Can>`); labels vía
  `useTranslations("nav")`.
- **`AppHeader`**: marca, `TenantSwitcher`, campana (placeholder → 20), `LanguageSwitcher`, `ThemeToggle`,
  logout. **`AppShell`**: header + nav lateral (colapsa a columna en móvil) + slot de contenido.
- **Layout `(app)`**: `src/app/(app)/layout.tsx` monta el `AppShell`. La home `/` se **movió a
  `(app)/page.tsx`** para que use el shell (antes en `src/app/page.tsx`; el test smoke la sigue).
- `providers.tsx` reescrito: Query → Theme → Auth → Tenant → Locale. `render-with-session` ampliado con
  Theme + Locale (helper canónico de subárbol autenticado).

### Escenarios Gherkin → tests (1:1)

- «la navegación refleja las capacidades» → `app-nav.test.tsx` (sin `tenant.manage` no aparece "Clientes").
- «cambio de idioma» → `language-switcher.test.tsx` (ES "Bandeja" → EN "Inbox").
- «cambio de tema» → `theme-toggle.test.tsx` (dark class + persistencia + aria-pressed; y vuelta a claro).

### Verificación (comandos corridos en esta sesión)

- `pnpm --filter frontend test` → **71 passed (17 ficheros)**.
- `tsc --noEmit` → 0. `eslint` → 0/0. `prettier --check .` → limpio.
- `next build` → OK (`/` sirve `(app)/page` dentro del shell).
- `stryker run` → **90.76%** (break 80); task 06 añade solo `.tsx` (cubiertos por RTL).

### Incidencias resueltas

- **Route types obsoletos**: mover `page.tsx` a `(app)/` dejó `.next/dev/types/validator.ts` apuntando a
  la ruta vieja → `tsc`/build fallaban. Solución: `rm -rf .next` + `next build` regenera los tipos.
- **Lint `react-hooks/set-state-in-effect`**: el init de tema desde `localStorage` va en un `useEffect`
  post-montaje (SSR-safe: server = 'light', cliente sincroniza al hidratar); consolidado en un `setTheme`
  con `eslint-disable-next-line` justificado. El script anti-flash de tema queda para la task 20.

### Cierre

- **Gate `fact-checker`** (subagente fresco, sonnet): 12/13 VERIFICADO + **1 matiz real cazado y
  corregido**: `next build` imprimía `Error: ENVIRONMENT_FALLBACK` de next-intl (falta `timeZone` →
  formateo dependiente del entorno, contra cross-cutting §2). **Fix**: `timeZone="Europe/Madrid"` en
  `NextIntlClientProvider`. Verificado: `next build` ahora **0 `Error:`**, compila limpio. (tz por-usuario
  → tasks 12/20.)
- Tarea `active → done` (`actual: 4h`), movida a `completed/`; `[x]` en el plan; commit
  `frontend-helpdesk-core-06: …`.
