"""app.api.v1.routers.approvals — cola de aprobación HITL por HTTP (contrato 06/12).

`approval.decide` es una capacidad **exclusivamente `global`** (`rbac.md §3/§4`: ningún rol custom por
tenant puede concederla, solo Soporte) — pero las `ApprovalTask` pertenecen a los tenants CLIENTE, nunca
al tenant `syntax`. `GET /approvals` resuelve `tenant_id=None` (agrega cross-tenant) cuando el subject
tiene la capacidad en ámbito `global`; con un hipotético grant `tenant` (invariante de RBAC lo impide en
producción, pero el puerto lo soporta genéricamente) usa `subject.tenant_id`. `decide()` (CAS, resume del
grafo) ya está cerrado en `domain-services` — este router solo hace wiring HTTP, sin lógica nueva.
"""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.approvals import (
    ApprovalApproveRequest,
    ApprovalEditRequest,
    ApprovalRejectRequest,
)
from app.api.v1.schemas.approvals import ApprovalTask as ApprovalTaskSchema
from app.api.v1.schemas.common import Page
from app.core.deps import get_approval_service, require_capability
from app.domain.entities.business import ApprovalTask as ApprovalTaskEntity
from app.domain.entities.enums import ApprovalStatus
from app.domain.entities.identity import Subject
from app.domain.errors import Validation
from app.domain.ports.repositories import APPROVAL_SORT_FIELDS
from app.domain.services.approval_service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["ai-flow"])

_CAPABILITY = "approval.decide"


def _to_schema(task: ApprovalTaskEntity) -> ApprovalTaskSchema:
    return ApprovalTaskSchema(
        id=task.id,
        ticket_id=task.ticket_id,
        agent_run_id=task.agent_run_id,
        status=task.status.value,
        draft_body=task.draft_body,
        final_body=task.final_body,
        human_note=task.human_note,
        decided_by=task.decided_by,
        decided_at=task.decided_at,
        created_at=task.created_at,
    )


def _validate_sort(sort: str) -> str:
    if sort not in APPROVAL_SORT_FIELDS:
        raise Validation(
            f"sort no admitido: {sort}",
            code="approval.sort_not_allowed",
            details={"field": "sort", "message": f"sort no admitido: {sort}"},
        )
    return sort


def _parse_status(value: str | None) -> ApprovalStatus | None:
    if value is None:
        return None
    try:
        return ApprovalStatus(value)
    except ValueError as exc:
        raise Validation(
            f"status no admitido: {value}",
            code="approval.invalid_status",
            details={"field": "status", "message": f"status no admitido: {value}"},
        ) from exc


def _tenant_scope_or_none(subject: Subject) -> uuid.UUID | None:
    """`None` (agrega cross-tenant) si el subject tiene `approval.decide` en ámbito `global`;
    `subject.tenant_id` si solo la tiene en `tenant` (invariante de RBAC lo impide en producción,
    soportado aquí de forma genérica)."""
    if (_CAPABILITY, "global") in subject.capabilities:
        return None
    return subject.tenant_id


@router.get("")
async def list_approvals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    sort: str = Query("sla_due,confidence"),
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
    approval_service: ApprovalService = Depends(get_approval_service),
) -> Page[ApprovalTaskSchema]:
    subject, _session = subject_session
    _validate_sort(sort)
    parsed_status = _parse_status(status)
    result = await approval_service.list_queue(
        _tenant_scope_or_none(subject),
        status=parsed_status,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[_to_schema(t) for t in result.items],
        page=page,
        page_size=page_size,
        total=result.total,
    )


@router.post("/{id}/approve")
async def approve(
    id: uuid.UUID,
    payload: ApprovalApproveRequest | None = None,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
    approval_service: ApprovalService = Depends(get_approval_service),
) -> ApprovalTaskSchema:
    _subject, _session = subject_session
    human_note = payload.human_note if payload is not None else None
    task = await approval_service.decide(id, "approve", None, human_note)
    return _to_schema(task)


@router.post("/{id}/edit")
async def edit(
    id: uuid.UUID,
    payload: ApprovalEditRequest,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
    approval_service: ApprovalService = Depends(get_approval_service),
) -> ApprovalTaskSchema:
    _subject, _session = subject_session
    task = await approval_service.decide(id, "edit", payload.final_body, payload.human_note)
    return _to_schema(task)


@router.post("/{id}/reject")
async def reject(
    id: uuid.UUID,
    payload: ApprovalRejectRequest,
    subject_session: tuple[Subject, AsyncSession] = Depends(require_capability(_CAPABILITY)),
    approval_service: ApprovalService = Depends(get_approval_service),
) -> ApprovalTaskSchema:
    _subject, _session = subject_session
    task = await approval_service.decide(id, "reject", None, payload.human_note)
    return _to_schema(task)
