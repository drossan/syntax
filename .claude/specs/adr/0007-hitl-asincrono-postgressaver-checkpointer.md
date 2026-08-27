# 0007. HITL asíncrono sobre API con checkpointer PostgresSaver (interrupt→resume)

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; `design-review` backend (split tareas 15/16, HITL como núcleo de riesgo).

## Contexto y planteamiento del problema

El producto exige **aprobación humana** de cada draft IA. El agente (LangGraph) debe **pausar**, esperar
una decisión que llega por **API en otro momento** (no en el mismo request), y **reanudar** — sobreviviendo
a reinicios del servidor y a decisiones duplicadas. Es el **núcleo de riesgo** del sistema.

## Decision drivers

- La aprobación es asíncrona: el run se suspende y se reanuda en un request posterior.
- Durabilidad: un reinicio del servidor no debe perder el trabajo del run.
- Idempotencia: una doble decisión (carrera) no debe reanudar el grafo dos veces.

## Opciones consideradas

- **Opción 1** — `interrupt()` dinámico + **`PostgresSaver`** como checkpointer; `thread_id =
  ticket_{id}_run_{n}`; la decisión llega por endpoint `approval.decide` y reanuda con `Command(resume=)`.
- **Opción 2** — Mantener el draft en **memoria del proceso** hasta la aprobación.
- **Opción 3** — `interrupt_before` **compile-time** con checkpointer `SqliteSaver`/`MemorySaver` (patrón
  de las demos de referencia).

## Resultado de la decisión

Elegida: **Opción 1**. El grafo se compila con **`PostgresSaver`**; al `decide.requires_approval=true` el
nodo llama a `interrupt()`, que **persiste el estado completo** en el checkpoint Postgres y **suspende** el
run, creando un `ApprovalTask(pending)` (mapeo 1:1 interrupt↔ApprovalTask). `approval.decide`
(`approved|edited|rejected`) reanuda con `Command(resume=)` sobre el mismo `thread_id`. Como el estado vive
**solo** en Postgres, un proceso nuevo **reanuda desde el último checkpoint**. La transición
`pending→decidida` va bajo bloqueo/optimistic-concurrency: **solo la primera** decisión reanuda; una
segunda recibe **409** (no-op idempotente). Reabrir un ticket lanza un **run nuevo** (`run_seq=n+1`,
thread nuevo); el anterior queda superado.

### Confirmación

`agent-graph.md` §6 (detalle alto: reinicio, doble decisión→409, consistencia ante fallo del LLM);
`app/agents/{checkpointer,hitl,runner}.py` (real, tareas 07/08/09); endpoints `approvals` en
`api-contract` (409 en doble decisión, CAS de `approval_service`, plan `domain-services`).

**Verificación real cerrada** (tarea `backend-agent-graph-09`, integración contra Postgres real, sin
mocks de checkpointer/HITL):
- Aprobación/edición/rechazo reanudan y publican (o no) el mensaje esperado.
- **Reinicio a mitad de run**: un runner/checkpointer construido de cero (simula un proceso nuevo)
  reanuda desde el checkpoint sin re-invocar `classify`/`retrieve`/`grade`/`generate` — verificado con
  espías de llamadas al `ChatModel`/`Retriever`, no asumido.
- **Defensa en profundidad**: reanudar un run ya terminal (thread sin interrupt pendiente) es un no-op
  verificado contra el SDK real (`ainvoke(Command(resume=...))` sobre un grafo terminado devuelve el
  estado final sin re-ejecutar nada) — la garantía primaria de no-doble-resume sigue siendo el CAS de
  `approval_service.decide_if_pending`, no este adaptador.
- **Re-draft tras reopen**: un `AgentRun` superado no interfiere con el run activo del mismo ticket
  (thread_ids distintos, aislamiento ya garantizado por el checkpointer, tarea 07).
- `resume()` sobre un `agent_run_id` inexistente falla con `NotFound`, no una excepción cruda.

## Consecuencias

- **Buenas**: aprobación durable y asíncrona; sobrevive reinicios; idempotente ante carreras.
- **Malas / coste**: acopla el flujo al checkpointer Postgres; el surface exacto de LangGraph
  (`interrupt()`/`Command`) debe **pinarse y verificarse** al compilar el lockfile (deps no instaladas aún).
- **Riesgo confirmado al implementar** (tarea `backend-agent-graph-07`, `design-review` ajuste 10): las
  4 tablas de `checkpoints`/`checkpoint_blobs`/`checkpoint_writes`/`checkpoint_migrations` no tienen API
  pública — su DDL (migración Alembic `0005_agent_checkpoint_tables`) se copió del array `MIGRATIONS`
  interno de `langgraph-checkpoint-postgres` (no-público, strings Python crudos; la librería solo
  documenta `AsyncPostgresSaver.setup()` como el punto de entrada soportado). **En cualquier bump de
  esa dependencia hay que re-verificar a mano** que `MIGRATIONS` no cambió antes de asumir que la
  migración vendida sigue siendo correcta; `syntax_app` (sin `CREATE`) no puede auto-repararse en
  runtime si diverge.

## Pros y contras de las opciones

- **Opción 1**: 👍 durable, idempotente, asíncrono real · 👎 depende de PostgresSaver; surface a pinar.
- **Opción 2**: 👍 trivial · 👎 un reinicio pierde el run; no escala a multi-proceso.
- **Opción 3**: 👍 patrón de las demos · 👎 checkpointer no productivo (Sqlite/memoria); interrupt estático.
