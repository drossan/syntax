---
id: backend-agent-graph
package: backend
status: active
branch: plan/backend/agent-graph
created: 2026-08-27
updated: 2026-08-27
---

# Agente LangGraph + HITL asíncrono (classify→retrieve→grade→generate→decide→interrupt→respond)

## Contexto y problema

El backend de Syntax ya tiene, mergeado en `main`, todo lo que rodea al grafo pero no el grafo en sí:

- `app/rag/{retriever,reranker,dedup}.py` — retriever RAG real (plan `kb-retriever`, PR #10).
- `app/domain/services/{classification,agent_service,approval_service}.py` — servicios de dominio
  **reales**, ya con tests (plan `domain-services`).
- `app/domain/ports/{llm,agent_runner,repositories}.py` — puertos reales; `ChatModel` hoy solo declara
  `classify` (a propósito: sin caller para `generate`/`grade` hasta este plan).
- Routers HTTP `POST /tickets/{id}/ai-draft`, `GET /agent-runs/{id}`, `/approvals/*` — **ya funcionan**
  contra `StubAgentRunner` (`app/infra/agent_runner/stub.py`), que crea el `AgentRun` pero no ejecuta
  ningún nodo.
- `app/agents/` y las partes de LLM de `app/infra/llm/` (`OpenAIChatModel`, `structured.py`) y
  `app/rag/{confidence,citations}.py` son **guión puro** (solo docstring): es lo que falta.

Este plan implementa ese guión con código real y TDD: el grafo LangGraph, la confianza híbrida, las
citas, la extensión del puerto LLM, el checkpointer Postgres y el ciclo HITL interrupt→resume — y
sustituye `StubAgentRunner` por el adaptador real sin tocar servicios ni routers (ya cerrados).

### Precondición dura — verificada en esta sesión (no asumida)

El `HOW-TO-START-A-TASK.md` avisa de que las deps LLM "no están instaladas". **Verificado ahora**: sí lo
están — `requirements.txt` ya está compilado y el `.venv` tiene `langgraph==1.2.11`, `langchain==1.3.15`,
`langchain-openai==1.5.1`, `langgraph-checkpoint-postgres==3.1.2`, `langsmith==0.11.0` instalados (aviso
desactualizado del plan `kb-retriever`, que no tocaba esta parte).

Verificado por introspección real contra el paquete instalado (no contra las demos de referencia):
- `langgraph.types.interrupt(value: Any) -> Any` — dinámico, como asume la spec (NO `interrupt_before`).
- `langgraph.types.Command(*, graph=None, update=None, resume=None, goto=())`.
- `StateGraph.compile(checkpointer=None, *, cache=None, store=None, interrupt_before=None, ...)`.
- `ChatOpenAI.with_structured_output(schema, *, method='json_schema', include_raw=False, ...)`.

La spec acertó en el surface objetivo (`interrupt()`/`Command(resume=)`/`with_structured_output`); no hay
API drift que absorber.

**Hallazgo nuevo, bloqueante para el checkpointer (tarea 07)**: `psycopg` (3.3.4, sin extras) **no
importa** — `ImportError: no pq wrapper available` (falta el wrapper C/binario; no hay `libpq` de
sistema). `AsyncPostgresSaver` (`langgraph.checkpoint.postgres.aio`) depende de `psycopg` para
funcionar. Fix verificado disponible: `psycopg-binary==3.3.4` existe en PyPI para esta versión exacta.
La tarea 01 añade `psycopg[binary]` a `requirements.in` (ya es dependencia transitiva de
`langgraph-checkpoint-postgres`; esto solo fuerza la variante binaria en vez del wrapper C ausente — no
es una librería nueva) y recompila el lockfile.

### Decisión de alcance confirmada con el owner — LangSmith tracing

Dentro de alcance, **versión mínima explícita**: variables de entorno + población de
`agent_run.langsmith_trace_url`. Sin dashboards, alerting ni instrumentación fina — se anota como
follow-up en el plan change log y en el session log de la tarea 11.

### Decisiones de diseño (`grilling`, 2026-08-27)

1. **`graph.py` (06) construye el grafo COMPLETO**, `classify→retrieve→grade→generate→decide→
   [respond directo | interrupt()→respond]`, incl. el nodo `respond` (con `MessageRepository`
   inyectado) y la llamada a `interrupt()`. `interrupt()` es solo una llamada de función dentro de un
   nodo — la durabilidad la da compilar CON `PostgresSaver` (07), no el nodo en sí — así que la
   estructura completa no necesita el checkpointer para definirse. Corrige el guión previo de
   `nodes/__init__.py` (6 nodos, sin `respond`), escrito antes de verificar la API real. Tarea 07 =
   solo el checkpointer; tarea 08 = compilar grafo+checkpointer e invocar (`trigger`); tarea 09 =
   `resume`.
2. **DI de nodos = factory-closure**: cada `nodes/<nombre>.py` expone `make_<nombre>_node(puerto...) ->
   Callable[[State], Awaitable[State]]`; `build_graph(chat_model, retriever, messages_repo,
   confidence_threshold, ...)` las ensambla inyectando los puertos concretos. Mismo criterio de
   inyección por constructor que `Retriever`/`AgentService`/`ApprovalService`.
3. **Tablas de checkpoint vía migración Alembic** (DSN superuser, igual que el resto del schema): una
   migración nueva ejecuta el DDL de `AsyncPostgresSaver.setup()` una vez y otorga a `syntax_app` solo
   SELECT/INSERT/UPDATE (sin CREATE) — mantiene el least-privilege que ya rige `database_url`; las
   tablas de checkpoint quedan versionadas como el resto del schema.
4. **Pool del checkpointer = singleton perezoso por proceso** (`get_checkpointer_pool()`/
   `get_checkpointer()`), mismo patrón que `app/infra/db/session.py::get_engine()`/
   `get_sessionmaker()`; DSN derivado de `settings.database_url` quitándole `+asyncpg`. La
   **estructura** del grafo (sin I/O en su construcción) se construye per-request/per-run dentro del
   adaptador `LangGraphAgentRunner` (igual que `StubAgentRunner` hoy, wiring en tarea 10) — evita que un
   `MessageRepository` con sesión de una request quede capturado en un singleton de proceso.
5. **Fórmula de confianza** (`app/rag/confidence.py`, 02): `confidence = max(hit.score for hit in
   retrieved)` si `grade.suficiente=True`, si no `0.0`. El `grade` actúa como veto (no como sumando
   aritmético): `suficiente=False` escala siempre, sin hiperparámetro de ponderación sin datos reales
   para calibrarlo.
6. **Schema `Grade`** (nodo `grade`, 05): `Grade{suficiente: bool, motivo: str}` (ver ajuste 12: sin
   `relevante`, sin consumidor en el plan) — `motivo` obligatorio, se usa como `human_note` al escalar
   (CU-BE-05 exige explicar el hueco, no una nota genérica).
7. **`auto_approve` en `HelpdeskState`**, no puerto en `decide`: `runner.trigger()` (08) resuelve el
   tenant una vez al arrancar el run y mete `auto_approve: bool` en el estado inicial; `decide` (05)
   solo lee el campo — sin `TenantRepository` propio, acotado a lo que el nodo decide de verdad.

### Ajustes tras `design-review` (subagente adversario, 2026-08-27)

8. **[Bloqueante, resuelto] Gate de drift `tests/test_migration.py::test_models_do_not_drift_from_schema`**:
   las 4 tablas internas de `langgraph-checkpoint-postgres` (`checkpoint_migrations`, `checkpoints`,
   `checkpoint_blobs`, `checkpoint_writes`) no tienen modelo ORM — sin ajuste, el diff estructural las
   reporta como drift y el test (hoy en verde) se rompe. Fix: **allowlist explícito por nombre en el
   propio test** (filtrar tablas `checkpoint*` del diff, con comentario que remita a esta tarea/plan),
   no un `Table()` sin ORM paralelo — evita duplicar el DDL interno de la librería en un segundo sitio
   que habría que mantener sincronizado a mano (ver punto 10). Tarea 07 no cierra su DoD sin este ajuste.
9. **`respond` vive en `app/agents/nodes/respond.py`** (`make_respond_node(messages_repo)`), mismo
   patrón factory-closure que el resto — se mueve al alcance de la tarea 05 (junto al resto de nodos);
   `graph.py` (06) lo importa y wirea igual que a los demás. Corrige el hueco: el plan original solo
   listaba 6 nodos en "Dentro del alcance" y ninguna tarea mencionaba el fichero de `respond`.
10. **Riesgo documentado (no bloqueante)**: la migración de la tarea 07 clona DDL interno **no-público**
    de `langgraph-checkpoint-postgres` (`base.py`, strings Python crudos — no API estable; la librería
    documenta `.setup()` como lo que el usuario debe llamar, no algo pensado para clonarse a mano). Si se
    actualiza la dependencia y cambia su DDL interno, nada detecta que la migración Alembic vendida quedó
    desincronizada, y `syntax_app` (sin `CREATE`, decisión 3) no puede auto-repararse en runtime. La
    tarea 07 debe dejar esta nota en su propio fichero/session log: **en cualquier bump de
    `langgraph-checkpoint-postgres`, re-verificar a mano el array `MIGRATIONS` contra la migración
    Alembic vendida**.
11. **`app/rag/confidence.py` (tarea 02) gana una guarda explícita**: `retrieved=[]` con
    `grade.suficiente=true` (el LLM alucina suficiencia sin hits — fallo de juicio, no de conectividad)
    se trata como insuficiente (`confidence=0.0`), en vez de dejar que `max()` sobre secuencia vacía
    lance `ValueError` sin control. Añadido como escenario Gherkin de borde en la tarea 02.
12. **`Grade` se recorta a `Grade{suficiente: bool, motivo: str}`** (sin `relevante`): ningún consumidor
    del plan lo lee (`confidence.py` solo usa `suficiente`; `decide`/`citations`/`generate` tampoco lo
    mencionan) — mismo criterio que ya aplica `app/domain/ports/llm.py` (no fijar un campo sin caller
    real). Si aparece un consumidor real más adelante, se añade con su primer test.

## Objetivos

1. **Grafo determinista** `classify → retrieve → grade → generate → decide → [auto | interrupt] →
   respond`, edges condicionales tipados (ADR-0008).
   - *Criterio de éxito*: test de routing que, dado un estado con cada combinación relevante de
     `classification.resoluble` / `grade.suficiente` / `decide.requires_approval`, el grafo visita los
     nodos esperados.
2. **Confianza híbrida** (similitud + grade) gobierna auto vs escalado (ADR-0009).
   - *Criterio de éxito*: bajo umbral o `grade.suficiente=false` → siempre escalado con `human_note`,
     nunca respuesta inventada.
3. **HITL asíncrono durable** sobre `PostgresSaver` (ADR-0007).
   - *Criterio de éxito*: interrupt→checkpoint→resume funciona con un **runner reinstanciado** (simula
     reinicio del proceso) y una doble decisión sobre la misma `ApprovalTask` no reanuda el grafo dos
     veces (el CAS ya lo garantiza en `approval_service`; aquí se verifica que el resume real lo respeta).
4. **`StubAgentRunner` sustituido** por el adaptador real sin tocar `agent_service`/`approval_service`/
   los routers.
   - *Criterio de éxito*: el flujo HTTP completo (`ai-draft` → `approvals/{id}/approve|edit|reject`)
     funciona contra el runner real.
5. **Citas trazables** en toda respuesta con confianza suficiente.
   - *Criterio de éxito*: `generate` nunca produce un draft sin al menos una cita con `uc_id`.

## Alcance y fuera de alcance

### Dentro del alcance
- `app/rag/confidence.py`, `app/rag/citations.py`.
- Extensión de `ChatModel` (`generate`/`grade`) + `app/infra/llm/structured.py` +
  `app/infra/llm/openai_adapter.py` (`OpenAIChatModel` completo).
- `app/agents/state.py` + `app/agents/nodes/{classify,retrieve,grade,generate,decide,trim,respond}.py`.
- `app/agents/graph.py` (`build_graph()`).
- `app/agents/checkpointer.py` (`PostgresSaver`).
- `app/agents/runner.py` + `app/agents/hitl.py` (adaptador real de `AgentRunner`).
- Wiring en `app/core/deps.py` (sustituir `StubAgentRunner`).
- Settings nuevas (`agent_confidence_threshold`, config mínima de LangSmith).
- Fix `psycopg[binary]` en `requirements.in`/`requirements.txt`.

### Fuera de alcance
- Fase 2 completa: nota al desarrollador, KB de código, visibilidad `developer` (agent-graph.md §7/§11).
- Streaming SSE / `astream` token-a-token (seam, no Fase 1; agent-graph.md §9).
- `app/agents/tools.py` (`@tool`): ningún nodo de Fase 1 requiere tools externas — queda en guión.
- LangSmith más allá de la versión mínima acordada (sin dashboards/alerting).
- Rate-limiting multi-proceso de `ai-draft` (limitación ya documentada y aceptada en el plan anterior).
- El test de seguridad que falta en `app/core/deps.py:238` (revocar acceso a mitad de sesión) y
  `app/infra/db/seed.py` (tarea 17 del guión): notas sueltas de la sesión previa, sin relación con este
  plan — no se tocan salvo decisión explícita aparte.

## Recursos externos

- `OPENAI_API_KEY` real para verificación manual end-to-end (fuera del gate automatizado: los tests de
  `OpenAIChatModel` mockean el cliente `langchain-openai`, igual que ya hace `OpenAIEmbeddingModel`).
- Postgres+pgvector en Docker (`docker compose -f backend/docker-compose.yml up -d db`) para las tareas
  07/08/09/10 (checkpointer e integración HITL — obligatorio integración, no mocks).
- Cuenta LangSmith (tarea 11) — si no hay API key en el entorno de test, tracing se desactiva
  (`langsmith_tracing=false` por defecto) y el campo queda `None`; no bloquea el resto del gate.
- Specs: `.claude/specs/backend/agent-graph.md`, `spec.md`,
  `casos-de-uso/CU-BE-05-clasificacion-y-retrieval-rag.md`,
  `casos-de-uso/CU-BE-06-draft-ia-y-aprobacion-hitl.md`. ADRs: 0007, 0008, 0009.

## Estimación global

- **Tareas totales**: 11 (ver lista al final).
- **Esfuerzo estimado**: ~40-45h (revisado tras `scenario-coverage`: 05 sube a 6h por los nodos
  `trim`/`generate`/`decide` con más bordes; 08 sube a 8h por absorber la extensión de
  `AgentRunRepository`/`ApprovalRepository`; 09 gana 2 escenarios de borde adicionales).
- **Recursos**: 1 sesión por tarea; Postgres Docker para 07-10; `OPENAI_API_KEY` opcional (mockeada en CI).

## Criterios de calidad y verificación

- TDD en todas las capas; tests antes de la implementación.
- `make test` (pytest) y `ruff` + `mypy --strict` en verde tras cada tarea cerrada.
- Gate de mutation testing (`cosmic-ray`, `break: 80`) por tarea, sobre los ficheros que toca.
- Nivel de test por artefacto (`HOW-TO-START-A-TASK.md`): `confidence.py`/`citations.py`/nodos/
  `graph.py` → unit con mocks de puertos; `checkpointer.py` y el ciclo HITL (`runner`/`hitl`) →
  integración obligatoria contra Postgres real en Docker.
- `/sdd-lint` (spec EARS · CU Gherkin · ADR MADR) y `fact-checker` en el cierre de cada tarea.
- Verificación manual (no gateada): un `ai-draft` real de punta a punta contra OpenAI, revisado a ojo,
  antes de dar el plan por listo para producción — se anota en la nota retro del plan.

## Tasks

- [x] `backend-agent-graph-01` (P1) — Fix precondición: `psycopg[binary]`, settings nuevas
  (`agent_confidence_threshold`), smoke-test de superficie LangGraph/LangChain instalada · depends_on: —
- [x] `backend-agent-graph-02` (P1) — `app/rag/confidence.py` (confianza híbrida) · depends_on: —
- [x] `backend-agent-graph-03` (P1) — `app/rag/citations.py` (construcción de citas) · depends_on: —
- [x] `backend-agent-graph-04` (P1) — Extender `ChatModel` (`generate`/`grade`) + `structured.py` +
  `OpenAIChatModel` completo · depends_on: —
- [x] `backend-agent-graph-05` (P1) — `app/agents/state.py` + nodos (`classify/retrieve/grade/generate/
  decide/trim/respond`) · depends_on: backend-agent-graph-02, backend-agent-graph-03, backend-agent-graph-04
- [ ] `backend-agent-graph-06` (P1) — `app/agents/graph.py` (`build_graph()`, grafo COMPLETO incl.
  `respond`/`interrupt()`, plano, edges tipados; NO compila con checkpointer todavía) ·
  depends_on: backend-agent-graph-05
- [ ] `backend-agent-graph-07` (P1) — `app/agents/checkpointer.py` (`PostgresSaver` + migración Alembic
  de sus tablas + allowlist en `test_models_do_not_drift_from_schema` + nota de riesgo DDL vendido, pool
  singleton perezoso) · depends_on: backend-agent-graph-01
- [ ] `backend-agent-graph-08` (P1) — `app/agents/runner.py::trigger/run` (compila grafo(06)+
  checkpointer(07), `ainvoke` hasta interrupt o respond; persiste `AgentRun`) ·
  depends_on: backend-agent-graph-06, backend-agent-graph-07
- [ ] `backend-agent-graph-09` (P1) — `app/agents/hitl.py` + `runner.py::resume` (Command(resume=),
  reinicio a mitad de run, fallo LLM consistente) · depends_on: backend-agent-graph-08
- [ ] `backend-agent-graph-10` (P1) — Wiring: sustituir `StubAgentRunner` por el adaptador real en
  `app/core/deps.py`; smoke e2e vía HTTP · depends_on: backend-agent-graph-09
- [ ] `backend-agent-graph-11` (P2) — LangSmith tracing mínimo (env config + `langsmith_trace_url`) ·
  depends_on: backend-agent-graph-09

## Registro de cambios del plan

- 2026-08-27: creado. Verificado en sesión: deps LangGraph/LangChain **ya instaladas** (contradice el
  aviso de precondición del `HOW-TO-START-A-TASK.md`, que queda desactualizado); surface real
  (`interrupt`/`Command`/`with_structured_output`/`StateGraph.compile`) coincide con el objetivo de la
  spec. Hallazgo nuevo: `psycopg` sin wrapper binario rompe `AsyncPostgresSaver` → fix con
  `psycopg[binary]` en tarea 01. LangSmith tracing confirmado dentro de alcance (versión mínima,
  explícitamente parcial — follow-up documentado) tras pregunta directa al owner.
- 2026-08-27: refinado con `grilling` (7 preguntas, 7 decisiones — ver "Decisiones de diseño" arriba).
  Reshape de tareas 06-09: `graph.py` (06) pasa a construir el grafo COMPLETO (incl. `respond`/
  `interrupt()`), no solo hasta `decide`; `checkpointer.py` (07) se acota a checkpointer+migración
  Alembic+pool singleton; DI de nodos = factory-closure; fórmula de confianza = máximo del score si
  `grade.suficiente` si no 0; `Grade` lleva `motivo` (human_note); `auto_approve` viaja en
  `HelpdeskState`, no como puerto extra en `decide`.
- 2026-08-27: `design-review` (subagente adversario fresco, sin routing de modelo válido en
  `models.design-review` → aviso al owner y ejecutado con el modelo de sesión heredado). Halló 1
  bloqueante + 4 hallazgos menores; los 5 resueltos: (8) allowlist explícito por nombre en
  `test_models_do_not_drift_from_schema` para las 4 tablas del checkpointer, en vez de un `Table()` sin
  ORM paralelo — bloqueaba el cierre de la tarea 07; (9) `respond` pasa a `app/agents/nodes/respond.py`
  (factory-closure, `MessageRepository`) y se mueve al alcance de la tarea 05; (10) nota de riesgo
  añadida a la tarea 07: la migración clona DDL interno no-público de `langgraph-checkpoint-postgres`,
  re-verificar a mano en cualquier bump de la dependencia; (11) `confidence()` (tarea 02) gana guarda
  explícita para `retrieved=[]` con `grade.suficiente=true` (trata como insuficiente, no deja que
  `max()` reviente); (12) `Grade` se recorta a `{suficiente, motivo}` — sin `relevante`, sin consumidor
  en el plan (mismo criterio que ya aplica `app/domain/ports/llm.py`).
- 2026-08-27: `scenario-coverage` (subagente QA fresco, modelo `sonnet` — válido en
  `models.scenario-coverage`). Sección (B) fuera de alcance: **ninguno** — todos los hallazgos caían
  dentro del alcance ya declarado. Sección (A), 2 hallazgos **críticos** verificados contra código
  real (no hipótesis): (1) ninguna tarea creaba la `ApprovalTask(pending)` al interrumpir
  (`approval_service.py` no la crea; `decide` es puro sin puertos); (2) `AgentRunRepository` solo
  expone `update_status(id, status)`, sin forma de persistir `confidence`/`sources`/`error`/
  `escalated`/`finished_at`/`langsmith_trace_url` que 08/09/11 daban por hecho. Resueltos ampliando el
  alcance de la tarea 08 (añade `ApprovalRepository` + `AgentRunRepository.update_result(...)` nuevo,
  con su adaptador SQL) en vez de una tarea nueva — confirmado con el owner. Resto de hallazgos
  incorporados íntegros a las tareas 01 (límites de `agent_confidence_threshold`), 03 (dedup 3+,
  preserva orden), 04 (salida inválida vs. fallo de red, inicialización perezosa), 05 (prompt-injection
  en `classify`, idioma de respuesta + límites de salida en `generate`, `grade=None` no rompe,
  frontera exacta de `decide`, escenarios propios de `trim` — antes sin ninguno), 06 (propagación de
  errores de un puerto a través del grafo compilado, `trim` con 0/1 mensajes), 07 (pool singleton,
  aislamiento entre `thread_id`, Postgres inalcanzable), 09 (`resume` con `agent_run_id` inexistente,
  defensa en profundidad sobre thread sin interrupt pendiente, re-draft tras reopen con `run_seq=n+1`),
  10 (fallo de construcción de dependencias visible en arranque), 11 (continuidad de la traza
  LangSmith entre `trigger` y `resume`). Confirmado con el owner: incorporar todos, ninguno se
  descartó como sobre-ingeniería por el propio QA.
