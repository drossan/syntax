# Spec — Agente LangGraph + HITL asíncrono + LangSmith

> Fuente de verdad del diseño del agente de Syntax. Es el **núcleo de riesgo** del producto
> (aprobación humana asíncrona sobre API), así que va con **detalle alto**. La implementan **15**
> (definición del grafo) y **16** (checkpointer + HITL); **06/12** exponen los endpoints del flujo-IA.
> Aterriza en las entidades de **03** (`AgentRun`/`Ticket`/`ApprovalTask`/`Message`) y consume el
> contrato de retrieval/confianza de **04**. **Este fichero es la spec, no el código.**
>
> **SDD** — Doc de **referencia** de la capa SDD. Requisitos en [`spec.md`](./spec.md); decisiones en
> [ADR-0007](../adr/0007-hitl-asincrono-postgressaver-checkpointer.md),
> [ADR-0008](../adr/0008-grafo-langgraph-plano-edges-tipados.md),
> [ADR-0009](../adr/0009-confianza-hibrida-y-auto-approve-por-tenant.md) y
> [ADR-0019](../adr/0019-fallback-de-dominio-por-relevancia-baja-en-retrieval.md) (§4, fallback de
> dominio); flujos en
> [CU-BE-05](./casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md) y
> [CU-BE-06](./casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md).
>
> **Nota de conformidad de API (leer antes de implementar).** Este spec fija el **diseño**, no pina el
> surface exacto de LangGraph/LangChain: el `requirements.txt` es un stub (lockfile sin compilar) y las
> deps (`langgraph`, `langgraph-checkpoint-postgres`, `langchain`, `langchain-openai`, `langsmith`, todas
> en `requirements.in` sin versión) **no están instaladas**. Las demos de referencia usan variantes
> **antiguas** (`interrupt_before` compile-time; `PydanticOutputParser`); aquí el objetivo son las
> **modernas** (`interrupt()` dinámico + `Command(resume=…)`; `with_structured_output`). 15/16 **deben
> pinar y verificar** el nombre/firma exactos contra el paquete instalado al compilar el lockfile.

## 1. Patrones adoptados / anti-patrones descartados

- **Adoptado** (de las demos, verificado por grep): grafo `StateGraph` con `checkpointer`; estado con
  `add_messages`; `trim_messages` para hilos largos; HITL por interrupción + checkpointer; extracción
  estructurada (Pydantic); tools tipadas `@tool`.
- **Descartado**: `SqliteSaver`/`MemorySaver` (→ **PostgresSaver**); singleton global de chatbot;
  Streamlit/filesystem por usuario; routing por prompt (supervisor en prosa); `create_react_agent` como
  única pieza sin edges tipados; clasificación por parseo de strings.

## 2. Grafo — plano, edges condicionales **tipados** (NO supervisor por prompt)

```
        ┌─────────┐
        │ classify│  with_structured_output → {categoria, dominio(1-17), prioridad, resoluble}
        └────┬────┘
             │ (dominio filtra el retrieval)
        ┌────▼────┐
        │ retrieve│  pgvector coseno top-k, filtros domain/package/estado (04)
        └────┬────┘
        ┌────▼────┐
        │  grade  │  relevancia + suficiencia del contexto (LLM)
        └────┬────┘
   insuficiente │ suficiente
     ┌──────────┴───────────┐
     ▼                      ▼
 (human_note)          ┌─────────┐
 draft = escalado      │ generate│  redacta draft_response (idioma del ticket)
     │                 └────┬────┘
     └────────┬─────────────┘
        ┌─────▼─────┐
        │  decide   │  requires_approval? (auto_approve=false OR confianza baja OR escalado)
        └─────┬─────┘
    sí (HITL) │        │ no (auto)
        ┌─────▼─────┐  │
        │ interrupt │  │  ← checkpoint Postgres; crea ApprovalTask(pending)
        └─────┬─────┘  │
   Command(resume)│    │
        ┌─────▼────────▼─────┐
        │      respond        │  emite Message(public) (o nada si rejected)
        └─────────────────────┘
```

- El **routing** entre nodos son **edges condicionales** que leen campos **tipados** del estado
  (`classification.resoluble`, `grade.suficiente`, `decide.requires_approval`), nunca texto libre del LLM.
- El grafo es **plano** (sin sub-supervisor que decida por prompt).

## 3. Estado del grafo

Estado tipado (`TypedDict`/Pydantic) con reducer `add_messages` en `messages`:

| Campo | Tipo | Persiste en (03) |
|---|---|---|
| `messages` | `Annotated[list, add_messages]` | (checkpoint) |
| `tenant_id` | UUID | `agent_run.tenant_id` |
| `ticket_id` | UUID | `agent_run.ticket_id` |
| `classification` | `{categoria, dominio, prioridad, resoluble}` | `ticket.domain`/`ticket.priority` |
| `retrieved` | `list[{uc_id, chunk_id, section_type, title, source_url, score}]` | `agent_run.sources` |
| `confidence` | float 0–1 | `agent_run.confidence` |
| `requires_approval` | bool | (deriva `approval_task`) |
| `draft_response` | str | `approval_task.draft_body` |
| `human_note` | str \| null | `approval_task.human_note` |

- **`trim_messages`** acota la ventana de contexto en hilos largos (reopen acumulan mensajes) antes de
  invocar el LLM; no altera la persistencia del histórico (el `Message` real vive en 03, no en el estado).
- Los campos del estado **coinciden** con `AgentRun`/`Ticket`/`ApprovalTask` de 03 (DoD de esta tarea).

## 4. Clasificación (structured output, no parseo de strings)

- Nodo `classify` con **`with_structured_output`** sobre un modelo Pydantic:
  `Classification{ categoria: str, dominio: KBDomain(1-de-17), prioridad: TicketPriority, resoluble: bool }`.
- **`dominio` filtra el retrieval** (recuperar solo de ese dominio; opción de incluir vecinos vía grafo
  `Relacionado:` de 04). Fija `ticket.domain` y `ticket.priority` (03).
- `resoluble=false` → el ticket no es auto-resoluble por KB (escala directo a humano, sin generate).
- **Ticket no clasificable con confianza** (dominio incierto) → **fallback**: retrieval **sin filtro de
  dominio** (no forzar uno equivocado); se marca baja confianza de clasificación (§Refuerzos).
- **Dominio asignado pero equivocado** (ADR-0019, plan `rag-domain-fallback`, CU-BE-05 extensión 1c): a diferencia
  del caso anterior, aquí SÍ hay un dominio con aparente confianza, pero el documento que responde a la
  pregunta vive en otro de los 17 (frontera de taxonomía ambigua — verificado con casos reales donde el
  score filtrado ya superaba el umbral de confianza y aun así era el dominio equivocado). `retrieve`
  reintenta **siempre** sin filtro cuando hay dominio asignado, y usa ese resultado si mejora
  significativamente sobre el filtrado (`Settings.rag_domain_fallback_margin`, sin mezclar ambas
  listas). No corrige `ticket.domain`/`ticket.priority` persistidos.

## 5. Confianza híbrida (consume 04)

- Señal = **similitud** de los chunks recuperados (score coseno normalizado + re-ranking `estado`, 04) +
  **`grade`** del LLM (relevancia + suficiencia). Este spec fija cómo se combinan y el **umbral**
  (`AGENT_CONFIDENCE_THRESHOLD`, config); 04 aportó la similitud, aquí se fija la política.
- **≥ umbral** → candidato a auto (aún sujeto a `auto_approve`). **< umbral** o `grade.suficiente=false`
  → **escalado** con `human_note` explicando el hueco (contexto insuficiente), sin inventar respuesta.
- `confidence` se persiste en `agent_run.confidence`; `escalated` en `agent_run.escalated` (03).

## 6. HITL asíncrono (detalle — núcleo de riesgo)

**Modelo `interrupt → checkpoint Postgres → endpoint de aprobación → resume`:**

1. **Compilación**: el grafo se compila con **`PostgresSaver`** (`langgraph-checkpoint-postgres`) como
   checkpointer. `thread_id` = **`agent_run.langgraph_thread_id`** = `ticket_{id}_run_{n}` (03 §4.2).
2. **Interrupción**: cuando `decide.requires_approval=true`, el nodo llama a **`interrupt()`** antes de
   `respond`. Esto **persiste el estado completo** en el checkpoint Postgres y **suspende** el run. En ese
   momento se crea/actualiza un **`ApprovalTask(status=pending)`** ligado a `agent_run_id` (mapeo 1:1
   interrupt↔ApprovalTask), con `draft_body = draft_response`.
3. **Decisión (API, 06/12)**: `approval.decide` recibe `{decision: approved|edited|rejected, final_body?,
   human_note?}` y **reanuda** el grafo con **`Command(resume=<decision>)`** sobre el mismo `thread_id`.
   - `approved` → `respond` emite **`Message(public)`** con `draft_body`.
   - `edited` → `respond` emite `Message(public)` con `final_body` (se guarda en `approval_task.final_body`).
   - `rejected` → `respond` **no emite** mensaje público; el run termina, el humano gestiona; el
     `AgentRun` queda cerrado (superado). `human_note` se conserva.
4. **Transición**: al reanudar, `approval_task` pasa `pending → approved|edited|rejected` y `agent_run`
   → `succeeded` (o el estado que corresponda). El ticket transiciona según 06 (p.ej. `open`/`pending`).

**Reinicio del servidor a mitad de run.** El estado vive **solo** en el checkpoint Postgres (no en
memoria): un proceso nuevo re-adjunta el `thread_id` y **reanuda desde el último checkpoint** al llegar el
`Command(resume=)`. La interrupción es **durable**; no se pierde trabajo ni se re-ejecutan nodos ya
completados (el checkpointer es el punto de reanudación).

**Ediciones concurrentes / doble decisión.** El `thread_id` es el **punto de serialización** del run.
- **Doble `approval.decide`** sobre la misma `ApprovalTask`: decidir una tarea ya no-`pending` es
  **no-op idempotente** (03 §4.2). En carrera, **solo la primera** decisión transiciona `pending→decidida`
  y reanuda el grafo; la segunda recibe **409 Conflict** (06) y **no** reanuda el run por segunda vez.
- La transición `pending→decidida` se hace bajo bloqueo/optimistic-concurrency para que `Command(resume=)`
  se aplique **una sola vez** al thread.

**Consistencia ante fallo del LLM.** Si un nodo (p.ej. `generate`) falla, el run va a
**`agent_run.status=failed`** con `agent_run.error`; el checkpoint queda **consistente** (estado parcial
persistido, sin `ApprovalTask` si no se llegó a `interrupt`); el usuario recibe un **error controlado**.

**Re-draft tras reopen (A1.2).** Reabrir un ticket lanza un **run nuevo** con `run_seq=n+1` y
`thread_id=ticket_{id}_run_{n+1}`; el `AgentRun` anterior queda **superado** (no se re-usa su checkpoint).

## 7. Fases y configuración

- **`auto_approve=false` por defecto, por tenant**: en Fase 1 todo draft pasa por HITL salvo que un tenant
  active auto. **`auto_approve=true` eleva el riesgo** de prompt-injection (§8) → documentado.
- **Fase 2 fuera**: nota al desarrollador / KB de código / visibilidad `developer` — diferidas por
  completo (03 §11, 02 §6).

## 8. Tools, settings, seguridad de input

- **Tools tipadas** (`@tool` con args tipados) **solo si un nodo las requiere**; **toolset acotado por
  tenant** (mínimo privilegio: una tool no ve datos de otro tenant; el aislamiento sigue app-level+RLS de
  03/02).
- **Settings inyectables** (`pydantic-settings` `BaseSettings`): **sin** validar config ni crear
  credenciales/clientes en el **import** (sin efectos de importación) — se inyectan en el arranque (07).
- **Prompt injection** (refuerzo): el contenido del ticket es **input no confiable** →
  - se pasa en un **turno de usuario delimitado**, **aislado** del system-prompt; **no** se ejecutan
    instrucciones embebidas ("ignora lo anterior…");
  - **límites de salida** (longitud, formato) y validación del draft;
  - con `auto_approve=true` el riesgo es máximo (nadie revisa) → recomendación: mantener HITL para tenants
    sensibles.

## 9. Observabilidad (LangSmith) y streaming

- **Tracing** de todo el grafo con LangSmith; la URL de la traza se guarda en
  **`agent_run.langsmith_trace_url`** (03 §4.2) para depurar cada run.
- **Implementado en versión mínima y explícitamente parcial** (`backend-agent-graph-11`):
  `LangGraphAgentRunner` envuelve cada `ainvoke()` (`trigger`/`resume`) en `tracing_v2_enabled`
  (`langchain_core.tracers.context`) cuando `settings.langsmith_tracing` y `langsmith_api_key` están
  configurados, y puebla `agent_run.langsmith_trace_url` con `tracer.get_run_url()`. Un fallo del
  cliente LangSmith (red, cuota) nunca tumba el run — best-effort. **Follow-up explícito pendiente**:
  `trigger()` y `resume()` son dos invocaciones `ainvoke()` separadas (procesos distintos, posible
  reinicio entre medias) — cada una genera su propio run raíz de LangSmith SIN enlace de `trace_id`
  verificado entre ambas contra el SDK instalado (`langsmith==0.11.0`); `resume()` por eso **preserva**
  la URL de `trigger()` en vez de sobrescribirla (más completa: cubre todo el trabajo hasta el
  interrupt), pero esa URL **no** enlaza automáticamente a lo ejecutado en `resume()` — dashboards,
  alerting e instrumentación fina por nodo, y una posible reconciliación real del `trace_id` entre
  `trigger`/`resume`, quedan fuera de esta iteración.
- **Idioma de respuesta** (refuerzo): responder en el **idioma del ticket** (detección del texto o locale
  de tenant/usuario). La **KB está en español**: el retrieval opera en español y la generación traduce al
  idioma del ticket si difiere.
- **Seam `astream`**: el grafo se diseña para permitir `astream` (streaming token-a-token del draft) en
  una **fase posterior**; en Fase 1 el draft se entrega por request/polling (streaming SSE **fuera de
  alcance**, plan).

## 10. Refuerzos (scenario-coverage) — checklist

- **Prompt injection** → §8 (input no confiable aislado; sin ejecutar instrucciones; riesgo con auto).
- **Ticket no clasificable** → §4 (fallback: retrieval sin filtro de dominio; no forzar dominio).
- **Idioma de respuesta** → §9 (idioma del ticket; KB en español).
- **Fallo del LLM a mitad de run** → §6 (`agent_run.failed` + error controlado; checkpoint consistente).
- **Re-draft tras reopen** → §6 (run nuevo `run_seq=n+1`, thread nuevo, AgentRun previo superado; A1.2).

## 11. Fuera de alcance

- Implementar el grafo (**15**) ni el checkpointer/HITL (**16**): aquí solo la spec.
- Nota al desarrollador / KB de código (**Fase 2**); **streaming SSE** del draft (seam, no Fase 1).
- Pinar versiones exactas del stack LangGraph/LangChain: lo hace la compilación del lockfile (01/09) y
  15/16 verifican el surface (ver Nota de conformidad arriba).
