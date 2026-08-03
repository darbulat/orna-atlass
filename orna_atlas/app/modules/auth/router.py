import hmac
import logging
import secrets
from typing import Literal
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from orna_atlas.app.core.config import Settings, get_settings
from orna_atlas.app.core.domain_errors import (
    AuthenticationError,
    ConflictError,
    ServiceUnavailableError,
)
from orna_atlas.app.core.rate_limit import auth_rate_limit
from orna_atlas.app.core.security import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    CurrentUser,
    get_current_user,
    get_optional_active_user,
)
from orna_atlas.app.db.session import get_db_session
from orna_atlas.app.modules.auth import magic, oauth, service
from orna_atlas.app.modules.auth.oauth import OAuthProvider
from orna_atlas.app.modules.auth.schemas import (
    AccountEmailAccepted,
    AccountRecoveryError,
    AccountTokenRequest,
    EmailVerificationResponse,
    LoginRequest,
    LogoutResponse,
    MagicLinkAccepted,
    MagicLinkRequest,
    OAuthLinkCancelledResponse,
    OAuthLinkConfirmRequest,
    OAuthLinkPendingResponse,
    OAuthLinkResponse,
    OAuthProvidersResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetResponse,
    RegisterRequest,
    TokenResponse,
)
from orna_atlas.app.modules.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _oauth_state_cookie(provider: OAuthProvider) -> str:
    return f"orna_oauth_state_{provider}"


def _oauth_cookie_samesite(provider: OAuthProvider) -> Literal["lax", "none"]:
    return "none" if provider == "apple" else "lax"


def _clear_oauth_state_cookie(
    response: Response,
    provider: OAuthProvider,
    settings: Settings,
) -> None:
    response.delete_cookie(
        _oauth_state_cookie(provider),
        path=f"{settings.api_prefix}/auth/oauth/{provider}/callback",
        secure=settings.auth_cookie_secure or provider == "apple",
        httponly=True,
        samesite=_oauth_cookie_samesite(provider),
    )


def _set_oauth_link_cookie(response: Response, raw_intent: str, settings: Settings) -> None:
    response.set_cookie(
        oauth.OAUTH_LINK_COOKIE,
        raw_intent,
        max_age=oauth.OAUTH_LINK_TTL_SECONDS,
        path=f"{settings.api_prefix}/auth",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _clear_oauth_link_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        oauth.OAUTH_LINK_COOKIE,
        path=f"{settings.api_prefix}/auth",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _oauth_link_error_response(status_code: int, detail: str) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content={"detail": detail})
    response.headers["Cache-Control"] = "no-store"
    _clear_oauth_link_cookie(response, get_settings())
    return response


async def _mark_pending_oauth_link_reauthenticated(
    request: Request, user_id: UUID
) -> None:
    raw_intent = request.cookies.get(oauth.OAUTH_LINK_COOKIE)
    if not raw_intent:
        return
    try:
        await oauth.mark_oauth_link_reauthenticated(raw_intent, user_id)
    except ServiceUnavailableError:
        logger.warning("OAuth link reauthentication marker unavailable")


async def _require_oauth_link_origin(request: Request) -> None:
    configured = urlsplit(get_settings().oauth_frontend_url)
    expected = f"{configured.scheme}://{configured.netloc}"
    if request.headers.get("origin") != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid request origin",
        )


def _frontend_redirect(return_to: str, *, provider: str, error: str | None = None) -> str:
    settings = get_settings()
    configured = urlsplit(settings.oauth_frontend_url)
    target = urlsplit(return_to)
    query = dict(parse_qsl(target.query, keep_blank_values=True))
    query["oauth_provider"] = provider
    query["oauth"] = "error" if error else "success"
    if error:
        query["oauth_error"] = error
    return urlunsplit(
        (configured.scheme, configured.netloc, target.path, urlencode(query), "")
    )


def _magic_frontend_redirect(
    return_to: str, *, outcome: str = "login", error: str | None = None
) -> str:
    settings = get_settings()
    configured = urlsplit(settings.oauth_frontend_url)
    target = urlsplit(magic.safe_return_to(return_to))
    query = dict(parse_qsl(target.query, keep_blank_values=True))
    query["magic"] = "error" if error else outcome
    if error:
        query["magic_error"] = error
    return urlunsplit(
        (configured.scheme, configured.netloc, target.path, urlencode(query), "")
    )


def _set_auth_cookies(response: Response, payload: TokenResponse, refresh_token: str) -> None:
    settings = get_settings()
    common = {"httponly": True, "secure": settings.auth_cookie_secure, "samesite": "lax"}
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        ACCESS_COOKIE, payload.access_token, max_age=settings.access_token_ttl_seconds, **common
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 86400,
        # Catalog endpoints must distinguish genuine anonymous requests from
        # expired access cookies that remain recoverable. HttpOnly/SameSite
        # protect the token while root scope lets those endpoints observe it.
        path="/",
        **common,
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE, path="/")


@router.post(
    "/email-verification/request",
    response_model=AccountEmailAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(auth_rate_limit)],
)
async def request_email_verification(
    response: Response,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AccountEmailAccepted:
    await service.request_email_verification(session, UUID(current_user.id))
    response.headers["Cache-Control"] = "no-store"
    return AccountEmailAccepted()


@router.post(
    "/email-verification/confirm",
    response_model=EmailVerificationResponse,
    responses={status.HTTP_400_BAD_REQUEST: {"model": AccountRecoveryError}},
    dependencies=[Depends(auth_rate_limit)],
)
async def confirm_email_verification(
    data: AccountTokenRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> EmailVerificationResponse:
    try:
        await service.confirm_email_verification(session, data.token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired email verification token",
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    return EmailVerificationResponse(status="verified")


@router.post(
    "/password-reset/request",
    response_model=AccountEmailAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(auth_rate_limit)],
)
async def request_password_reset(
    data: PasswordResetRequest,
    response: Response,
    background_tasks: BackgroundTasks,
) -> AccountEmailAccepted:
    background_tasks.add_task(service.deliver_password_reset, str(data.email))
    response.headers["Cache-Control"] = "no-store"
    return AccountEmailAccepted()


@router.post(
    "/password-reset/confirm",
    response_model=PasswordResetResponse,
    responses={status.HTTP_400_BAD_REQUEST: {"model": AccountRecoveryError}},
    dependencies=[Depends(auth_rate_limit)],
)
async def confirm_password_reset(
    data: PasswordResetConfirm,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> PasswordResetResponse | Response:
    try:
        await service.confirm_password_reset(session, data.token, data.password)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token",
        ) from exc
    except ServiceUnavailableError as exc:
        error_response = JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": exc.detail},
        )
        _clear_auth_cookies(error_response)
        error_response.headers["Cache-Control"] = "no-store"
        return error_response
    _clear_auth_cookies(response)
    response.headers["Cache-Control"] = "no-store"
    return PasswordResetResponse(status="password_reset")


@router.get("/oauth/providers", response_model=OAuthProvidersResponse)
async def oauth_providers(response: Response) -> OAuthProvidersResponse:
    response.headers["Cache-Control"] = "no-store"
    return OAuthProvidersResponse(providers=oauth.configured_providers(get_settings()))


@router.get("/oauth/link/pending", response_model=OAuthLinkPendingResponse)
async def pending_oauth_link(
    response: Response,
    raw_intent: str | None = Cookie(default=None, alias=oauth.OAUTH_LINK_COOKIE),
    current_user: CurrentUser | None = Depends(get_optional_active_user),
) -> OAuthLinkPendingResponse:
    response.headers["Cache-Control"] = "no-store"
    if not raw_intent:
        return OAuthLinkPendingResponse(pending=False)
    try:
        intent = await oauth.get_oauth_link_intent(raw_intent)
    except AuthenticationError:
        _clear_oauth_link_cookie(response, get_settings())
        return OAuthLinkPendingResponse(pending=False)
    if intent is None:
        _clear_oauth_link_cookie(response, get_settings())
        return OAuthLinkPendingResponse(pending=False)
    current_user_id = UUID(current_user.id) if current_user is not None else None
    ready = (
        current_user_id == intent.target_user_id
        and intent.reauthenticated_user_id == intent.target_user_id
    )
    return OAuthLinkPendingResponse(
        pending=True,
        provider=intent.provider,
        ready=ready,
    )


@router.post(
    "/oauth/link/confirm",
    response_model=OAuthLinkResponse,
    dependencies=[Depends(auth_rate_limit), Depends(_require_oauth_link_origin)],
)
async def confirm_oauth_link(
    data: OAuthLinkConfirmRequest,
    response: Response,
    raw_intent: str | None = Cookie(default=None, alias=oauth.OAUTH_LINK_COOKIE),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> OAuthLinkResponse | JSONResponse:
    del data  # Literal[True] plus extra="forbid" makes confirmation explicit.
    response.headers["Cache-Control"] = "no-store"
    if not raw_intent:
        return _oauth_link_error_response(
            status.HTTP_400_BAD_REQUEST,
            "OAuth link expired",
        )
    try:
        intent = await oauth.consume_oauth_link_intent(raw_intent)
        if intent is None:
            raise AuthenticationError("OAuth link expired")
        await service.link_oauth_identity(
            session,
            current_user_id=UUID(current_user.id),
            intent=intent,
        )
    except AuthenticationError:
        return _oauth_link_error_response(
            status.HTTP_403_FORBIDDEN,
            "OAuth link requires account authentication",
        )
    except ConflictError:
        return _oauth_link_error_response(
            status.HTTP_409_CONFLICT,
            "OAuth link conflict",
        )
    except SQLAlchemyError:
        try:
            await session.rollback()
        except Exception:  # Terminal cookie cleanup must survive a broken DB connection.
            logger.exception("OAuth-link rollback failed")
        return _oauth_link_error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "OAuth link could not be completed",
        )
    _clear_oauth_link_cookie(response, get_settings())
    return OAuthLinkResponse(
        status="linked",
        provider=intent.provider,
        return_to=intent.return_to,
    )


@router.post(
    "/oauth/link/cancel",
    response_model=OAuthLinkCancelledResponse,
    dependencies=[Depends(auth_rate_limit), Depends(_require_oauth_link_origin)],
)
async def cancel_oauth_link(
    response: Response,
    raw_intent: str | None = Cookie(default=None, alias=oauth.OAUTH_LINK_COOKIE),
) -> OAuthLinkCancelledResponse:
    response.headers["Cache-Control"] = "no-store"
    if raw_intent:
        await oauth.cancel_oauth_link_intent(raw_intent)
    _clear_oauth_link_cookie(response, get_settings())
    return OAuthLinkCancelledResponse(status="cancelled")


@router.post(
    "/magic-link/request",
    response_model=MagicLinkAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(auth_rate_limit)],
)
async def request_magic_link(
    data: MagicLinkRequest,
    request: Request,
    response: Response,
) -> MagicLinkAccepted:
    settings = get_settings()
    browser_nonce = secrets.token_urlsafe(32)
    email = str(data.email)
    expected_user_id: UUID | None = None
    raw_intent = request.cookies.get(oauth.OAUTH_LINK_COOKIE)
    if raw_intent:
        try:
            intent = await oauth.get_oauth_link_intent(raw_intent)
        except AuthenticationError:
            intent = None
        if intent is not None:
            email = intent.email
            expected_user_id = intent.target_user_id
    await magic.send_magic_link(
        settings=settings,
        email=email,
        return_to=data.return_to,
        browser_nonce=browser_nonce,
        expected_user_id=expected_user_id,
    )
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        magic.MAGIC_LINK_BROWSER_COOKIE,
        browser_nonce,
        max_age=magic.MAGIC_LINK_TTL_SECONDS,
        path=f"{settings.api_prefix}/auth/magic-link/consume",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return MagicLinkAccepted()


def _clear_magic_browser_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        magic.MAGIC_LINK_BROWSER_COOKIE,
        path=f"{settings.api_prefix}/auth/magic-link/consume",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


async def _rollback_magic_session(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:  # The terminal cookie response must survive a broken DB connection.
        logger.exception("Magic-link rollback failed")


def _magic_unavailable_response(settings: Settings) -> RedirectResponse:
    response = RedirectResponse(
        _magic_frontend_redirect("/membership", error="unavailable"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    _clear_magic_browser_cookie(response, settings)
    return response


@router.get(
    "/magic-link/consume",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    responses={status.HTTP_303_SEE_OTHER: {"description": "Consume one-time link"}},
    dependencies=[Depends(auth_rate_limit)],
)
async def consume_magic_link(
    request: Request,
    token: str = Query(default=""),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    settings = get_settings()
    if not 32 <= len(token) <= 256:
        response = RedirectResponse(
            _magic_frontend_redirect("/membership", error="invalid_or_expired"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
        _clear_magic_browser_cookie(response, settings)
        return response
    try:
        claims = await magic.consume_magic_link(
            token, request.cookies.get(magic.MAGIC_LINK_BROWSER_COOKIE)
        )
        if claims is None:
            response = RedirectResponse(
                _magic_frontend_redirect("/membership", error="invalid_or_expired"),
                status_code=status.HTTP_303_SEE_OTHER,
            )
            _clear_magic_browser_cookie(response, settings)
            return response
        payload, refresh_token, created = await service.authenticate_magic_link(
            session,
            claims["email"],
            expected_user_id=claims.get("expected_user_id"),
        )
        response = RedirectResponse(
            _magic_frontend_redirect(
                claims["return_to"], outcome="signup" if created else "login"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
        _set_auth_cookies(response, payload, refresh_token)
        await _mark_pending_oauth_link_reauthenticated(
            request, UUID(str(payload.user.id))
        )
        _clear_magic_browser_cookie(response, settings)
        return response
    except (AuthenticationError, ServiceUnavailableError):
        response = _magic_unavailable_response(settings)
        await _rollback_magic_session(session)
        return response
    except Exception:
        logger.exception("Magic-link terminal operation failed")
        response = _magic_unavailable_response(settings)
        await _rollback_magic_session(session)
        return response


@router.get(
    "/oauth/{provider}/start",
    response_class=RedirectResponse,
    status_code=status.HTTP_302_FOUND,
    responses={status.HTTP_302_FOUND: {"description": "Redirect to OAuth provider"}},
    dependencies=[Depends(auth_rate_limit)],
)
async def oauth_start(
    provider: OAuthProvider,
    return_to: str | None = Query(default=None, max_length=512),
) -> RedirectResponse:
    settings = get_settings()
    authorization = oauth.create_authorization(provider, settings, return_to=return_to)
    await oauth.register_oauth_state(
        authorization, ttl_seconds=oauth.OAUTH_STATE_TTL_SECONDS
    )
    response = RedirectResponse(authorization.url, status_code=status.HTTP_302_FOUND)
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        _oauth_state_cookie(provider),
        authorization.state,
        max_age=oauth.OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.auth_cookie_secure or provider == "apple",
        samesite=_oauth_cookie_samesite(provider),
        path=f"{settings.api_prefix}/auth/oauth/{provider}/callback",
    )
    return response


async def _complete_oauth_callback(
    provider: OAuthProvider,
    request: Request,
    state: str | None,
    code: str | None,
    error: str | None,
    session: AsyncSession,
) -> RedirectResponse:
    settings = get_settings()
    cookie_name = _oauth_state_cookie(provider)
    stored_state = request.cookies.get(cookie_name)
    if not state or not stored_state or not hmac.compare_digest(state, stored_state):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OAuth state",
        )
    try:
        claims = await oauth.consume_oauth_state(state, expected_provider=provider)
    except ServiceUnavailableError:
        response = RedirectResponse(
            _frontend_redirect("/membership", provider=provider, error="unavailable"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
        _clear_oauth_state_cookie(response, provider, settings)
        return response
    except AuthenticationError:
        response = RedirectResponse(
            _frontend_redirect("/membership", provider=provider, error="failed"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
        _clear_oauth_state_cookie(response, provider, settings)
        return response
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or replayed OAuth state",
        )
    try:
        if error:
            response = RedirectResponse(
                _frontend_redirect(
                    claims["return_to"], provider=provider, error="cancelled"
                ),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        else:
            if not code:
                raise AuthenticationError("OAuth authorization code required")
            identity = await oauth.exchange_code(provider, code, claims, settings)
            payload, refresh_token = await service.authenticate_oauth_identity(session, identity)
            response = RedirectResponse(
                _frontend_redirect(claims["return_to"], provider=provider),
                status_code=status.HTTP_303_SEE_OTHER,
            )
            _set_auth_cookies(response, payload, refresh_token)
            await _mark_pending_oauth_link_reauthenticated(
                request, UUID(str(payload.user.id))
            )
    except service.OAuthLinkRequired as exc:
        try:
            raw_intent = await oauth.register_oauth_link_intent(
                exc.identity,
                target_user_id=exc.target_user_id,
                return_to=claims["return_to"],
            )
        except ServiceUnavailableError:
            response = RedirectResponse(
                _frontend_redirect(
                    claims["return_to"], provider=provider, error="unavailable"
                ),
                status_code=status.HTTP_303_SEE_OTHER,
            )
        else:
            response = RedirectResponse(
                _frontend_redirect(
                    claims["return_to"], provider=provider, error="account_conflict"
                ),
                status_code=status.HTTP_303_SEE_OTHER,
            )
            _set_oauth_link_cookie(response, raw_intent, settings)
    except ConflictError:
        response = RedirectResponse(
            _frontend_redirect(
                claims["return_to"], provider=provider, error="account_conflict"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except ServiceUnavailableError:
        response = RedirectResponse(
            _frontend_redirect(
                claims["return_to"], provider=provider, error="unavailable"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except SQLAlchemyError:
        await session.rollback()
        logger.exception("OAuth database operation failed", extra={"provider": provider})
        response = RedirectResponse(
            _frontend_redirect(
                claims["return_to"], provider=provider, error="unavailable"
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except AuthenticationError:
        response = RedirectResponse(
            _frontend_redirect(claims["return_to"], provider=provider, error="failed"),
            status_code=status.HTTP_303_SEE_OTHER,
        )
    _clear_oauth_state_cookie(response, provider, settings)
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get(
    "/oauth/{provider}/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    responses={status.HTTP_303_SEE_OTHER: {"description": "Return to frontend"}},
    dependencies=[Depends(auth_rate_limit)],
)
async def oauth_callback(
    provider: OAuthProvider,
    request: Request,
    state: str | None = Query(default=None),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    return await _complete_oauth_callback(
        provider, request, state, code, error, session
    )


@router.post(
    "/oauth/apple/callback",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
    responses={status.HTTP_303_SEE_OTHER: {"description": "Return to frontend"}},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "state": {"type": "string"},
                            "code": {"type": "string"},
                            "error": {"type": "string"},
                        },
                    }
                }
            },
        }
    },
    dependencies=[Depends(auth_rate_limit)],
)
async def apple_oauth_callback(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> RedirectResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported OAuth callback content type",
        )
    body = await request.body()
    if len(body) > 16_384:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="OAuth callback payload is too large",
        )
    try:
        form = parse_qs(
            body.decode("utf-8"),
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=5,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth callback payload",
        ) from exc

    def field(name: str) -> str | None:
        values = form.get(name, [])
        if len(values) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid OAuth callback payload",
            )
        return values[0] if values else None

    return await _complete_oauth_callback(
        "apple", request, field("state"), field("code"), field("error"), session
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
    payload, refresh_token = await service.authenticate_password_login(
        session,
        data,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookies(response, payload, refresh_token)
    await _mark_pending_oauth_link_reauthenticated(request, UUID(str(payload.user.id)))
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
    _clear_auth_cookies(response)
    return LogoutResponse()
