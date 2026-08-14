# Session log — backend-skeleton-foundation-16 (Skeleton grafo — checkpointer + HITL)

## 2026-08-13 — Arranque

Movida `pending → active`. Deps 15/08 `done`. Doc-only. **Núcleo de riesgo** → guión exhaustivo. Recoge el
modelo HITL detallado de la spec 05 (interrupt→checkpoint Postgres→endpoint→resume; reinicio; concurrencia;
mapeo interrupt↔ApprovalTask). Mantiene nota de conformidad de API.

Ficheros: `app/agents/{checkpointer,hitl,runner}.py`.

## 2026-08-13 — Cierre

**Resumen:** 3 ficheros guión en `app/agents/`: `checkpointer` (PostgresSaver, thread_id=ticket_{id}_run_{n},
comparte pool 08, descarta Sqlite/Memory), `hitl` (guión exhaustivo: interrupt→checkpoint→endpoint→resume
con Command(resume); reinicio a mitad de run reanuda desde checkpoint; doble decisión→409 idempotente;
mapeo 1:1 interrupt↔ApprovalTask; auto_approve=true riesgo), `runner` (run/resume, AgentRun.failed en
fallo LLM, materializa Message(public)+transición delegando en approval_service 10, A1.1). Nota de
conformidad de API en PostgresSaver/interrupt/Command.

**Verificación:** `compileall` exit 0; grep código ejecutable → sin coincidencias.

**Gate `fact-checker` (sonnet):** **8/8 VERIFICADO** (incl. coherencia con 03: agent_run
langgraph_thread_id/run_seq/failed, approval_status).

**Docs:** 3 ficheros nuevos. Plan: `[x]` 16 + Registro. **Tiempo real:** ~0.6 h.

**Follow-ups:** cierra el flujo HITL end-to-end; 12 (ai-draft→run, approvals→resume) lo invoca. Al
implementar: tests de reanudación tras reinicio + concurrencia (los footguns del núcleo de riesgo).
