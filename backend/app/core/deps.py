"""app.core.deps — dependencias FastAPI comunes.

GUIÓN (→ tarea 07)
------------------
Propósito: el punto de composición de la capa API. Provee (vía ``Depends``) las piezas transversales
que consumen los routers (11/12), respetando hexagonal (la API orquesta; el dominio define puertos).

Qué implementar:
  - ``get_settings`` → re-export de ``app.core.config.get_settings`` como dependencia.
  - **Sesión DB**: ``get_db_session()`` → ``AsyncSession`` por request (de ``app.infra.db`` 08). Al abrir
    la conexión, fija el contexto de tenant para RLS: ``SET app.tenant_id = <uuid>`` (08 — **footgun** en
    pool asyncpg: exige tests de integración).
  - **Contexto de tenant**: ``get_tenant_context()`` → tenant del sujeto (o el elegido en el switcher si
    es Soporte con capacidad ``global``). Lo consumen repos (filtro app-level) y el SET de RLS.
  - **Sujeto autenticado**: ``get_current_subject()`` → decodifica el access (``security.py``) y **resuelve
    las capacidades server-side por request** desde BD (A1.7), no desde el token. Fail-closed: si no se
    pueden resolver → deny-all (ver rbac 02 §8).
  - **Autorización**: ``require_capability(capability, scope)`` → dependencia/decorador que consulta el
    servicio RBAC (``app.domain``); deny → HTTP 403 con el envelope estándar (06). Decide por
    **capacidad + ámbito**, nunca por nombre de rol.

Contrato: dependencias inyectables reutilizables por todos los routers; sin estado global.

Anti-patrones: resolver permisos desde el JWT; abrir sesiones DB fuera del ciclo de request; autorizar por
nombre de rol; capturar el tenant de forma global compartida entre requests (romper el aislamiento).
"""
