"""app.core.security — primitivas de identidad puras y sin estado.

Hashing de contraseñas (Argon2id) y JWT de acceso. NO decide autorización (eso es RBAC/dominio),
NO toca DB y NO lee config: recibe lo que necesita por parámetro. El wiring a get_settings() lo hace
el servicio de auth en su plan.
"""

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()
_OPAQUE_TOKEN_BYTES = 32
"""256 bits de entropía (`secrets.token_urlsafe` genera ~1.3 caracteres por byte)."""


def new_opaque_token() -> str:
    """Token opaco aleatorio (256 bits) para `refresh_session`/`auth_token`.

    No es un JWT ni lleva payload: es un secreto que solo tiene sentido junto a su `hash_token()`
    almacenado, buscado por igualdad.
    """
    return secrets.token_urlsafe(_OPAQUE_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Hash **determinista** (SHA-256) de un token opaco — buscable por igualdad en `token_hash`.

    A diferencia de `hash_password` (Argon2id, salt aleatorio embebido → cada hash es distinto aunque
    la contraseña sea la misma, por diseño), `token_hash` es `UNIQUE` y se busca por igualdad exacta:
    Argon2 haría esa búsqueda imposible. No es para contraseñas humanas (sin salt, sin cómputo lento
    a propósito) — el propio token ya tiene 256 bits de entropía aleatoria.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    """Calcula el hash Argon2id de ``password`` (salt aleatorio embebido)."""
    return _hasher.hash(password)


def verify_password(password: str, hash: str) -> bool:
    """Verifica ``password`` contra el ``hash`` Argon2id. Devuelve ``True``/``False``, nunca lanza por
    contraseña incorrecta (fail-closed)."""
    try:
        return _hasher.verify(hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(
    sub: str,
    tenant_id: str,
    *,
    secret: str,
    algorithm: str,
    ttl: int,
    now: datetime,
) -> str:
    """Emite un JWT de acceso. Claims: ``sub``, ``tenant_id``, ``iat`` (=now), ``exp`` (=now+ttl).
    NO incluye capacidades (se resuelven server-side por request)."""
    issued = int(now.timestamp())
    payload = {"sub": sub, "tenant_id": tenant_id, "iat": issued, "exp": issued + ttl}
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_access_token(
    token: str,
    *,
    secret: str,
    algorithm: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Decodifica y valida el JWT. Fija ``algorithms=[algorithm]`` (rechaza alg=none/confusión) y
    comprueba la expiración contra ``now`` (o el reloj real si ``now`` es None). ``exp <= now`` → expirado."""
    claims: dict[str, Any] = jwt.decode(
        token,
        secret,
        algorithms=[algorithm],
        options={"require": ["exp", "sub", "tenant_id"], "verify_exp": False},
    )
    current = int((now or datetime.now(tz=UTC)).timestamp())

    if current >= claims["exp"]:
        raise jwt.ExpiredSignatureError("El token ha expirado")

    return claims
