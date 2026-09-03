---
id: frontend-markdown-editor-01
package: frontend
plan: markdown-editor
status: done
priority: 1
depends_on: []
estimate: 1 sesión
actual: 1 sesión
issue:
created: 2026-09-01
updated: 2026-09-01
---

# Componente `MarkdownEditor` y adopción en las 3 superficies de composición/edición

## Description

El plan `markdown-rendering` (cerrado) resolvió la lectura (`MarkdownText`); esta tarea resuelve la
escritura. Nuevo componente compartido `MarkdownEditor` (`@uiw/react-md-editor`) que sustituye los
`<textarea>` planos de `ticket-reply-form.tsx`, `ticket-create-form.tsx` y `approval-decision.tsx`
(modo edición), sin cambiar el formato de almacenamiento (sigue siendo un string de Markdown) ni el
contrato de API. Diseño completo, con el hallazgo crítico de seguridad y su corrección, en
[ADR-0021](../../../specs/adr/0021-editor-markdown-nativo-con-preview-reusando-el-allow-list.md).

## Spec

- **Nueva dependencia**: `@uiw/react-md-editor` (v4.1.2, MIT).
- **`frontend/src/components/markdown-editor.tsx`** (nuevo, mismo patrón de ubicación que
  `markdown-text.tsx`):
  - Envuelve `@uiw/react-md-editor`, importado vía `next/dynamic` con `ssr: false` (usa APIs de
    navegador).
  - `preview="live"`. **Obligatorio**: prop `components.preview` sobreescrita para renderizar con
    `MarkdownText` (no el motor de preview por defecto de la librería) — es el hallazgo crítico de
    `design-review`, ver ADR-0021 §"Preview: sobreescrita con `MarkdownText`".
  - Toolbar completo vía `commands`/`extraCommands` del paquete: negrita, cursiva, tachado, listas
    (ordenada/no ordenada), enlace, imagen, código, cita, tabla. `checkedListCommand` **excluido**
    explícitamente (`excludeCommands`) — ADR-0021.
  - **`excludeCommands` también retira el comando nativo de alternar modo de vista**
    (edit/live/preview) — `scenario-coverage`: mantenerlo contradiría fijar `preview="live"` en las 3
    superficies (decisión de consistencia de `grilling`).
  - **Verificar en implementación** si `@uiw/react-md-editor` embebe por defecto una imagen
    pegada/arrastrada como `data:`/base64 en el propio texto (`scenario-coverage`, comportamiento no
    confirmado de la librería). Si lo hace, **bloquearlo explícitamente** (interceptar el evento de
    paste/drop del editor y descartar imágenes embebidas) — contradice directamente la decisión
    "solo URL externa" de ADR-0021; no se acepta como riesgo conocido, se corrige.
  - Tooltips/etiquetas de cada comando traducidos vía `next-intl` (nuevo namespace o claves añadidas
    a uno existente — a decidir en implementación, sin crear un namespace por componente si uno
    genérico de UI ya existe).
  - `data-color-mode` derivado de `useTheme()` (`frontend/src/features/shell/theme-provider.tsx`) —
    sincroniza el tema del editor con el `.dark` de la app, reactivo a cambios en caliente
    (`scenario-coverage`).
  - Props: `value: string`, `onChange: (value: string) => void`, y las que haga falta pasar
    (`aria-label`, `id`) para mantener la accesibilidad de los `<label htmlFor>` existentes.
- **`ticket-reply-form.tsx`**: sustituir `<textarea {...register("body")}>` por `Controller` de RHF
  (`control`, `name="body"`) envolviendo `MarkdownEditor` — primer uso de `Controller` en el repo.
  **Verificar explícitamente** (`scenario-coverage`) que usar un botón del toolbar (inserción
  programática, no un evento de teclado nativo) dispara `field.onChange` y por tanto marca el
  formulario como `dirty`/inválido correctamente — no asumirlo por analogía con `register()`.
- **`ticket-create-form.tsx`**: mismo patrón `Controller` para el campo de descripción. **Riesgo de
  regresión real** (`scenario-coverage`): `useUnsavedGuard(isDirty)` ya existe en este formulario y
  depende de que RHF marque `isDirty` — verificar que sigue disparándose tras el cambio de
  `<textarea>` a `Controller`+`MarkdownEditor`, con un test explícito (no solo confiar en que RHF lo
  maneja igual que con un input nativo).
- **`approval-decision.tsx`**: el `<textarea>` de modo edición (`draftText`/`setDraftText`) pasa a
  `MarkdownEditor` con `value={draftText}`/`onChange={setDraftText}` (ya es estado local de React, no
  RHF — no necesita `Controller`).

## Fuera de alcance

- Cualquier cambio al contrato de API o al backend.
- El textarea de nota de rechazo (`human_note` en `ConfirmDialog`) — no es Markdown.
- WYSIWYG completo (Tiptap/Lexical) — descartado en el plan.
- Integración de imágenes con el sistema de adjuntos — solo URL externa (ver ADR-0021).
- Optimizar/cachear el bundle de `@uiw/react-md-editor` más allá del `next/dynamic` básico.

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin), endurecidos con `scenario-coverage` (11 escenarios añadidos), en
los casos de uso:
- [CU-FE-04 — Alta de ticket](../../../specs/frontend/casos-de-uso/CU-FE-04-alta-de-ticket.md) —
  extensión 1a y 7 escenarios (editor en la descripción, preview con el mismo renderer del hilo,
  Markdown llega intacto a la creación, descripción vacía, `isDirty` con el toolbar, guard de salida
  activado tras marcar el formulario modificado, estado de carga antes de hidratar).
- [CU-FE-05 — Detalle, visibilidad y mutaciones](../../../specs/frontend/casos-de-uso/CU-FE-05-detalle-visibilidad-y-mutaciones.md)
  — extensión 1d y 9 escenarios (editor en la respuesta, casilla de tarea excluida, botón nativo de
  modo de vista excluido, Markdown llega intacto al publicar, validación de campo obligatorio con el
  editor, marcado adversario tecleado a mano, `Scenario Outline` por comando del toolbar, toolbar
  operable por teclado, tooltips reactivos al locale).
- [CU-FE-06 — Flujo IA: cola, ciclo de draft y decisiones](../../../specs/frontend/casos-de-uso/CU-FE-06-flujo-ia-cola-draft-decisiones.md)
  — extensión 4c y 7 escenarios (editor al editar un borrador, preview reusa el allow-list de la
  cola, tema reactivo en caliente, texto en curso no se pierde al cambiar de tema, polling no
  interrumpe una edición activa, checkbox tecleado a mano se desenvuelve, pegar/arrastrar imagen no
  se embebe como base64).

## Provides

—

## Definition of Done

- [x] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [x] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [x] Todos los tests en verde (457/457, `pnpm vitest run`)
- [x] Spec cumplida
- [x] Lint / format / typecheck OK (`pnpm lint`, `pnpm typecheck`)
- [x] Gate de mutation testing (Stryker, `break: 80`) superado en `markdown-editor.tsx` (86–90%) y en
      las 3 superficies tocadas: `ticket-reply-form.tsx` (94–96%), `ticket-create-form.tsx` (84–86%),
      `approval-decision.tsx` (94–95%) — rango observado entre corridas propias y las del gate
      `fact-checker` independiente, siempre ≥80% (`perTest` de Stryker introduce varianza entre
      corridas, ya documentado en esta sesión, no un defecto real). Supervivientes restantes
      documentados como mutantes equivalentes (parámetros muertos de hooks nunca disparados,
      `ssr:false→true` no observable bajo jsdom, argumento `translate` inalcanzable en `problemToUi`,
      comparación `+1`/`-1` de una key de remount).
- [x] Gate `sdd-lint` superado — CU-FE-04/05/06/ADR-0021 sin ERROR de formato/completitud; 8 AVISO
      reconocidos (asimetría de trazabilidad FR↔editor en `spec.md`, 2 escenarios compuestos ya
      corregidos, desajuste de conteo de escenarios en esta tarea, ya corregido)
- [x] Gate de `fact-checker` superado — 10/11 afirmaciones VERIFICADO a la primera; 1 INCORRECTO
      ("457/457 en verde" no era determinista: 3 tests flakeaban bajo carga de CPU por el
      `next/dynamic` de `MarkdownEditor` corriendo contra el timeout por defecto de testing-library,
      1000ms) — corregido (`asyncUtilTimeout: 5000` en `src/test/setup.ts`) y re-verificado con 4
      corridas limpias consecutivas de la suite completa tras el fix
- [x] Verificación manual contra el backend real: escribir con el toolbar en las 3 superficies,
      confirmar que el resultado se renderiza correctamente al publicarse/aprobarse/crearse
- [x] Documentación actualizada:
  - [x] TSDoc/docstrings en `markdown-editor.tsx` y en las 3 superficies donde cambia el campo
  - [ ] Histórico de la tarea — session log en
        `.claude/context/frontend/frontend-markdown-editor-01.md`
- [x] Docs de dev / usuario final + `pnpm changeset` donde aplique (N/A — sin `pnpm changeset` en este repo)
