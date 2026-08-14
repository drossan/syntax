# Session log — backend-skeleton-foundation-05 (Spec agente LangGraph + HITL + LangSmith)

## 2026-08-13 — Arranque

**Estado:** tarea movida `pending → active` (`status: active`, `updated: 2026-08-13`). `depends_on: 04`
verificado `done`. Doc-only. Núcleo de riesgo → detalle alto. Coherente con 03 (estado↔AgentRun/Ticket/
ApprovalTask) y 04 (confianza/retrieval).

**Verificaciones previas a redactar (esta sesión):**
- `backend/requirements.in` declara el stack LLM: `langchain`, `langgraph`,
  `langgraph-checkpoint-postgres` (PostgresSaver), `langchain-openai`, `langsmith`, `pydantic`/
  `pydantic-settings`, `asyncpg`. **Sin versión pinada** y `requirements.txt` es un **stub** (lockfile no
  compilado) → no puedo citar versiones exactas ni verificar el surface contra un paquete instalado.
- Demos (patrones verificados por grep):
  - `helpdesk_system`: `interrupt_before` + `checkpointer` + `StateGraph` (+ `SqliteSaver` = anti-patrón,
    lo reemplaza PostgresSaver).
  - `multiuser_chat_system`: `add_messages`, `trim_messages`, `StateGraph`, `PydanticOutputParser`,
    `checkpointer` (+ `SqliteSaver`).
  - `soc_multiagent`: `create_react_agent`, `@tool`.
- **Nota de honestidad (NO verificado contra paquete instalado):** la spec objetivo usa las APIs
  **modernas** (`interrupt()` dinámico + `Command(resume=)`, `with_structured_output`), mientras las
  demos usan las **antiguas** (`interrupt_before` compile-time, `PydanticOutputParser`). Ambas son reales
  a mi conocimiento (cutoff Ene-2026), pero el **surface exacto se pina al implementar (15/16)** cuando se
  compile/instale el lockfile. La spec lo marca explícitamente.

## 2026-08-13 — Cierre

**Resumen:** Escrita `.claude/specs/backend/agent-graph.md` (detalle alto): grafo **plano** con edges
condicionales **tipados** (`classify→retrieve→grade→generate→decide→[auto|HITL]→respond`, sin supervisor
por prompt); clasificación `with_structured_output` `{categoria, dominio 1-de-17, prioridad, resoluble}`
que **filtra el retrieval** y fija `ticket.domain/priority`; estado `add_messages`+dominio mapeado 1:1 a
03; `trim_messages`; confianza híbrida (similitud de 04 + grade → umbral → auto/escalado/human_note); y
el **modelo HITL asíncrono a fondo**. Refuerzos cerrados: prompt-injection, no-clasificable→fallback,
idioma de respuesta, `agent_run.failed`, re-draft tras reopen.

**Decisiones técnicas + porqué:**
- **HITL**: `interrupt()` → checkpoint **PostgresSaver** (`thread_id=ticket_{id}_run_{n}`) → endpoint
  `approval.decide` → `Command(resume=)`. **Reinicio a mitad de run**: estado solo en Postgres → proceso
  nuevo re-adjunta el thread y reanuda desde el checkpoint (interrupción durable). **Doble decisión**:
  transición `pending→decidida` bajo bloqueo → solo la 1ª reanuda; la 2ª = 409 (idempotencia de 03).
  Mapeo 1:1 interrupt↔ApprovalTask; `approved`→Message(public) con draft, `edited`→final_body,
  `rejected`→sin mensaje público, AgentRun superado.
- **Grafo plano + edges tipados** (no routing por prompt): el routing lee campos tipados del estado
  (`resoluble`/`suficiente`/`requires_approval`), nunca texto libre.
- **Confianza partida** con 04: 04 aporta similitud; 05 fija umbral (`AGENT_CONFIDENCE_THRESHOLD`) y
  política auto/escalado.
- **Nota al desarrollador / streaming SSE**: fuera (Fase 2 / seam `astream`).

**Verificación (gate `fact-checker`, subagente fresco, sonnet por config):** **8/8 VERIFICADO**, 0
INCORRECTO, 0 NO VERIFICABLE. Cubrió coherencia con 03 (campos AgentRun/ApprovalTask/enums) y 04
(confianza+filtro dominio), `requirements.in` (stack LLM declarado sin pin), `requirements.txt` = stub no
compilado, patrones de las 3 demos (grep), y **C8 (honestidad)**: ninguna afirmación presenta el surface
de LangGraph/LangChain como hecho verificado sin matiz.

**Nota de honestidad (mantenida en la spec):** las deps LLM NO están instaladas/compiladas; las demos
usan variantes antiguas (`interrupt_before`, `PydanticOutputParser`); la spec objetivo usa las modernas
(`interrupt()`, `with_structured_output`) **marcadas como diseño a pinar/verificar en 15/16**.

**Docs actualizadas:** `.claude/specs/backend/agent-graph.md` (nuevo). Plan: `[x]` tarea 05 + Registro.

**Ficheros/commits:** `.claude/specs/backend/agent-graph.md` (nuevo); task 05 pending→active→completed;
session log; plan. (Commit pendiente de que el owner lo pida.)

**Tiempo real:** ~1 h.

**Follow-ups:** 06 (contrato de API) ya tiene sus 4 deps (02/03/04/05) → puede arrancar. 15 implementa la
definición del grafo; 16 el checkpointer+HITL (verificando el surface exacto de la API). 06/12 exponen los
endpoints del flujo-IA (approval.decide con 409 en doble decisión).
