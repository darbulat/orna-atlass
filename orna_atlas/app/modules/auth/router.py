from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.rate_limit import auth_rate_limit
from orna_atlas.app.core.security import ACCESS_COOKIE, REFRESH_COOKIE
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.admin.repository import add_audit_event
from orna_atlas.app.modules.auth import service
from orna_atlas.app.modules.auth.schemas import (
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    TokenResponse,
)
from orna_atlas.app.modules.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, payload: TokenResponse, refresh_token: str) -> None:
    settings = get_settings()
    common = {"httponly": True, "secure": settings.auth_cookie_secure, "samesite": "lax"}
    response.set_cookie(
        ACCESS_COOKIE, payload.access_token, max_age=settings.access_token_ttl_seconds, **common
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        path=f"{settings.api_prefix}/auth",
        **common,
    )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limit)],
)
async def register(data: RegisterRequest, session: AsyncSession = Depends(get_db_session)) -> UserRead:
    return UserRead.model_validate(await service.register(session, data))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def login(
    data: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    user = await service.authenticate(session, data)
    await add_audit_event(
        session,
        event_type="auth.login_succeeded",
        subject_type="user",
        subject_id=str(user.id),
        actor_user_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    payload, refresh_token = await service.issue_token_pair(session, user)
    _set_auth_cookies(response, payload, refresh_token)
    return payload


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token required")
    payload, replacement = await service.rotate_refresh_token(session, refresh_token)
    _set_auth_cookies(response, payload, replacement)
    return payload


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    session: AsyncSession = Depends(get_db_session),
) -> LogoutResponse:
    await service.logout(session, refresh_token)
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE, path=f"{get_settings().api_prefix}/auth")
    return LogoutResponse()
