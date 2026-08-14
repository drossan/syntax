"""app.core.security — hashing, JWT y sesiones de refresh.

GUIÓN (→ tarea 07)
------------------
Propósito: primitivas de autenticación. NO decide autorización (eso es RBAC, ver
``.claude/specs/backend/rbac.md`` 02 y ``app.domain``); aquí solo identidad + tokens.

Qué implementar:
  - **Password hashing**: Argon2id (p.ej. ``argon2-cffi``/``passlib``). ``hash_password(str)`` /
    ``verify_password(str, hash)``. Nunca guardar la contraseña en claro (03: ``user.password_hash``).
  - **JWT access**: ``create_access_token(sub, tenant_id, ...)`` con claims ``sub`` (user id),
    ``tenant_id``, ``exp`` (JWT_ACCESS_TTL). TTL corto (memoria en el cliente).
    ``decode_access_token(token) -> claims`` con verificación de firma/exp.
    NOTA (A1.7): el token **NO** lleva las capacidades; se resuelven server-side por request (ver
    ``deps.py``) para que un cambio/revocación de rol surta efecto en la siguiente request.
  - **Refresh + RefreshSession (03)**: el refresh viaja en cookie httpOnly. Contra la tabla
    ``refresh_session`` (03 §4.1): se guarda el ``token_hash`` (no el token), con ``family_id`` +
    ``parent_id`` para la cadena de rotación.
      - ``rotate_refresh(...)``: emite uno nuevo, marca el anterior ``rotated``.
      - **reuse-detection**: si llega un refresh ya ``rotated``/``revoked`` → revocar **toda la
        ``family_id``** (logout global de esa cadena) y denegar.
      - ``logout(...)``: **server-side** — revoca la sesión/familia en BD, no solo borra la cookie.
  - **Tokens de un solo uso** (03 ``auth_token``): reset de contraseña / invitación (hash + expiración
    + ``used_at``); el envío del email es un stub del puerto en Fase 1.

Contrato (consumido por deps/routers): ``get_current_subject`` (en ``deps.py``) usa ``decode_access_token``
para resolver el sujeto; la rotación/reuse-detection las orquesta el servicio de auth.

Anti-patrones: meter roles/capacidades en el JWT y confiar en ellos para autorizar; logout que solo borra
la cookie sin revocar en BD; almacenar el refresh en claro; algoritmo de hashing débil.
"""
