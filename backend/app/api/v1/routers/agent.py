"""app.api.v1.routers.agent — disparo del agente y estado del run (contrato 06).

GUIÓN (→ tarea 12)
------------------
Endpoints (delegan en el runner del grafo 16 + ``approval_service`` 10):
  - ``POST /tickets/{id}/ai-draft`` (``agent.trigger``) → lanza el grafo (15/16); crea ``AgentRun`` y (si
    procede) ``ApprovalTask`` pendiente. Fase 1: request/polling (sin SSE). **Rate-limit por usuario/
    tenant** (B.1 — cada disparo cuesta llamadas LLM); 429 al exceder; 409 si ya hay run en curso.
  - ``GET /agent-runs/{id}`` → estado del run: ``status`` (incl. ``failed``), ``confidence``, ``sources``
    (citas), ``langsmith_trace_url``, ``error``.

Respuesta ante ``AgentRun.failed`` (fallo LLM): error controlado con envelope, no excepción cruda.
Anti-patrón: ejecutar el grafo sínc. bloqueando el request sin límite; exponer el run de otro tenant.
"""
