---
id: frontend-markdown-rendering-01
package: frontend
plan: markdown-rendering
status: active
priority: 1
depends_on: []
estimate: 3h
actual:
issue:
created: 2026-08-31
updated: 2026-08-31
---

# Componente compartido `MarkdownText` con allow-list y garantía anti-XSS

## Description

Ni `ApprovalDecision` ni `TicketThread` renderizan Markdown hoy — muestran el texto literal. Esta
tarea crea el componente compartido que ambos reusarán (tareas `02`/`03`): envuelve `react-markdown`
con un allow-list explícito de elementos, sin `rehype-raw` (el Markdown fuente nunca se interpreta
como HTML — la garantía anti-XSS central), y con las mitigaciones fijadas en `grilling`/
`design-review` del plan (`.claude/plans/pending/frontend/markdown-rendering.md`, Registro de
cambios). Ver [ADR-0020](../../../specs/adr/0020-renderizado-markdown-seguro-con-allow-list.md) para
el razonamiento completo de la decisión.

## Spec

- `pnpm add react-markdown remark-gfm --filter frontend`.
- `frontend/src/components/markdown-text.tsx` — exporta `MarkdownText({ children }: { children: string
  })`, envuelve `<ReactMarkdown remarkPlugins={[remarkGfm]}>`.
- `allowedElements`: `p`, `strong`, `em`, `del`, `h1`-`h6`, `ul`, `ol`, `li`, `a`, `img`, `code`,
  `pre`, `blockquote`, `table`, `thead`, `tbody`, `tr`, `th`, `td`, `hr`, `br`. `unwrapDisallowed:
  true`. **No** incluir las casillas de lista-de-tareas de GFM (se desenvuelven a texto plano,
  `scenario-coverage`: sin decisión explícita antes, `hr` sí entra — con `unwrapDisallowed` un `hr`
  no tiene texto que conservar y desaparecería en silencio si se excluyera).
- Componentes custom vía la prop `components`:
  - `h1`-`h6` → peso visual moderado (`text-base font-semibold`, no tamaños de portada).
  - `img` → `referrerPolicy="no-referrer"` + `loading="lazy"`, preservando `alt`.
  - `a` → `target="_blank" rel="noopener noreferrer"` (`scenario-coverage` — evita *reverse
    tabnabbing*, no arriesga la sesión SPA cuyo access-token vive en memoria, FR-003).
  - `table`/`th`/`td` → estilos básicos de borde/padding (no rota visualmente).
  - `hr` → línea fina (`border-t`), sin peso visual excesivo dentro de una card.
- **Sin** `whitespace-pre-wrap` en el componente ni en su contenedor — los saltos de párrafo/lista los
  da el HTML real que genera `react-markdown`.
- `React.memo(MarkdownText)` como export — mitigación preventiva sin evidencia de necesidad (decisión
  del owner, `design-review`).
- **No** pasar `urlTransform` propio — se confía en `defaultUrlTransform` de `react-markdown`
  (verificado en `grilling`: sanea `href`/`src` por defecto, incluye `javascript:`).

## Fuera de alcance

- Tocar `TicketTimeline` — no renderiza `body`, confirmado; no es una superficie de este plan.
- Sanitización de HTML crudo embebido vía `rehype-raw`/`dompurify` — deliberadamente no soportado.
- Casillas de lista-de-tareas de GFM en el allow-list.
- Markdown en cualquier otro campo de texto libre del producto (asunto de ticket, notas internas,
  nombres).
- Corregir `stryker.config.json` (tarea `04`, independiente).
- Wiring en `ApprovalDecision`/`TicketThread` (tareas `02`/`03`).

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en los casos de uso:
- [CU-FE-05 — Detalle, visibilidad y mutaciones del ticket](../../../specs/frontend/casos-de-uso/CU-FE-05-detalle-visibilidad-y-mutaciones.md)
  — extensión 1c y los escenarios: "Contenido externo se muestra como texto inerte", "Markdown
  legítimo se renderiza formateado", "Una imagen embebida no filtra en qué ticket está el usuario".
- [CU-FE-06 — Flujo IA: cola, ciclo de draft y decisiones](../../../specs/frontend/casos-de-uso/CU-FE-06-flujo-ia-cola-draft-decisiones.md)
  — extensiones 3a-3e y los escenarios: "El borrador con Markdown se muestra formateado", "El
  borrador con marcado adversario se muestra inerte", "El borrador truncado a mitad de sintaxis no
  rompe el render", el `Scenario Outline` de elementos Markdown (código, cita, listas, tabla, `hr`,
  autolink, casilla de tarea), "El enlace de un borrador se abre en pestaña nueva sin arriesgar la
  sesión", "Un enlace o imagen con protocolo peligroso queda neutralizado", "El texto alternativo de
  una imagen se conserva", "Un borrador vacío o solo con espacios no rompe el render", "El formato
  real de las fuentes se renderiza como lista".

Estos escenarios se verifican aquí a nivel del componente `MarkdownText` en aislamiento (sin montar
`ApprovalDecision`/`TicketThread` todavía — eso lo hacen las tareas `02`/`03` sobre sus propias
superficies, per `cross-cutting.md` §1 "test mínimo por superficie").

## Provides

- `frontend/src/components/markdown-text.tsx` — `MarkdownText`, componente memoizado, listo para
  envolver cualquier texto Markdown de origen no confiable con la garantía anti-XSS ya resuelta.
  Tareas `02`/`03` lo consumen directamente.

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores) — incl. negrita,
      lista ordenada Y no ordenada, tabla, encabezado, tachado, código inline/bloque, cita, `hr`,
      autolink, casilla de tarea GFM (se desenvuelve a texto plano), imagen (con
      `referrerPolicy`/`loading`/`alt` preservado), enlace (`target`/`rel`), enlace/imagen con
      `javascript:` neutralizado, el caso adversario del script/HTML embebido, Markdown truncado a
      mitad de sintaxis, `children` vacío/solo-espacios, y el formato exacto de `_finalize_draft`
      ("Fuentes:\n- [UC-ID] título (tipo)") end-to-end
- [ ] Todos los tests en verde
- [ ] Spec cumplida; lo declarado en `Provides` queda disponible para las tareas `02`/`03`
- [ ] Lint / format / typecheck OK (`pnpm lint`, `pnpm typecheck`)
- [ ] Gate de mutation testing superado (Stryker, `pnpm exec stryker run --mutate
      "src/components/markdown-text.tsx"`, `break: 80`)
- [ ] Gate `sdd-lint` superado — artefactos SDD sin ERROR de formato/completitud (AVISO se reconoce)
- [ ] Gate de `fact-checker` superado — afirmaciones de la sesión verificadas
- [ ] Documentación actualizada:
  - [ ] TSDoc en `MarkdownText` y su allow-list
  - [ ] Histórico de la tarea — session log en
        `.claude/context/frontend/frontend-markdown-rendering-01.md`
- [ ] Docs de dev / usuario final + `pnpm changeset` donde aplique (N/A — sin `pnpm changeset` en este repo)
