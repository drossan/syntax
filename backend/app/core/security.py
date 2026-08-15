"""app.core.security — primitivas de identidad puras y sin estado.

Hashing de contraseñas (Argon2id) y JWT de acceso. NO decide autorización (eso es RBAC/dominio),
NO toca DB y NO lee config: recibe lo que necesita por parámetro. El wiring a get_settings() lo hace
el servicio de auth en su plan.
"""

from datetime import UTC, datetime
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


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
