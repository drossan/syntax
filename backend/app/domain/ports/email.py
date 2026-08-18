"""app.domain.ports.email — puerto de envío de email (stub en Fase 1).

`auth_service` lo usa para reset/invitación (B.3). Fase 1: el adaptador real es un stub que loguea/encola
(fuera de este plan). Anti-patrón: bloquear el flujo de negocio si el email falla (best-effort en Fase 1).
"""

from typing import Protocol


class EmailPort(Protocol):
    """Envío de email transaccional (async)."""

    async def send(self, to: str, template: str, context: dict[str, object]) -> None:
        """Envía `template` a `to` con `context`. El adaptador real debe envolver fallos en `PortError`."""
        ...
