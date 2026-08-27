"""app.agents.nodes — nodos del grafo (agent-graph.md §2-§3, tarea backend-agent-graph-05).

Un nodo por fichero; cada uno es una **factory-closure** `make_<nombre>_node(puerto...) -> NodeFn`: recibe
sus puertos por inyección de constructor (sin importar infra directamente) y devuelve la función async
que `build_graph()` (tarea 06) registra. 7 nodos (`respond` se sumó en `design-review`, ajuste 9 — el
guión previo solo listaba 6):

  - ``classify``  → structured output ``{categoria, dominio 1-de-17, prioridad, resoluble}``; filtra retrieval.
  - ``retrieve``  → usa el retriever (02/03), filtra por ``dominio`` (fallback sin filtro si no clasificable).
  - ``grade``     → relevancia/suficiencia del contexto → confianza híbrida (``app.rag.confidence``).
  - ``generate``  → draft fiel al contexto + citas (``app.rag.citations``); idioma del ticket.
  - ``decide``    → auto vs escalado (``requires_approval``) + ``interrupt()`` inline si escala.
  - ``trim``      → ``trim_messages`` para acotar el historial en hilos largos.
  - ``respond``   → publica el `Message` público según `requires_approval`/`human_decision`.

Anti-patrón: mezclar lógica de varios nodos; que ``classify``/``generate`` confíen en instrucciones
embebidas en el ticket (prompt-injection — RN-3 de CU-BE-06).
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agents.state import HelpdeskState

NodeFn = Callable[["HelpdeskState"], Awaitable["HelpdeskState"]]
"""Firma común de todo nodo del grafo: recibe el estado completo, devuelve el estado actualizado."""
