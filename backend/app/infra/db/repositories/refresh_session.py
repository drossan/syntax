"""app.infra.db.repositories.refresh_session — adaptador SQLAlchemy de `RefreshSessionRepository`.

`rotate_if_active` es el CAS real: **una sola sentencia** `UPDATE ... WHERE token_hash=:h AND
status='active' ... RETURNING` — nunca `get`+`if`+`update` en pasos separados. Dos llamadas
concurrentes con el mismo `token_hash` serializan sobre el lock de fila de Postgres: como mucho una
ve el `UPDATE` afectar la fila (gana `Rotated`); la otra encuentra `status` ya `rotated` (0 filas
afectadas) y cae a `Reused`. Si el `UPDATE` afecta 0 filas, un `SELECT` de diagnóstico (fuera de la
ventana de carrera — ya no hay nada que proteger, el token ya está resuelto) distingue `Reused`
(existe pero no estaba activa) de `NotFound` (el hash no corresponde a ninguna sesión).
"""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.enums import RefreshSessionStatus
from app.domain.entities.identity import RefreshSession
from app.domain.errors import NotFound, PortError
from app.domain.ports.repositories import Reused, Rotated, RotationOutcome
from app.infra.db.models import RefreshSession as RefreshSessionModel
from app.infra.db.models.enums import RefreshSessionStatus as RefreshSessionStatusOrm
from app.infra.db.repositories._enum_bridge import to_domain, to_orm


def _to_domain(row: RefreshSessionModel) -> RefreshSession:
    return RefreshSession(
        id=row.id,
        user_id=row.user_id,
        tenant_id=row.tenant_id,
        token_hash=row.token_hash,
        family_id=row.family_id,
        parent_id=row.parent_id,
        status=to_domain(RefreshSessionStatus, row.status),
        expires_at=row.expires_at,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
    )


class SqlAlchemyRefreshSessionRepository:
    """Adaptador de `RefreshSessionRepository` (`app.domain.ports.repositories`)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, session: RefreshSession) -> RefreshSession:
        row = RefreshSessionModel(
            id=session.id,
            user_id=session.user_id,
            tenant_id=session.tenant_id,
            token_hash=session.token_hash,
            family_id=session.family_id,
            parent_id=session.parent_id,
            status=to_orm(RefreshSessionStatusOrm, session.status),
            expires_at=session.expires_at,
            user_agent=None,
            ip=None,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except Exception as exc:
            raise PortError("fallo al crear refresh session") from exc
        return _to_domain(row)

    async def rotate_if_active(
        self, token_hash: str, new_token_hash: str, now: datetime
    ) -> RotationOutcome:
        stmt = (
            update(RefreshSessionModel)
            .where(
                RefreshSessionModel.token_hash == token_hash,
                RefreshSessionModel.status == RefreshSessionStatusOrm.active,
            )
            .values(status=RefreshSessionStatusOrm.rotated, last_used_at=now)
            .returning(
                RefreshSessionModel.id,
                RefreshSessionModel.user_id,
                RefreshSessionModel.tenant_id,
                RefreshSessionModel.family_id,
                RefreshSessionModel.expires_at,
            )
        )
        try:
            rotated_row = (await self._session.execute(stmt)).one_or_none()
        except Exception as exc:
            raise PortError("fallo al rotar refresh session") from exc

        if rotated_row is not None:
            old_id, user_id, tenant_id, family_id, expires_at = rotated_row
            new_row = RefreshSessionModel(
                id=uuid.uuid4(),
                user_id=user_id,
                tenant_id=tenant_id,
                token_hash=new_token_hash,
                family_id=family_id,
                parent_id=old_id,
                status=RefreshSessionStatusOrm.active,
                expires_at=expires_at,
            )
            self._session.add(new_row)
            try:
                await self._session.flush()
            except Exception as exc:
                raise PortError("fallo al crear la sesión rotada") from exc
            return Rotated(session=_to_domain(new_row))

        try:
            existing_family_id = (
                await self._session.execute(
                    select(RefreshSessionModel.family_id).where(
                        RefreshSessionModel.token_hash == token_hash
                    )
                )
            ).scalar_one_or_none()
        except Exception as exc:
            raise PortError("fallo al comprobar refresh session") from exc
        if existing_family_id is None:
            raise NotFound(
                "ninguna refresh_session corresponde a ese token_hash",
                code="refresh_session.not_found",
            )
        return Reused(family_id=existing_family_id)

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        try:
            await self._session.execute(
                update(RefreshSessionModel)
                .where(RefreshSessionModel.family_id == family_id)
                .values(status=RefreshSessionStatusOrm.revoked)
            )
        except Exception as exc:
            raise PortError("fallo al revocar la family") from exc

    async def revoke(self, session_id: uuid.UUID) -> None:
        try:
            await self._session.execute(
                update(RefreshSessionModel)
                .where(RefreshSessionModel.id == session_id)
                .values(status=RefreshSessionStatusOrm.revoked)
            )
        except Exception as exc:
            raise PortError("fallo al revocar la sesión") from exc

    async def revoke_by_hash(self, token_hash: str) -> None:
        try:
            await self._session.execute(
                update(RefreshSessionModel)
                .where(RefreshSessionModel.token_hash == token_hash)
                .values(status=RefreshSessionStatusOrm.revoked)
            )
        except Exception as exc:
            raise PortError("fallo al revocar por hash") from exc
