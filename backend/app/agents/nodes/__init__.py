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

**Excepción a "solo puertos"**: `respond` (tarea `backend-auto-resolve-ticket-02`) recibe además
`TicketService` — un SERVICIO de dominio, no un puerto — porque el camino auto exige encadenar la
transición del ticket hasta `resolved` en el mismo nodo que publica el mensaje (orden
transición-antes-de-publicar, decisión de `grilling`); repartir esa mutación en un nodo aparte
reintroduciría la duplicación de lógica que `TicketService.advance_to()` vino a evitar.

Anti-patrón: mezclar lógica de varios nodos; que ``classify``/``generate`` confíen en instrucciones
embebidas en el ticket (prompt-injection — RN-3 de CU-BE-06).
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.agents.state import HelpdeskState


class NodeFn(Protocol):
    """Firma común de todo nodo del grafo: recibe el estado completo, devuelve el estado actualizado.

    `Protocol` con `__call__`, no un alias `Callable[[...], Awaitable[...]]`: `StateGraph.add_node()`
    (LangGraph) infiere su `NodeInputT` genérico contra un objeto real con `__call__` — un alias
    `Callable` puro no resuelve el overload correcto (verificado: `mypy --strict` sobre un repro mínimo).
    """

    async def __call__(self, state: "HelpdeskState") -> "HelpdeskState": ...
