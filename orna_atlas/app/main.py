from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from orna_atlas.app.core.config import get_settings
from orna_atlas.app.core.errors import register_error_handlers
from orna_atlas.app.core.logging import configure_logging
from orna_atlas.app.db.session import engine
from orna_atlas.app.integrations.redis import get_redis_client
from orna_atlas.app.modules.admin.router import router as admin_router
from orna_atlas.app.modules.atlas.router import router as atlas_router
from orna_atlas.app.modules.locations.router import router as locations_router
from orna_atlas.app.modules.sessions.router import router as sessions_router


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
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(admin_router, prefix=settings.api_prefix)
    app.include_router(atlas_router, prefix=settings.api_prefix)
    app.include_router(locations_router, prefix=settings.api_prefix)
    app.include_router(sessions_router, prefix=settings.api_prefix)
    return app


app = create_app()


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
