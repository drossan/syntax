"""app.infra.email — adaptador stub del puerto `EmailPort` (Fase 1).

`auth_service` lo usa para reset/invitación (B.3). El envío real de email queda fuera de alcance en
esta fase (decisión de `domain-services`/`routers-core`): el stub loguea en vez de enviar, y nunca
bloquea el flujo de negocio si "falla" (no puede fallar — no hace I/O real).
"""

import structlog

_logger = structlog.get_logger()


class StubEmailPort:
    """Adaptador de `EmailPort`: loguea el envío en vez de mandarlo (sin I/O real, Fase 1)."""

    async def send(self, to: str, template: str, context: dict[str, object]) -> None:
        _logger.info("email_stub_send", to=to, template=template)
