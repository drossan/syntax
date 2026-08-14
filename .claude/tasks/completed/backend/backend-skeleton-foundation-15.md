---
id: backend-skeleton-foundation-15
package: backend
plan: skeleton-foundation
status: done
priority: 3
depends_on: [backend-skeleton-foundation-05, backend-skeleton-foundation-09, backend-skeleton-foundation-14]
estimate: 3h
actual: 0.6h
issue:
created: 2026-08-11
updated: 2026-08-13
---

# Skeleton grafo de agentes — definición

## Description

Esqueleto de `app/agents/` (definición del grafo): estado, nodos y edges tipados según spec 05, SIN el
checkpointer/HITL (eso es 16). Recoge el patrón multi-nodo de las demos. Solo esqueleto + guión.

## Spec

- `app/agents/state.py` — `HelpdeskState` (`add_messages` + `tenant_id/ticket_id/classification/retrieved/
  confidence/requires_approval/draft_response/human_note`).
- `app/agents/nodes/` — `classify.py` (structured output → `{categoria, dominio 1-de-17, prioridad,
  resoluble}`), `retrieve.py` (usa retriever 14, filtra por dominio), `grade.py` (relevancia/suficiencia),
  `generate.py` (respuesta fiel al contexto + citas), `decide.py` (auto vs escalado por confianza híbrida),
  `trim.py` (`trim_messages`).
- `app/agents/graph.py` — construye el `StateGraph` **plano con edges condicionales tipados** (no supervisor
  por prompt); expone `build_graph()` (sin compilar con checkpointer todavía).
- `app/agents/tools.py` — tools tipadas (`@tool`) con toolset acotado por tenant, si se usan.

## Refuerzos (scenario-coverage)

- **Aislamiento anti prompt-injection** en `classify`/`generate` (contenido del ticket = dato no confiable).
- **Fallback no-clasificable**: baja confianza de clasificación → retrieval sin filtro de dominio.
- **Idioma de respuesta** según el ticket/locale; retrieval **0/1 resultados** → ruta a "insuficiente → nota al humano".

## Fuera de alcance

- Checkpointer Postgres + HITL interrupt/resume → tarea 16. Streaming SSE (seam). Nota al desarrollador (Fase 2). Implementar lógica.

## Scenarios (Gherkin)

<!-- Doc-only. -->
**Verificación (doc-only):**
- El estado incluye `add_messages` + los campos de dominio de 05; los nodos existen (classify/retrieve/grade/generate/decide/trim).
- El grafo es plano con edges tipados; la clasificación es structured-output y filtra el retrieval por dominio.
- No hay routing por prompt ni parseo de strings de clasificación.

## Provides

- `app/agents/{state,graph,nodes/*,tools}.py` con `build_graph()`. 16 le añade checkpointer+HITL; 12 lo dispara vía `ai-draft`.

## Definition of Done

- [x] Estado (`HelpdeskState` add_messages + campos 05) + 6 nodos + grafo plano (`build_graph`) + tools creados con guión, según 05. `compileall` OK.
- [x] Clasificación structured-output que filtra retrieval; edges condicionales tipados; sin routing por prompt; fallback no-clasificable; anti prompt-injection en classify/generate.
- [x] `Provides` disponible para las dependientes (16 añade checkpointer+HITL; 12 dispara vía ai-draft).
- [x] Gate de `fact-checker` superado (sonnet): 8/8 VERIFICADO (M7 matiz: añadida cautela de conformidad a classify.py).
- [x] Histórico en `.claude/context/backend/backend-skeleton-foundation-15.md`.
