"""app.agents.runner — orquestación de run/resume del grafo.

GUIÓN (→ tarea 16; spec 05)
---------------------------
Qué implementar (integra grafo 15 + checkpointer 16 + servicios 10 + tracing 09):
  - ``run(ticket)``: crea ``AgentRun`` (``run_seq`` = siguiente; ``thread_id=ticket_{id}_run_{n}``),
    compila el grafo con el ``PostgresSaver`` e invoca hasta el ``interrupt`` (o hasta ``respond`` si
    ``auto_approve``). Persiste ``confidence``/``sources``/``langsmith_trace_url`` en el AgentRun (03/09).
  - ``resume(ticket, decision)``: reanuda con ``Command(resume=decision)`` sobre el ``thread_id`` del run
    pendiente; delega en ``approval_service`` (10) la materialización ``Message(public)`` + transición del
    ticket (A1.1) y las transiciones de ``ApprovalTask``/``AgentRun``.
  - **Fallo del LLM a mitad de run** → ``AgentRun.failed`` + ``error``; checkpoint consistente; error
    controlado al usuario (no excepción cruda).

Lo invoca el router de flujo-IA (12: ``ai-draft`` → ``run``; ``approvals`` → ``resume``).
Anti-patrón: lógica de negocio duplicada aquí (delegar en servicios 10); reanudar sin guard de idempotencia.
"""
