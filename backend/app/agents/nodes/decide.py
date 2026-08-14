"""app.agents.nodes.decide — auto vs escalado (HITL gate).

GUIÓN (→ tarea 15; spec 05)
---------------------------
  - Decide ``requires_approval`` según: ``auto_approve`` del tenant (default false) **OR** confianza <
    umbral (``AGENT_CONFIDENCE_THRESHOLD``, 14) **OR** escalado (contexto insuficiente).
  - Es el edge condicional tipado hacia ``[auto | HITL]`` → ``respond``. El ``interrupt``/checkpointer/
    ``respond`` con persistencia los añade la tarea 16.

Anti-patrón: decidir por texto libre del LLM; ignorar ``auto_approve`` del tenant.
"""
