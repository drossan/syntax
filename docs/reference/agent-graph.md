# Referencia · Agente + HITL

**Fuente canónica:** `.claude/specs/backend/agent-graph.md`. Implementación: `app/agents/` (definición del
grafo + checkpointer/HITL) y `app/rag/` (retrieval/confianza).

## Grafo (plano, edges condicionales tipados)

```
classify → retrieve → grade → generate → decide → [auto | HITL] → respond
```

- **Plano, sin supervisor por prompt**: el routing lee **campos tipados** del estado
  (`classification.resoluble`, `grade.suficiente`, `decide.requires_approval`), nunca texto libre.
- **`classify`** con `with_structured_output` → `{categoria, dominio (1-de-17), prioridad, resoluble}`;
  el `dominio` **filtra el retrieval** (fallback sin filtro si no clasificable).
- **Estado** (`HelpdeskState`): `add_messages` + `tenant_id/ticket_id/classification/retrieved/confidence/
  requires_approval/draft_response/human_note`. `trim_messages` acota el historial.

## HITL asíncrono (núcleo de riesgo)

```
interrupt → checkpoint Postgres (thread_id=ticket_{id}_run_{n}) → endpoint approvals → Command(resume)
```

- **Checkpointer Postgres** (`PostgresSaver`): el estado vive solo en el checkpoint → **reanudar tras
  reinicio** del servidor.
- **Decisión**: `approve` → `Message(public)` con el borrador; `edit` → con `final_body`; `reject` → sin
  mensaje público. Al reanudar: transición del ticket + `ApprovalTask`/`AgentRun`.
- **Doble decisión** → **409 idempotente** (el grafo se reanuda una sola vez; bloqueo/optimistic).
- **Mapeo 1:1** `interrupt ↔ ApprovalTask`. `auto_approve=false` por defecto (por tenant).

## Refuerzos

- **Prompt-injection**: el ticket es input no confiable → aislado del system-prompt; no ejecutar
  instrucciones embebidas; riesgo máximo con `auto_approve=true`.
- **Idioma**: responder en el idioma del ticket (KB en español).
- **Fallo del LLM** → `AgentRun.failed` + error controlado; checkpoint consistente.
- **Observabilidad**: tracing LangSmith (`langsmith_trace_url` en `AgentRun`); seam `astream` (streaming
  SSE diferido — Fase 1 es request/polling).

## Conformidad de API

Las deps LangGraph/LangChain aún no están instaladas (`requirements.txt` es un stub). El surface objetivo
(`interrupt()`, `with_structured_output`, `PostgresSaver`, `add_messages`, `trim_messages`, `@tool`) se
**pina y verifica al implementar**.
