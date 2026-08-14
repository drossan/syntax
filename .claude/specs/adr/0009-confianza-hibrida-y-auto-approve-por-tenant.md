# 0009. Confianza híbrida (similitud + grade) → auto vs escalado; auto_approve=false por tenant

- **Estado**: accepted
- **Fecha**: 2026-08-11
- **Decisores**: Owner; `grilling` backend (rama 7); confirmado `auto_approve=false` por tenant.

## Contexto y planteamiento del problema

Tras recuperar contexto de la KB, el agente debe decidir si el draft es **fiable** (candidato a
auto-respuesta) o debe **escalar** a un humano con una nota. ¿Con qué señal se mide la fiabilidad y quién
decide si una respuesta se envía sin revisión?

## Decision drivers

- Una sola señal (solo similitud, o solo juicio del LLM) es frágil.
- No inventar respuesta cuando el contexto es insuficiente.
- El riesgo de auto-responder es del tenant; debe poder desactivarse.

## Opciones consideradas

- **Opción 1** — **Confianza híbrida**: similitud pgvector (coseno normalizado + re-ranking `estado`) **+**
  `grade` del LLM (relevancia/suficiencia) → umbral config → auto vs escalado; **`auto_approve=false` por
  defecto, por tenant**.
- **Opción 2** — Confianza **solo por similitud** vectorial.
- **Opción 3** — Confianza **solo por el juicio del LLM** (`grade`).

## Resultado de la decisión

Elegida: **Opción 1**. La señal combina **(a)** similitud de los chunks recuperados (de
[[0010-rag-pgvector-chunking-h2-tolerante-estado-peso]]) y **(b)** el `grade` del LLM; `≥ umbral`
(`AGENT_CONFIDENCE_THRESHOLD`) → candidato a auto; `< umbral` o `grade.suficiente=false` → **escalado** con
`human_note` explicando el hueco, **sin inventar** respuesta. `auto_approve=false` **por defecto y por
tenant**: en Fase 1 todo draft pasa por HITL salvo que un tenant lo active (y activarlo **eleva el riesgo**
de prompt-injection → documentado). `confidence`/`escalated` se persisten en `agent_run`.

### Confirmación

`agent-graph.md` §5, §7; `app/rag/confidence.py` (guión: híbrida, umbral config) + `approval_service`
(`auto_approve` default false). El umbral concreto se calibra al implementar.

## Consecuencias

- **Buenas**: dos señales independientes reducen falsos positivos; el humano decide por defecto.
- **Malas / coste**: dos llamadas de señal (retrieval + grade) por run; el umbral requiere calibración.

## Pros y contras de las opciones

- **Opción 1**: 👍 robusta, conservadora, configurable · 👎 coste de dos señales + calibración.
- **Opción 2**: 👍 barata, determinista · 👎 alta similitud ≠ respuesta correcta (falsos positivos).
- **Opción 3**: 👍 juicio contextual · 👎 el LLM sobre-confía; sin ancla objetiva de recuperación.
