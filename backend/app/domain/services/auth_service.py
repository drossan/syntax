"""app.domain.services.auth_service — sesión, reset e invitación (B.3).

GUIÓN (→ tarea 10)
------------------
Qué implementar (sobre ``UserRepository`` + ``RefreshSessionRepository`` + ``AuthToken`` + puerto email):
  - **Login**: verificar credenciales (Argon2, ``app.core.security``), emitir access + crear
    ``RefreshSession``.
  - **Refresh**: rotación + **reuse-detection** (un refresh ya usado → revocar toda la ``family_id``);
    **logout server-side** (revocar en BD, no solo borrar cookie). (03 §4.1, 07 ``security.py``.)
  - **Password reset** (B.3): ``forgot`` genera ``AuthToken(kind=password_reset)`` (hash + expiración) y
    lo envía por el **puerto email (stub)**; ``reset`` lo consume (un solo uso, ``used_at``); ``change``
    con la contraseña actual.
  - **Invitación** (B.3): al crear usuario → estado ``invited`` + ``AuthToken(kind=invitation)`` enviado
    por email (stub); al fijar contraseña pasa a ``active``.

Anti-patrón: revelar si un email existe (respuesta uniforme en ``forgot``); tokens de reset reutilizables;
logout que no revoca la sesión en BD.
"""
