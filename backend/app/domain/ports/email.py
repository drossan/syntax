"""app.domain.ports.email — puerto de envío de email (stub en Fase 1).

GUIÓN (→ tarea 10; B.3)
-----------------------
Interfaz (async) para entregar emails transaccionales de **reset de contraseña** e **invitación** (B.3).
Fase 1: adaptador **stub** (loguea/encola, no envía de verdad); el envío real (SMTP/proveedor) queda
**diferido**.

  - ``send(to, template, context)`` — el ``auth_service`` lo usa para reset/invitación.

Anti-patrón: bloquear el flujo de negocio si el email falla (best-effort en Fase 1); revelar en la
respuesta HTTP si el destinatario existe.
"""
