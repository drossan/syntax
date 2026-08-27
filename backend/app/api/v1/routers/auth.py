"""app.api.v1.routers.auth — endpoints de autenticación (contrato `api-contract.yaml`).

Delega toda la lógica en `auth_service` (dominio) + `app.core.security`; el router solo traduce
HTTP↔dominio (valida con schemas, llama al servicio, construye la respuesta) — cero `try/except`
local, cero lógica de negocio (task 03: todos los errores viajan por el envelope problem+json).
"""

from typing import cast

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginTenantSelection,
    Me,
    MeUser,
    ResetPasswordRequest,
    SelectTenantRequest,
    SwitchTenantRequest,
    TenantChoice,
    TokenResponse,
)
from app.core.config import Settings, get_settings
from app.core.deps import get_auth_service, get_current_subject, get_db_session, oauth2_scheme
from app.core.security import JWT_ALGORITHM
from app.domain.entities.identity import Subject
from app.domain.errors import NotFound
from app.domain.services.auth_service import AuthResult, AuthService, IdentitySelection
from app.infra.db.repositories import (
    SqlAlchemyUserRepository,
    SqlAlchemyUserTenantMembershipRepository,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE_NAME = "refresh_token"  # noqa: S105 — nombre de cookie, no un secreto


def _cookie_kwargs(settings: Settings) -> dict[str, object]:
    """`secure` solo fuera de `development` (permite probar en local sin TLS)."""
    return {
        "httponly": True,
        "secure": settings.app_env != "development",
        "samesite": "lax",
    }


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(_REFRESH_COOKIE_NAME, token, **_cookie_kwargs(settings))  # type: ignore[arg-type]


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(_REFRESH_COOKIE_NAME, **_cookie_kwargs(settings))  # type: ignore[arg-type]


def _token_response(result: AuthResult, settings: Settings) -> TokenResponse:
    return TokenResponse(access_token=result.access_token, expires_in=settings.jwt_access_ttl)


@router.post("/login")
async def login(
    payload: LoginRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> TokenResponse | LoginTenantSelection:
    outcome = await auth_service.login(
        payload.email,
        payload.password,
        secret=settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
        ttl=settings.jwt_access_ttl,
    )
    if isinstance(outcome, IdentitySelection):
        return LoginTenantSelection(
            identity_token=outcome.identity_token,
            tenants=[
                TenantChoice(id=t.tenant_id, slug=t.slug, name=t.name) for t in outcome.tenants
            ],
        )
    _set_refresh_cookie(response, outcome.refresh_token, settings)
    return _token_response(outcome, settings)


@router.post("/select-tenant")
async def select_tenant(
    payload: SelectTenantRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    result = await auth_service.select_tenant(
        payload.identity_token,
        payload.tenant_id,
        secret=settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
        ttl=settings.jwt_access_ttl,
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _token_response(result, settings)


@router.post("/switch-tenant")
async def switch_tenant(
    payload: SwitchTenantRequest,
    response: Response,
    access_token: str | None = Depends(oauth2_scheme),
    _subject: Subject = Depends(get_current_subject),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    # get_current_subject (Depends) ya rechazó `None` con 401 antes de llegar aquí — narrowing puro.
    result = await auth_service.switch_tenant(
        cast(str, access_token),
        payload.tenant_id,
        secret=settings.jwt_secret,
        algorithm=JWT_ALGORITHM,
        ttl=settings.jwt_access_ttl,
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _token_response(result, settings)


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    token = request.cookies.get(_REFRESH_COOKIE_NAME, "")
    result = await auth_service.refresh(
        token, secret=settings.jwt_secret, algorithm=JWT_ALGORITHM, ttl=settings.jwt_access_ttl
    )
    _set_refresh_cookie(response, result.refresh_token, settings)
    return _token_response(result, settings)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    response: Response,
    _subject: Subject = Depends(get_current_subject),
    auth_service: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> None:
    token = request.cookies.get(_REFRESH_COOKIE_NAME)
    if token:
        await auth_service.logout(token)
    _clear_refresh_cookie(response, settings)


@router.get("/me")
async def me(
    subject: Subject = Depends(get_current_subject),
    session: AsyncSession = Depends(get_db_session),
    auth_service: AuthService = Depends(get_auth_service),
) -> Me:
    user = await SqlAlchemyUserRepository(session).get(subject.id)
    membership = await SqlAlchemyUserTenantMembershipRepository(session).get(
        subject.id, subject.tenant_id
    )
    if user is None or membership is None:
        # Race rara: el user/membership se borró entre emitir el token y esta request.
        raise NotFound("el sujeto autenticado ya no existe", code="auth.subject_not_found")
    available = await auth_service.eligible_tenants(subject.id)
    return Me(
        user=MeUser(id=user.id, email=user.email, status=membership.status.value, roles=[]),
        active_tenant_id=subject.tenant_id,
        capabilities=[
            {"capability": capability, "scope": scope} for capability, scope in subject.capabilities
        ],
        available_tenants=[
            TenantChoice(id=t.tenant_id, slug=t.slug, name=t.name) for t in available
        ],
    )


@router.post("/password/forgot", status_code=202)
async def forgot_password(
    payload: ForgotPasswordRequest, auth_service: AuthService = Depends(get_auth_service)
) -> None:
    await auth_service.forgot_password(payload.email)


@router.post("/password/reset", status_code=204)
async def reset_password(
    payload: ResetPasswordRequest, auth_service: AuthService = Depends(get_auth_service)
) -> None:
    await auth_service.reset_password(payload.token, payload.new_password)


@router.post("/password/change", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    subject: Subject = Depends(get_current_subject),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    await auth_service.change_password(subject.id, payload.current_password, payload.new_password)
