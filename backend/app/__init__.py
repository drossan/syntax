"""Syntax — backend (paquete raíz).

Aplicación FastAPI async del helpdesk con IA generativa. Arquitectura HEXAGONAL:

    api → domain ← infra

El dominio (``app.domain``) NO importa infraestructura ni la capa API: define puertos
(interfaces) que ``app.infra`` implementa y que ``app.api`` orquesta. Regla de oro para
todo lo que cuelga de aquí: **la dirección de dependencias no se invierte nunca**.

Esqueleto doc-only: cada subpaquete lleva un guión que apunta a la tarea que lo rellena
(ver ``backend/README.md`` y `.claude/plans/active/backend/skeleton-foundation.md`).
"""
