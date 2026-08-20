"""app.infra.db.repositories.auth_token — adaptador SQLAlchemy de `AuthTokenRepository`.

Sin lógica condicional propia (CRUD simple sobre `token_hash`, único) — la semántica de un solo uso
(`used_at`, expiración, `kind`) la valida `auth_service`, no el repo.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import AuthTokenKind
from app.domain.entities.identity import AuthToken
from app.domain.errors import PortError
from app.infra.db.models import AuthToken as AuthTokenModel
from app.infra.db.models.enums import AuthTokenKind as AuthTokenKindOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm


def _to_domain(row: AuthTokenModel) -> AuthToken:
    return AuthToken(
        id=row.id,
        user_id=row.user_id,
        kind=to_domain(AuthTokenKind, row.kind),
        token_hash=row.token_hash,
        expires_at=row.expires_at,
        used_at=row.used_at,
    )


class SqlAlchemyAuthTokenRepository:
    """Adaptador de `AuthTokenRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, token: AuthToken) -> AuthToken:
        row = AuthTokenModel(
            id=token.id,
            user_id=token.user_id,
            kind=to_orm(AuthTokenKindOrm, token.kind),
            token_hash=token.token_hash,
            expires_at=token.expires_at,
            used_at=token.used_at,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear auth token") from exc
        return _to_domain(row)

    async def get_by_token_hash(self, token_hash: str) -> AuthToken | None:
        try:
            row = (
                await self._session.execute(
                    select(AuthTokenModel).where(AuthTokenModel.token_hash == token_hash)
                )
            ).scalar_one_or_none()
        except Exception as exc:
            raise PortError("fallo al buscar auth token") from exc
        return _to_domain(row) if row is not None else None

    async def mark_used(self, token_id: uuid.UUID, used_at: datetime) -> AuthToken:
        try:
            row = await self._session.get(AuthTokenModel, token_id)
        except Exception as exc:
            raise PortError("fallo al leer auth token") from exc
        if row is None:
            raise PortError(f"auth token {token_id} no existe")
        row.used_at = used_at
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al marcar auth token como usado") from exc
        return _to_domain(row)
