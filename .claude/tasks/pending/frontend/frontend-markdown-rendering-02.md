---
id: frontend-markdown-rendering-02
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

# Renderizar el draft con `MarkdownText` en `ApprovalDecision`

## Description

`frontend/src/features/approvals/approval-decision.tsx:70` muestra `approval.draft_body` en un
`<blockquote>` de texto plano. Esta tarea lo sustituye por `MarkdownText` (tarea `01`), para que el
revisor vea el draft del agente formateado (negrita, listas, tablas...) en vez de Markdown literal.

## Spec

- Reemplazar `<blockquote className="whitespace-pre-wrap border-l-2 pl-3 text-sm">{approval.draft_body}</blockquote>`
  por `<blockquote className="border-l-2 pl-3 text-sm"><MarkdownText>{approval.draft_body}</MarkdownText></blockquote>`
  — quitar `whitespace-pre-wrap` (lo da `MarkdownText`, fijado en la tarea `01`).
- Si `approval.draft_body` está vacío (caso ya resuelto en `fix/frontend/approval-decision-shows-escalation-reason`
  — `hasDraft`/`noDraftGenerated`, verificar si ya está mergeado a la rama base de esta tarea; si no,
  no bloquea esta tarea, el hueco vacío seguiría igual que antes), no se monta `MarkdownText`.

## Fuera de alcance

- Tocar `TicketTimeline` — no renderiza `body`, confirmado; no es una superficie de este plan.
- Cambiar el comportamiento de aprobar/editar/rechazar — solo el renderizado del texto, no la lógica
  de decisión.
- Corregir `stryker.config.json` (tarea `04`, independiente).
- Sanitización de HTML crudo embebido — deliberadamente no soportado (ver tarea `01`).

## Scenarios (Gherkin)

Criterios de aceptación (Gherkin) en el caso de uso:
- [CU-FE-06 — Flujo IA: cola, ciclo de draft y decisiones](../../../specs/frontend/casos-de-uso/CU-FE-06-flujo-ia-cola-draft-decisiones.md)
  — extensiones 3a-3e y los escenarios: "El borrador con Markdown se muestra formateado", "El
  borrador con marcado adversario se muestra inerte", "El borrador truncado a mitad de sintaxis no
  rompe el render", "El enlace de un borrador se abre en pestaña nueva sin arriesgar la sesión", "Un
  borrador vacío o solo con espacios no rompe el render" — verificados aquí montando
  `ApprovalDecision` (test mínimo por superficie, `cross-cutting.md` §1), no solo `MarkdownText` en
  aislamiento.

## Provides

—

## Definition of Done

- [ ] Tests escritos ANTES de la implementación (TDD) — Red → Green → Refactor
- [ ] Cada escenario Gherkin tiene al menos un test (camino feliz + bordes/errores)
- [ ] Todos los tests en verde
- [ ] Spec cumplida
- [ ] Lint / format / typecheck OK (`pnpm lint`, `pnpm typecheck`)
- [ ] Gate de mutation testing superado (Stryker, `pnpm exec stryker run --mutate
      "src/features/approvals/approval-decision.tsx"`, `break: 80`)
- [ ] Gate `sdd-lint` superado — artefactos SDD sin ERROR de formato/completitud (AVISO se reconoce)
- [ ] Gate de `fact-checker` superado — afirmaciones de la sesión verificadas
- [ ] Verificación manual contra el backend real: un draft real del LLM (con negrita/listas) se ve
      formateado en la cola de aprobaciones.
- [ ] Documentación actualizada:
  - [ ] Histórico de la tarea — session log en
        `.claude/context/frontend/frontend-markdown-rendering-02.md`
- [ ] Docs de dev / usuario final + `pnpm changeset` donde aplique (N/A — sin `pnpm changeset` en este repo)
