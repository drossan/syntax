---
id: frontend-markdown-rendering-03
package: frontend
plan: markdown-rendering
status: pending
priority: 2
depends_on: [frontend-markdown-rendering-01]
estimate: 1.5h
actual:
issue:
created: 2026-08-31
updated: 2026-08-31
---

# Renderizar el body del mensaje con `MarkdownText` en `TicketThread`

## Description

`frontend/src/features/tickets/ticket-thread.tsx` muestra `message.body` en un `<p>` de texto plano,
para **todos** los mensajes del hilo. Esta tarea lo sustituye por `MarkdownText` (tarea `01`), sin
condicionar a `is_ai_draft` (decisión de `grilling` — un mensaje humano con `**texto**` también se
renderiza en negrita, un solo camino de render).

## Spec

- Reemplazar `<p className="mt-1 whitespace-pre-wrap text-sm">{message.body}</p>` por
  `<div className="mt-1 text-sm"><MarkdownText>{message.body ?? ""}</MarkdownText></div>` — quitar
  `whitespace-pre-wrap` (lo da `MarkdownText`); `div` en vez de `p` porque `MarkdownText` puede
  renderizar bloques (listas, tablas) que un `<p>` no puede contener válidamente.
- **Corrección de tipos (`scenario-coverage`, hallazgo crítico)**: `Message.body` en el schema
  generado (`frontend/src/types/api.ts`) es `body?: string` — **opcional**, no `string` garantizado.
  `MarkdownText` (tarea `01`) declara `children: string`. Sin el `?? ""`, `pnpm typecheck` falla al
  envolver — el `<p>{message.body}</p>` actual no lo sufre porque JSX tolera `undefined` directamente,
  pero `MarkdownText` no.
- Se aplica a **todos** los mensajes del `thread.map(...)`, sin `if (message.is_ai_draft)`.

## Fuera de alcance

- Tocar `TicketTimeline` — no renderiza `body`, confirmado; no es una superficie de este plan.
- Distinguir renderizado por autor (`is_ai_draft`) — decisión de `grilling`: un solo camino para
  todos los mensajes.
- Corregir `stryker.config.json` (tarea `04`, independiente).
- Sanitización de HTML crudo embebido — deliberadamente no soportado (ver tarea `01`).

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-FE-05 — Detalle, visibilidad y mutaciones del ticket](../../../specs/frontend/casos-de-uso/CU-FE-05-detalle-visibilidad-y-mutaciones.md)
  — extensión 1c, RN-3 y los escenarios: "Contenido externo se muestra como texto inerte", "Markdown
  legítimo se renderiza formateado", "El renderizado no distingue autor", "Una imagen embebida no
  filtra en qué ticket está el usuario", "Un mensaje sin cuerpo no rompe el render del hilo", "Un
  mensaje humano con caracteres Markdown casuales se sigue leyendo razonablemente" — verificados aquí
  montando `TicketThread` (test mínimo por superficie, `cross-cutting.md` §1), no solo `MarkdownText`
  en aislamiento.

## Provides

—

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida
- [ ] Lint / format / typecheck OK (`pnpm lint`, `pnpm typecheck`)
- [ ] Gate de mutation testing superado (Stryker, `pnpm exec stryker run --mutate
      "src/features/tickets/ticket-thread.tsx"`, `break: 80`)
- [ ] Gate `sdd-lint` superado — artefactos SDD sin ERROR de formato/completitud (AVISO se reconoce)
- [ ] Gate de `fact-checker` superado — afirmaciones de la sesión verificadas
- [ ] Verificación manual contra el backend real: tras aprobar/auto-resolver un draft real, el
      mensaje se ve formateado en el hilo del ticket.
- [ ] Documentación actualizada:
  - [ ] Histórico de la tarea — session log en
        `.claude/context/frontend/frontend-markdown-rendering-03.md`
- [ ] Docs de dev / usuario final + `pnpm changeset` donde aplique (N/A — sin `pnpm changeset` en este repo)
