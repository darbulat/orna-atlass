from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.errors import register_error_handlers
from orna_atlas.app.core.logging import RequestLoggingMiddleware, configure_logging
from orna_atlas.app.core.metrics import metrics_response
from orna_atlas.app.core.security import public_jwks
from orna_atlas.app.db.session import engine
from orna_atlas.app.integrations.redis import get_redis_client
from orna_atlas.app.modules.admin.router import router as admin_router
from orna_atlas.app.modules.analytics.router import router as analytics_router
from orna_atlas.app.modules.auth.router import router as auth_router
from orna_atlas.app.modules.atlas.router import router as atlas_router
from orna_atlas.app.modules.collections.router import router as collections_router
from orna_atlas.app.modules.locations.router import router as locations_router
from orna_atlas.app.modules.library.router import router as library_router
from orna_atlas.app.modules.media.router import router as media_router
from orna_atlas.app.modules.memberships.router import router as memberships_router
from orna_atlas.app.modules.sessions.router import router as sessions_router
from orna_atlas.app.modules.users.router import router as users_router

class DependencyStatus(BaseModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    api: DependencyStatus
    postgres: DependencyStatus
    redis: DependencyStatus


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    # Fail deployment at process startup rather than serving an unusable auth
    # configuration or discovering malformed rotation material on the first request.
    if settings.auth_signing_algorithm == "RS256":
        public_jwks()
    app = FastAPI(title=settings.app_name)
    recovery_paths = {
        f"{settings.api_prefix}/auth/email-verification/request",
        f"{settings.api_prefix}/auth/email-verification/confirm",
        f"{settings.api_prefix}/auth/password-reset/request",
        f"{settings.api_prefix}/auth/password-reset/confirm",
    }
    optional_auth_operations = {
        (f"{settings.api_prefix}/sessions", "get"),
        (f"{settings.api_prefix}/sessions/{{locator}}", "get"),
        (f"{settings.api_prefix}/sessions/{{session_id}}/playback-grants", "post"),
    }

    @app.middleware("http")
    async def prevent_recovery_response_caching(request: Request, call_next):
        response = await call_next(request)
        if request.url.path in recovery_paths:
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    confirmation_errors = {
        f"{settings.api_prefix}/auth/email-verification/confirm": (
            "Invalid or expired email verification token"
        ),
        f"{settings.api_prefix}/auth/password-reset/confirm": (
            "Invalid or expired password reset token"
        ),
    }

    @app.exception_handler(RequestValidationError)
    async def sanitize_recovery_confirmation_validation(
        request: Request, exc: RequestValidationError
    ):
        detail = confirmation_errors.get(request.url.path)
        if detail is not None:
            return JSONResponse(
                status_code=400,
                content={"detail": detail},
                headers={"Cache-Control": "no-store"},
            )
        return await request_validation_exception_handler(request, exc)

    app.include_router(analytics_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(memberships_router, prefix=settings.api_prefix)
    app.include_router(users_router, prefix=settings.api_prefix)
    app.include_router(admin_router, prefix=settings.api_prefix)
    app.include_router(atlas_router, prefix=settings.api_prefix)
    app.include_router(collections_router, prefix=settings.api_prefix)
    app.include_router(locations_router, prefix=settings.api_prefix)
    app.include_router(library_router, prefix=settings.api_prefix)
    app.include_router(media_router, prefix=settings.api_prefix)
    app.include_router(sessions_router, prefix=settings.api_prefix)

    def custom_openapi():
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        for path in confirmation_errors:
            schema["paths"][path]["post"]["responses"].pop("422", None)
        optional_security = [{}, {"HTTPBearer": []}, {"APIKeyCookie": []}]
        for path, method in optional_auth_operations:
            schema["paths"][path][method]["security"] = optional_security
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
    return app


app = create_app()


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return metrics_response()


@app.get("/.well-known/jwks.json", include_in_schema=False)
async def jwks() -> dict[str, list[dict[str, object]]]:
    return public_jwks()


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    postgres = DependencyStatus(status="ok")
    redis = DependencyStatus(status="ok")

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health endpoint must report dependency errors.
        postgres = DependencyStatus(status="error", detail=exc.__class__.__name__)

    redis_client = get_redis_client()
    try:
        await redis_client.ping()
    except Exception as exc:  # noqa: BLE001 - health endpoint must report dependency errors.
        redis = DependencyStatus(status="error", detail=exc.__class__.__name__)
    finally:
        await redis_client.aclose()

    overall_status: Literal["ok", "degraded"] = (
        "ok" if postgres.status == "ok" and redis.status == "ok" else "degraded"
    )
    return HealthResponse(
        status=overall_status,
        api=DependencyStatus(status="ok"),
        postgres=postgres,
        redis=redis,
    )
