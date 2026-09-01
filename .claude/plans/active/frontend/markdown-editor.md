---
id: frontend-markdown-editor
package: frontend
status: active
branch: plan/frontend/markdown-editor
issue:
created: 2026-09-01
updated: 2026-09-01
---

# Editor de texto enriquecido (Markdown) para composición/edición

## Contexto y problema

El plan `markdown-rendering` (ya cerrado, PR #14) añadió `MarkdownText` — un **renderizador** de
Markdown de solo lectura, usado en `ApprovalDecision` (draft en revisión) y `TicketThread` (mensajes
publicados). El usuario esperaba que esto incluyera también una caja para **escribir/editar** con
formato, y no la encontró: los tres sitios donde el usuario ESCRIBE Markdown crudo siguen siendo
`<textarea>` planos, sin tocar (confirmado leyendo el código):

- `frontend/src/features/tickets/ticket-reply-form.tsx:121` — responder a un ticket (nuevo `Message`).
- `frontend/src/features/approvals/approval-decision.tsx:79` — editar el draft de la IA antes de aprobar.
- `frontend/src/features/tickets/ticket-create-form.tsx:87` — descripción inicial al crear un ticket
  (se convierte en el primer `Message` del hilo).

Los tres valores se guardan como **string de Markdown** (sin cambio de contrato — `body`/`draft_body`/
`final_body` ya son `string` en `api-contract.yaml`) y ya se renderizan con `MarkdownText` una vez
publicados/aprobados. Este plan es **puramente frontend**: no toca el backend ni el contrato.

**Excluido de raíz** (no es Markdown, no se renderiza con `MarkdownText`): el textarea de nota de
rechazo (`human_note`, `ConfirmDialog` dentro de `approval-decision.tsx`) — se muestra como texto plano
en `approval-decision.tsx`, no pasa por el renderer.

## Objetivos

1. **Sustituir los `<textarea>` planos de esas 3 superficies por un editor que ofrezca formato**
   (negrita, cursiva, listas, enlace como mínimo) y produzca el mismo string de Markdown que
   `MarkdownText` ya sabe renderizar — sin cambiar el contrato de API ni el formato de almacenamiento.
   - *Criterio de éxito*: escribir con el toolbar en las 3 superficies produce un texto que, al
     publicarse/aprobarse, se renderiza correctamente con `MarkdownText` (mismo resultado visual que un
     draft de la IA con la misma sintaxis).

## Alcance y fuera de alcance

### Dentro del alcance
- **Editor "Markdown-nativo" con toolbar, NO WYSIWYG completo.** Un WYSIWYG real (Tiptap/Lexical) opera
  sobre un documento interno (HTML/JSON) y necesitaría serializar A Markdown y deserializar DESDE
  Markdown en cada carga/guardado — riesgo real de conversión con pérdida, porque el allow-list de
  `MarkdownText` (ADR-0020) es un subconjunto deliberadamente distinto del HTML completo (sin tablas
  anidadas, sin estilos inline, casillas de tarea excluidas a propósito). Un editor Markdown-nativo
  evita esa doble conversión: el valor que produce el editor ES el string que ya se guarda y ya se
  renderiza.
- **Componente compartido nuevo** `MarkdownEditor` (mismo patrón que `MarkdownText`, en
  `frontend/src/components/`) para no triplicar la configuración del toolbar entre las 3 superficies.
- **`grilling`**: librería `@uiw/react-md-editor` (v4.1.2, `peerDependencies: react >=16.8.0` —
  verificado, compatible con React 19) — confirmado sobre la alternativa de toolbar hecha a mano.
  Requiere `next/dynamic` con `ssr: false` (usa APIs de navegador, no soporta SSR) — detalle de
  implementación.
- **`grilling`**: `preview="live"` (split-pane) en las **3 superficies** — decisión explícita del owner
  (revierte mi recomendación inicial de `preview="edit"` sin previsualización), por consistencia de
  comportamiento del editor en todo el producto.
- **`grilling`**: las 3 superficies se adoptan a la vez, no por fases — confirmado el recomendado (mismo
  componente compartido montado en 3 sitios, hacerlo por partes tripliraría el ciclo de verificación sin
  reducir riesgo real).
- **`grilling`**: toolbar completo, incluye tabla e imagen (revierte mi recomendación de subconjunto
  simple) — la librería los soporta de fábrica.
- **`grilling` (hecho verificado)**: `GET /messages/{id}/attachments/{attachment_id}` exige
  `Authorization` (401 sin él) — no es una URL pública, un `<img>` de Markdown no puede mandar
  cabeceras. El botón de imagen es **solo pegar URL externa** (confirmado el recomendado) — NO integra
  con el sistema de adjuntos (eso exigiría exponer una URL pública/firmada en el backend, fuera del
  alcance "puramente frontend" ya declarado, o un blob-URL local sin persistencia real entre sesiones).
- **`grilling`**: tooltips/aria-labels del toolbar traducidos vía `next-intl` (confirmado el
  recomendado) — consistente con el resto del producto en español; `@uiw/react-md-editor` permite
  pasar comandos personalizados (icono + `keyCommand` + tooltip), no hace falta tocar la librería.
- **Anti-XSS (`design-review` #1, CRÍTICO)**: el preview interno de `@uiw/react-md-editor`
  (`preview="live"`) usa su PROPIO motor de renderizado, no `MarkdownText` — sin más, reabriría
  ADR-0020 sin decirlo: el paquete no sanea HTML embebido por defecto en su preview (necesita
  `rehype-sanitize` explícito), y `draftText`/`approval.draft_body` es exactamente el "origen no
  confiable" que la ADR protege. **Obligatorio**: sobreescribir el renderer de preview del editor
  (prop `components.preview` de `@uiw/react-md-editor`) para que use el propio `MarkdownText` —
  mismo allow-list ya auditado, y además garantiza que lo que se ve en el preview ES exactamente lo
  que se renderizará al publicar (WYSIWYG real, no una aproximación de un segundo motor). NO se usa
  `rehype-sanitize` como alternativa: mantiene un único punto de verdad del allow-list.
- **`checkedListCommand` excluido del toolbar** (`design-review` #2): ADR-0020 excluye a propósito
  las casillas de lista-de-tareas de GFM del allow-list de `MarkdownText` (se desenvuelven a texto
  plano). El comando por defecto del toolbar que inserta `- [ ] texto` se retira explícitamente
  (`excludeCommands` de `@uiw/react-md-editor`) — si no, el propio botón del toolbar produciría un
  resultado que se rompe al publicar (`[ ] texto` literal, sin checkbox).
- **Integración con `react-hook-form`** (`design-review` #3): `@uiw/react-md-editor` es un componente
  controlado (`value`/`onChange`), no compatible con `{...register("body")}` sobre un `<textarea>`
  nativo. Las 2 superficies con formularios RHF (`ticket-reply-form.tsx`, `ticket-create-form.tsx`)
  necesitan `Controller` de RHF envolviendo `MarkdownEditor` — patrón nuevo en el repo (0 usos hoy de
  `Controller`, verificado), añadido explícitamente a la estimación de la tarea.
- **Theming** (`design-review` #4): `MarkdownEditor` lee el tema activo con el hook ya existente
  (`useTheme()` de `theme-provider.tsx`) y lo traduce al `data-color-mode` que espera
  `@uiw/react-md-editor` — sin este wiring, el editor queda visualmente desincronizado del `.dark` de
  la app.

### Fuera de alcance
- Cualquier cambio al contrato de API (`api-contract.yaml`) o al backend — los campos ya son `string`.
- El textarea de nota de rechazo (`human_note`) — no es Markdown, no se renderiza con `MarkdownText`.
- WYSIWYG completo (Tiptap/Lexical) — descartado explícitamente por el riesgo de conversión con
  pérdida frente al allow-list de `MarkdownText`.

## Consecuencias / riesgos aceptados

- **Riesgo aceptado, no mitigado** (`design-review`, reversibilidad): el Markdown ya persistido con
  `checkedListCommand` (si se hubiera usado antes de excluirlo del toolbar) no se corrige
  retroactivamente — excluir el comando solo evita casos nuevos. No hay Markdown histórico con esta
  sintaxis (feature nueva), así que el riesgo es teórico en el momento de cerrar este plan.
- **Coste de mantenimiento aceptado**: los tooltips traducidos del toolbar (comandos personalizados)
  no se actualizan solos si una versión futura de `@uiw/react-md-editor` cambia sus comandos por
  defecto — reconciliación manual en el próximo bump de la dependencia.
- **`preview="live"` en las 3 superficies, incluida `ticket-reply-form`** (espacio compacto,
  `rows={3}` hoy): reafirmado tras `design-review` #6 — el owner prioriza consistencia de
  comportamiento del editor sobre el espacio ocupado en esa superficie concreta.

## Recursos externos

- `frontend/src/components/markdown-text.tsx` — renderer existente, allow-list ADR-0020, patrón de
  ubicación del componente compartido a replicar.
- `.claude/specs/adr/0020-renderizado-markdown-seguro-con-allow-list.md` — decisión anti-XSS a no
  reabrir.
- `frontend/src/features/tickets/ticket-reply-form.tsx`, `ticket-create-form.tsx`,
  `frontend/src/features/approvals/approval-decision.tsx` — las 3 superficies a tocar.

## Estimación global

- **Tareas totales**: 1 (las 3 superficies se adoptan a la vez con el mismo componente compartido).
- **Esfuerzo estimado**: 1 sesión — incluye la integración `Controller` de RHF (patrón nuevo en el
  repo, `design-review` #3) y el override del preview con `MarkdownText` (`design-review` #1).
- **Recursos**: dependencia nueva `@uiw/react-md-editor` (v4.1.2, MIT, `peerDependencies: react
  >=16.8.0` — verificado, compatible con React 19).

## Registro de cambios del plan

- 2026-09-01: creado — el usuario esperaba un editor enriquecido tras el plan `markdown-rendering` y no
  lo encontró; confirmado leyendo el código, no es un bug, es alcance no incluido en el plan anterior.
- 2026-09-01: refinado con `grilling` (6 preguntas, 6 decisiones):
  1. Librería `@uiw/react-md-editor` — confirmado el recomendado (peer deps verificadas compatibles
     con React 19).
  2. `preview="live"` en las 3 superficies — el owner revirtió mi recomendación de `preview="edit"`
     sin previsualización.
  3. Las 3 superficies a la vez, no por fases — confirmado el recomendado.
  4. Toolbar completo (incluye tabla e imagen) — el owner revirtió mi recomendación de subconjunto
     simple.
  5. Imagen: solo pegar URL externa, NO integración con adjuntos — confirmado el recomendado, tras
     verificar que `GET /messages/{id}/attachments/{id}` exige `Authorization` (no es una URL pública
     que un `<img>` de Markdown pueda usar).
  6. Tooltips/aria-labels traducidos vía `next-intl` — confirmado el recomendado.
- 2026-09-01: revisado con `design-review` (subagente fresco, modelo caído a inherit —
  `models.design-review: claude-opus-4-8` no es un alias válido). 6 hallazgos, ninguno exige rehacer
  el diseño de fondo (componente compartido, librería, alcance de las 3 superficies); los 6
  aceptados sin discrepancia:
  1. **CRÍTICO, corregido**: el plan afirmaba "sin cambio de superficie de riesgo real" pero
     `preview="live"` usa el motor de renderizado propio de la librería, no auditado — reabría
     ADR-0020 sin decirlo. El borrador inicial (fase de exploración) sí decía "la preview debe usar
     `MarkdownText`", pero esa frase se perdió al escribir el plan final para `grilling` — fallo real
     mío, no del subagente. Corregido: preview obligatoriamente sobreescrita con `MarkdownText`.
  2. `checkedListCommand` excluido explícitamente del toolbar (choca con la exclusión de casillas de
     tarea de ADR-0020).
  3. Integración `Controller` de RHF añadida explícitamente al diseño y a la estimación (patrón
     nuevo en el repo).
  4. Theming (`useTheme()` → `data-color-mode`) añadido explícitamente al diseño.
  5. Añadida sección "Consecuencias / riesgos aceptados".
  6. `preview="live"` en las 3 superficies (incluida `ticket-reply-form`, compacta) reafirmado por el
     owner tras la re-pregunta.
- 2026-09-01: escrito ADR-0021 (accepted) y tarea `frontend-markdown-editor-01`; extendidos
  CU-FE-04/05/06 (1 extensión + 2 escenarios base cada uno).
- 2026-09-01: endurecido con `scenario-coverage` (subagente QA fresco). (A) 11 huecos dentro de
  alcance incorporados al Gherkin de las 3 CUs: integración `Controller`→API, descripción/respuesta
  vacía, validación de campo con el editor montado, marcado adversario tecleado a mano, tema
  reactivo en caliente, **regresión real de `useUnsavedGuard(isDirty)`** (riesgo de romper una
  feature existente con `Controller`+toolbar), casilla de tarea tecleada a mano, polling no
  interrumpe una edición activa, toolbar accesible por teclado + tooltips reactivos al locale,
  estado de carga antes de hidratar, y un `Scenario Outline` por cada comando del toolbar. (B)
  ninguno — todo dentro de alcance. Delegadas 2 decisiones al owner, resueltas:
  1. Botón nativo de alternar modo de vista — **excluido** del toolbar (contradiría la consistencia
     de `preview="live"` fijo en las 3 superficies).
  2. Pegar/arrastrar imagen como `data:`/base64 — **se verifica y bloquea explícitamente** en
     implementación si la librería lo hace por defecto (no se acepta como riesgo conocido).

## Criterios de calidad y verificación

- TDD en `MarkdownEditor` y en cada superficie que lo adopte.
- `pnpm lint`/`pnpm typecheck` en verde.
- Gate de mutation testing (Stryker, `break: 80`).
- Manual: escribir con el toolbar en las 3 superficies, confirmar que el texto resultante se renderiza
  correctamente al publicarse/aprobarse contra el backend real.

## Tasks

- [ ] `frontend-markdown-editor-01` (P1) — Componente `MarkdownEditor` y adopción en las 3 superficies  · depends_on: —
