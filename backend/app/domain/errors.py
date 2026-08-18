"""app.domain.errors — jerarquía de excepciones de dominio (taxonomía HTTP-derivable).

Todos los servicios de este plan señalizan error **lanzando** estas excepciones, **salvo**
`rbac_service.authorize` (devuelve `Allow | Deny` — el "no" es el camino esperado, no un error, decisión
de grilling). Cada excepción concreta hereda de una de las 4 bases; el mapeo HTTP futuro (11/12) es una
tabla de datos (`type(exc) -> status`), no un árbol de `isinstance`. `code` es un slug estable
(p.ej. `"ticket.invalid_transition"`) para telemetría/logs; `details` lleva contexto estructurado.

`PortError` es aparte: los adaptadores reales (asyncpg/httpx/openai) lanzarán excepciones de infra a
través de los puertos en producción — el docstring de cada puerto documenta que el adaptador debe
envolverlas en `PortError` (preservando la causa vía `raise ... from exc`).
"""


class DomainError(Exception):
    """Base de toda excepción de dominio. `code` es un slug estable; `details` es contexto estructurado."""

    def __init__(
        self, message: str, *, code: str, details: dict[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details: dict[str, object] = details if details is not None else {}


class NotFound(DomainError):
    """El recurso solicitado no existe (mapeo HTTP futuro: 404)."""


class Conflict(DomainError):
    """El recurso existe pero la operación no es válida en su estado actual (mapeo HTTP futuro: 409)."""


class InvalidTransition(Conflict):
    """Transición de estado no permitida por la máquina de estados (mapeo HTTP futuro: 409/422)."""


class Validation(DomainError):
    """La entrada no cumple una regla de negocio (mapeo HTTP futuro: 422)."""


class PortError(DomainError):
    """Envuelve un fallo de infra (timeout, error de proveedor) que atraviesa un puerto.

    El adaptador real debe lanzar `raise PortError(...) from original_exc` para preservar la causa
    (`__cause__`), nunca dejar pasar la excepción de infra cruda al dominio.
    """

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message, code="port.external_service_error", details=details)


ExternalServiceError = PortError
"""Alias — algunos puertos lo referencian con este nombre (más descriptivo en su contexto)."""
