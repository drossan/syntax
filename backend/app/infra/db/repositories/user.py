"""app.infra.db.repositories.user — adaptador SQLAlchemy de `UserRepository`.

`User` es identidad GLOBAL (sin `tenant_id`, email único global) desde el rediseño multi-tenant —
`get_by_email` busca sin filtrar por tenant. `BaseRepository` no aplica: no hay `TenantMixin`.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.identity import User
from app.domain.errors import PortError
from app.infra.db.models import User as UserModel


def _to_domain(row: UserModel) -> User:
    return User(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        sso_subject=row.sso_subject,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyUserRepository:
    """Adaptador de `UserRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        try:
            row = await self._session.get(UserModel, user_id)
        except Exception as exc:
            raise PortError("fallo al leer user") from exc
        return _to_domain(row) if row is not None else None

    async def get_by_email(self, email: str) -> User | None:
        try:
            row = (
                await self._session.execute(select(UserModel).where(UserModel.email == email))
            ).scalar_one_or_none()
        except Exception as exc:
            raise PortError("fallo al buscar user por email") from exc
        return _to_domain(row) if row is not None else None

    async def list_by_ids(self, user_ids: list[uuid.UUID]) -> list[User]:
        if not user_ids:
            return []
        try:
            rows = (
                await self._session.execute(select(UserModel).where(UserModel.id.in_(user_ids)))
            ).scalars()
        except Exception as exc:
            raise PortError("fallo al listar users por id") from exc
        return [_to_domain(row) for row in rows]

    async def add(self, user: User) -> User:
        row = UserModel(
            id=user.id,
            email=user.email,
            password_hash=user.password_hash,
            sso_subject=user.sso_subject,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear user (¿email duplicado?)") from exc
        return _to_domain(row)

    async def update(self, user: User) -> User:
        try:
            row = await self._session.get(UserModel, user.id)
        except Exception as exc:
            raise PortError("fallo al leer user") from exc
        if row is None:
            raise PortError(f"user {user.id} no existe")
        row.email = user.email
        row.password_hash = user.password_hash
        row.sso_subject = user.sso_subject
        try:
            await self._session.flush()
            await self._session.refresh(row)
        except Exception as exc:
            raise PortError("fallo al actualizar user") from exc
        return _to_domain(row)
