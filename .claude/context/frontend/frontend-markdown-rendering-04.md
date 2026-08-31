# Session log — frontend-markdown-rendering-04

## 2026-08-31
- `frontend/stryker.config.json`: quitada `"!src/**/*.tsx"` del array `mutate`; añadida
  `"src/components/**/*.{ts,tsx}"`. Resto de exclusiones (`test/spec`, `*.d.ts`, `lib/utils.ts`)
  intactas.
- Verificación funcional: fichero de sonda desechable `src/components/__probe.ts` +
  `__probe.test.ts`, `pnpm exec stryker run` **sin** `--mutate` (config corregido). Ejecución
  completa (coverage `perTest` sobre toda la suite): 21 min. Confirmado en el reporte que ficheros
  `.tsx` reales (`ticket-thread.tsx` 96.30%, `tickets-table.tsx` 31.75%, `ticket-detail.tsx` 43.33%,
  etc.) aparecen mutados — antes de esta tarea el `mutate` los excluía por completo. Sonda borrada
  tras la verificación, sin commitear (confirmado con `git status`).
- **Resultado del run sin acotar**: mutation score final **70.31%**, bajo el umbral `break: 80` →
  exit code de fallo. Esto es el resultado **esperado y fuera de alcance de esta tarea** (ver
  `## Fuera de alcance` de la tarea): es la primera vez que se muta `.tsx` sin acotar en todo el
  repo, y el volumen de survivors resultante es trabajo aparte para el owner, no un requisito de
  cierre de esta tarea.
- `pnpm lint` / `pnpm typecheck`: limpios.
- `sdd-lint`: esta tarea no toca ningún artefacto SDD (solo `stryker.config.json`); comprobación
  mecánica rápida (sin `[NECESITA ACLARACIÓN`, estado del ADR-0020 válido) — limpio, nada que
  reportar.
- `fact-checker`: 7/7 VERIFICADO (glob corregido, exclusiones intactas, lint/typecheck limpios, sin
  ficheros de sonda en el árbol, `reports/mutation/mutation.html` existe e ignorado por git).

## Nota para el owner
El `pnpm exec stryker run` sin acotar (config real, sin `--mutate`) ya alcanza todos los `.tsx` del
repo y da **70.31%** de mutation score — por debajo de `break: 80`. Los survivors resultantes
(vistos en `frontend/reports/mutation/mutation.html`, no commiteado) son volumen real de features
existentes que nunca se mutaron hasta ahora (p. ej. `tickets-table.tsx` 31.75%,
`ticket-create-form.tsx` 57.41%, `shell/theme-provider.tsx` 55%). Llevar esto a `break: 80` es
trabajo aparte, fuera de este plan.

## Cierre
- DoD completa. Tarea movida a `completed/`, `status: done`, `[x]` en el plan.
- Ficheros tocados: `frontend/stryker.config.json`.
- Última tarea del plan `markdown-rendering` — el plan se cierra a continuación.
