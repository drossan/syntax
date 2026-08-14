"""app.api.v1.routers.auth — endpoints de autenticación (contrato 06).

GUIÓN (→ tarea 11)
------------------
Endpoints (delegan en ``auth_service`` de 10 + ``app.core.security``):
  - ``POST /auth/login`` → access en body + refresh en cookie httpOnly (Set-Cookie).
  - ``POST /auth/refresh`` → rota el refresh (reuse-detection revoca familia).
  - ``POST /auth/logout`` → logout server-side (revoca sesión, no solo borra cookie).
  - ``GET /auth/me`` → sujeto + capacidades efectivas (resueltas server-side).
  - ``POST /auth/password/{forgot,reset,change}`` (B.3) + invitación al crear usuario (email = stub).

Convenciones: público (sin auth) en login/refresh/forgot/reset; throttling en login/refresh (07). Errores
con envelope problem+json. Anti-patrón: lógica de tokens en el router (vive en security/auth_service).
"""
