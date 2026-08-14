"""app.core.logging — logging estructurado + request-id.

GUIÓN (→ tarea 07)
------------------
Propósito: observabilidad transversal. Logs estructurados (JSON) correlacionables por petición.

Qué implementar:
  - ``configure_logging(settings)``: logging estructurado (JSON en prod, legible en dev según APP_ENV).
    Sin efectos en import; se llama desde ``create_app()``.
  - **request-id**: un ``contextvar`` con el id de correlación por request + un middleware que lo genera
    (o lee el header ``X-Request-ID`` entrante), lo inyecta en cada log y lo devuelve en la respuesta.
    Todos los logs de una request comparten ese id (traza extremo a extremo).
  - **Observabilidad de errores** (refuerzo B): hook opcional tipo Sentry (init condicionado por env; sin
    efectos en import). Las excepciones no capturadas se loguean con el request-id.
  - Enlace con el tracing del agente: el ``langsmith_trace_url`` del ``AgentRun`` (03/05) se referencia en
    los logs del flujo-IA para saltar de un log a su traza.

Contrato: ``get_request_id() -> str | None`` y el middleware de correlación (montado en ``main.py``).

Anti-patrones: ``print``; configurar logging a nivel de import; loguear secretos/PII (tokens,
contraseñas, cookies); un request-id global mutable en vez de ``contextvar`` (rompe en async/concurrencia).
"""
