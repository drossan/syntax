---
id: frontend-markdown-rendering-04
package: frontend
plan: markdown-rendering
status: done
priority: 3
depends_on: []
estimate: 0.5h
actual: 0.7h
issue:
created: 2026-08-31
updated: 2026-08-31
---

# Corregir la exclusión de `.tsx`/`src/components/**` en `stryker.config.json`

## Description

`frontend/stryker.config.json` termina su array `mutate` con `"!src/**/*.tsx"`, que anula la
inclusión de `.tsx` de la línea `"src/features/**/*.{ts,tsx}"` — un `pnpm exec stryker run` **sin
acotar** (sin `--mutate`) nunca muta ningún `.tsx` del repo. Además, `src/components/**` (el
directorio nuevo de la tarea `01`) no está en el glob en absoluto. Hallazgo de `design-review` del
plan `markdown-rendering`, ampliado a corrección explícita por el owner.

**Verificado que esto NO bloquea el gate de mutation de las tareas `01`-`03`**: `pnpm exec stryker
run --mutate "<fichero>"` ignora por completo el `mutate`/exclusiones del config (probado en vivo con
un fichero de prueba en `src/components/`, 100% de score). Esta tarea es higiene del repo para el
caso **sin acotar** (`pnpm mutation` / `pnpm exec stryker run` a secas), no un requisito de las otras
tareas de este plan.

## Spec

- Quitar `"!src/**/*.tsx"` del array `mutate` de `frontend/stryker.config.json`.
- Añadir `"src/components/**/*.{ts,tsx}"` al array `mutate`.
- Mantener las demás exclusiones existentes (`"!src/**/*.{test,spec}.{ts,tsx}"`, `"!src/**/*.d.ts"`,
  `"!src/lib/utils.ts"`) intactas.
- **No** ejecutar `pnpm exec stryker run` sin acotar hasta `break: 80` como parte de esta tarea — el
  volumen de survivors resultante (mutation real por primera vez en todos los `.tsx` del repo) es
  trabajo aparte, fuera de este plan; se señala para el owner en el session log de cierre.

## Fuera de alcance

- Llevar el `pnpm exec stryker run` sin acotar a superar `break: 80` — volumen fuera de esta tarea,
  señalado para el owner.
- Cualquier cambio de código de producción — esta tarea toca solo `stryker.config.json`.
- Las tareas `01`-`03` (el gate de mutation de esas tareas ya funciona sin este cambio, verificado).

## Scenarios (Gherkin)

Esta tarea no produce código testeable (cambio de configuración, no lógica de negocio). Verificación:
un fichero de prueba desechable en `src/components/` (creado, verificado, y **borrado** al terminar
la tarea — no se commitea) confirma que `pnpm exec stryker run` **sin** `--mutate` (usando solo el
`mutate` del config corregido) sí lo alcanza y muta, donde antes de esta tarea no lo hacía.

## Provides

—

## Definition of Done

- [x] Spec cumplida — diff mínimo, sin tocar nada más del fichero
- [x] Lint / format / typecheck OK (`pnpm lint`, `pnpm typecheck`) — sin impacto esperado, se verifica
      igual
- [x] Verificación funcional del glob corregido (ver `## Scenarios`), sin dejar ningún fichero de
      prueba commiteado
- [x] Gate de mutation testing: N/A — esta tarea modifica el propio config de mutation testing, no
      código de producción con lógica que mutar
- [x] Gate `sdd-lint` superado — artefactos SDD sin ERROR de formato/completitud (AVISO se reconoce)
- [x] Gate de `fact-checker` superado — afirmaciones de la sesión verificadas
- [x] Documentación actualizada:
  - [x] Histórico de la tarea — session log en
        `.claude/context/frontend/frontend-markdown-rendering-04.md`, incluyendo la nota explícita
        para el owner sobre el volumen de survivors pendiente en el `pnpm exec stryker run` sin acotar
- [x] Docs de dev / usuario final + `pnpm changeset` donde aplique (N/A — sin `pnpm changeset` en este repo)
