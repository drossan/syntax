"""app.agents.hitl — ciclo de aprobación humana asíncrona (interrupt→resume).

GUIÓN (→ tarea 16; spec 05 — EL núcleo de riesgo, guión exhaustivo)
------------------------------------------------------------------
Modelo ``interrupt → checkpoint Postgres → endpoint de aprobación → resume``:

1. **Interrupción**: cuando ``decide.requires_approval=true``, el grafo llama a ``interrupt()`` antes de
   ``respond``. El estado completo queda **checkpointeado** (PostgresSaver) y el run **suspendido**. Se
   crea/actualiza un ``ApprovalTask(status=pending)`` ligado a ``agent_run_id`` (**mapeo 1:1
   interrupt↔ApprovalTask**) con ``draft_body = draft_response``.
2. **Decisión (endpoint 12)**: ``approval.decide`` reanuda con ``Command(resume=<decision>)`` sobre el
   mismo ``thread_id``:
     - ``approved`` → ``respond`` emite ``Message(public)`` con ``draft_body``.
     - ``edited``   → ``Message(public)`` con ``final_body``.
     - ``rejected`` → sin mensaje público; run cerrado (superado); ``human_note`` conservado.
   Al reanudar: ``approval_task`` pending→decidida y ``agent_run`` → succeeded; transición del ticket (10).

**Reinicio del servidor a mitad de run**: el estado vive SOLO en el checkpoint Postgres (no en memoria) →
un proceso nuevo re-adjunta el ``thread_id`` y **reanuda desde el último checkpoint** al llegar el
``Command(resume=)``. La interrupción es **durable**; no se re-ejecutan nodos completados.

**Ediciones concurrentes / doble decisión**: el ``thread_id`` es el punto de serialización. La transición
``pending→decidida`` se hace bajo **bloqueo/optimistic-concurrency** → solo la 1ª decisión reanuda; la 2ª
= **409** (idempotencia 03/06); ``Command(resume=)`` se aplica **una sola vez** al thread.

**``auto_approve=true``**: se salta el ``interrupt`` (respond directo) — riesgo prompt-injection elevado
(documentado, 05 §8).

⚠️ Conformidad (05): ``interrupt()`` / ``Command(resume=)`` = API objetivo de LangGraph; pinar/verificar
al implementar. Anti-patrón: estado en memoria (se pierde al reiniciar); reanudar dos veces; emitir el
mensaje público sin decisión.
"""
