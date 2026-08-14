# CU-BE-05 — Clasificación y retrieval RAG

> **SDD** (Cockburn + Gherkin). CÓMO para FR-023…FR-025, FR-035 de [`../spec.md`](../spec.md). Decisiones:
> [[../../adr/0008-grafo-langgraph-plano-edges-tipados]], [[../../adr/0010-rag-pgvector-chunking-h2-tolerante-estado-peso]],
> [[../../adr/0009-confianza-hibrida-y-auto-approve-por-tenant]]. Detalle: [`../rag-ingestion.md`](../rag-ingestion.md) §6,
> [`../agent-graph.md`](../agent-graph.md) §4-§5.

- **Ámbito**: backend (nodos `classify`/`retrieve`/`grade` del grafo + retriever RAG)
- **Nivel**: subfunción (dentro del run del agente, [CU-BE-06](./CU-BE-06-draft-ia-y-aprobacion-hitl.md))
- **Actor primario**: agente LangGraph (en nombre del ticket)
- **Interesados e intereses**:
  - Soporte — respuestas fundamentadas en la KB correcta, con citas.
  - Plataforma — no forzar un dominio equivocado; no inventar cuando falta contexto.

## Precondiciones

- La KB está ingerida en pgvector ([CU-BE-07](./CU-BE-07-ingestion-de-la-kb.md)).

## Garantía mínima

- Si no hay contexto suficiente, no se genera una respuesta inventada: se marca insuficiente.

## Garantía de éxito (postcondición)

- El ticket queda clasificado (`domain`/`priority`); hay un conjunto de chunks recuperados con citas y una
  señal de confianza híbrida.

## Disparador

- Arranca un `agent_run` para un ticket.

## Escenario principal (éxito)

1. `classify` produce `{categoria, dominio(1-de-17), prioridad, resoluble}` con structured output.
2. El **dominio filtra** el retrieval; `retrieve` busca por similitud coseno top-k con el peso de `estado`.
3. `grade` evalúa relevancia/suficiencia; la confianza híbrida combina similitud + grade.
4. La confianza queda `≥ umbral` → candidato a draft, con citas (`uc_id/title/section_type/source_url`).

## Extensiones (flujos alternativos y de error)

- **1a.** Ticket **no clasificable** con confianza: `retrieve` opera **sin filtro de dominio** (fallback) y se marca baja confianza.
- **1b.** `resoluble=false`: se escala directo a humano sin `generate`.
- **3a.** Confianza `< umbral` o `grade.suficiente=false`: se **escala** con `human_note` (contexto insuficiente).
- **2a.** El corpus es 81% `draft`: el peso de `estado` es re-ranking, **no** filtro duro (no vacía el retrieval).

## Reglas de negocio

- **RN-1** — El routing entre nodos lee **campos tipados** del estado, nunca texto libre del LLM.
- **RN-2** — Filtrar por `estado` (solo `active`) es **opt-in** por consulta, no el comportamiento base.
- **RN-3** — Toda respuesta cita sus fuentes; las citas se persisten en `agent_run.sources`.

## Criterios de aceptación (Gherkin)

```gherkin
Feature: Clasificación y retrieval RAG

  Scenario: Clasificación fija el dominio y filtra el retrieval
    Given un ticket con contenido de un dominio reconocible
    When el agente clasifica el ticket
    Then obtiene un dominio de los 17 y el retrieval se restringe a ese dominio

  Scenario: Ticket no clasificable usa fallback sin filtro de dominio
    Given un ticket cuyo dominio no puede determinarse con confianza
    When el agente recupera contexto
    Then la búsqueda se hace sin filtro de dominio y se marca baja confianza de clasificación

  Scenario: Contexto insuficiente escala en vez de inventar
    Given un conjunto recuperado que el grade juzga insuficiente
    When el agente evalúa la confianza
    Then el caso se escala con una nota al humano y no se genera una respuesta inventada

  Scenario: El retrieval no se vacía por el predominio de borradores
    Given una KB donde la mayoría de documentos está en estado draft
    When el agente recupera contexto relevante
    Then los documentos draft participan del resultado ponderados, no excluidos

  Scenario: La respuesta cita sus fuentes
    Given un conjunto recuperado con confianza suficiente
    When el agente prepara el borrador
    Then el resultado incluye citas con uc_id, título y tipo de sección
```
