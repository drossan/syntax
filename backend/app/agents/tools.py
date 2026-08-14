"""app.agents.tools — tools tipadas del agente (si se usan).

GUIÓN (→ tarea 15; spec 05)
---------------------------
Qué implementar:
  - Tools ``@tool`` con **args tipados** (Pydantic), **solo si un nodo las requiere**.
  - **Toolset acotado por tenant** (mínimo privilegio): una tool no ve datos de otro tenant; el
    aislamiento sigue app-level + RLS (03/02).

⚠️ Conformidad (05): ``@tool`` = API objetivo de LangChain; pinar al implementar. Anti-patrón: tools con
acceso cross-tenant; tools no tipadas.
"""
