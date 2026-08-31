# CU-BE-05 — Clasificación y retrieval RAG

> **SDD** (Cockburn + Gherkin). CÓMO para FR-023…FR-025, FR-035 de [`../spec.md`](../spec.md). Decisiones:
> [[../../adr/0008-grafo-langgraph-plano-edges-tipados]], [[../../adr/0010-rag-pgvector-chunking-h2-tolerante-estado-peso]],
> [[../../adr/0009-confianza-hibrida-y-auto-approve-por-tenant]],
> [[../../adr/0019-fallback-de-dominio-por-relevancia-baja-en-retrieval]] (extensión 1c). Detalle:
> [`../rag-ingestion.md`](../rag-ingestion.md) §6, [`../agent-graph.md`](../agent-graph.md) §4-§5.
>
> **Alcance de este CU frente al plan `kb-retriever`** (nota añadida 2026-08-25). Este CU cubre el
> retrieval del **agente LangGraph**: chunks con `chunk_id`, **sin deduplicar**, con el `score` **crudo**
> que alimenta la confianza híbrida. El camino de la **persona** que consulta la KB desde el panel
> (documentos paginados, dedup por `uc_id`, `score` ponderado, `snippet`) vive en
> [CU-BE-12](./CU-BE-12-consulta-de-la-kb-desde-el-panel.md) — comparten `app/rag/`, no su forma de
> salida ([ADR-0018](../../adr/0018-retrieval-http-de-la-kb-ventana-dedup-y-peso-de-estado.md)).
>
> De los 5 escenarios de abajo, el plan `kb-retriever` materializa **solo los del retriever**: el **2**
> (fallback sin filtro de dominio) y el **4** (los `draft` participan ponderados). Los escenarios **1**
> (`classify` fija el dominio), **3** (contexto insuficiente escala) y **5** (citas) dependen de nodos
> LLM del grafo que **todavía no existen** → los cierra el plan del **agent-graph**.

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
- **1c.** ([ADR-0019](../../adr/0019-fallback-de-dominio-por-relevancia-baja-en-retrieval.md), plan
  `rag-domain-fallback`, 2026-08-31) Ticket **clasificable** con dominio asignado, pero el dominio es el
  equivocado (frontera de taxonomía ambigua — el mismo concepto vive en varios de los 17 dominios):
  `retrieve` reintenta **siempre** sin filtro de dominio (no solo cuando el score filtrado parece bajo —
  un caso real observado con score 0.611, ya por encima del umbral de confianza, seguía siendo el
  dominio equivocado) y usa ese resultado si mejora significativamente sobre el filtrado (margen
  configurable, `Settings.rag_domain_fallback_margin`). No se mezclan ambas listas de hits. No se
  corrige `ticket.domain`/`ticket.priority` persistidos — solo cambia qué se recupera para responder.
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

  Scenario: El dominio asignado pero equivocado no bloquea el retrieval de la respuesta correcta
    Given un ticket clasificado con un dominio asignado (con confianza) que no es el dominio real del
      documento que responde a la pregunta
    When el agente recupera contexto
    Then reintenta sin filtro de dominio, y si el resultado sin filtro mejora significativamente sobre
      el filtrado, usa ese resultado completo para el resto del run

  Scenario: El dominio asignado y correcto no se sustituye por ruido del resto del corpus
    Given un ticket clasificado con el dominio correcto, cuyo retrieval filtrado ya es suficiente
    When el agente recupera contexto y compara contra la búsqueda sin filtro
    Then la mejora sin filtro no supera el margen configurado y se mantiene el resultado filtrado

  Scenario Outline: El reintento sin filtro se ejecuta siempre que hay dominio asignado, independientemente del score filtrado
    Given un ticket clasificado con dominio asignado y un score máximo filtrado de <score_filtrado>
    When el agente recupera contexto
    Then se ejecuta una segunda búsqueda sin filtro de dominio para poder comparar

    Examples:
      | score_filtrado |
      | 0.384          |
      | 0.611          |
      | 0.66           |

  Scenario: El retrieval filtrado sin resultados no bloquea la comparación con el sin-filtro
    Given un ticket clasificado con un dominio asignado cuya búsqueda filtrada no devuelve ningún hit
    When el agente recupera contexto
    Then la comparación usa 0.0 como score máximo filtrado, sin lanzar error

  Scenario: Ni el retrieval filtrado ni el sin filtro encuentran nada
    Given un ticket clasificado con dominio asignado sin ningún hit en la KB, con o sin filtro
    When el agente recupera contexto
    Then se mantiene el resultado filtrado (vacío) y no se lanza ningún error

  Scenario Outline: El margen de mejora configurado, no un valor fijo, decide si el fallback se usa
    Given un ticket clasificado con dominio asignado y una mejora sin filtro de <delta>, con el margen
      de mejora configurado a <margen>
    When el agente recupera contexto
    Then el resultado usado es <resultado>

    Examples:
      | delta | margen | resultado  |
      | 0.10  | 0.05   | sin filtro |
      | 0.10  | 0.20   | filtrado   |
      | 0.125 | 0.125  | filtrado   |

  Scenario: Un fallo en la segunda búsqueda (sin filtro) no se enmascara con el resultado filtrado
    Given un ticket clasificado con dominio asignado cuya búsqueda filtrada tiene éxito
    And la segunda búsqueda sin filtro de dominio falla (proveedor caído)
    When el agente recupera contexto
    Then el fallo se propaga y el run no continúa con un resultado silenciosamente incompleto

  Scenario: El vector de la consulta se reutiliza entre la búsqueda filtrada y la sin filtro
    Given un ticket clasificado con un dominio asignado
    When el agente recupera contexto y se ejecuta el reintento sin filtro
    Then la consulta se embebe una única vez y ambas búsquedas usan ese mismo vector

  Scenario: Sin dominio asignado no se ejecuta una segunda búsqueda
    Given un ticket cuyo dominio no puede determinarse con confianza
    When el agente recupera contexto
    Then se ejecuta una única búsqueda (sin filtro), sin comparación ni reintento adicional

  Scenario: Toda comparación con dominio asignado se registra, dispare o no el fallback
    Given un ticket clasificado con dominio asignado
    When el agente recupera contexto y compara filtrado contra sin filtro
    Then se registra un log con el ticket, el dominio original, ambos scores máximos y si se usó el fallback
    And esto ocurre igual si el margen se supera que si no
```
