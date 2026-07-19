from datetime import UTC, datetime
from uuid import uuid4

from fastapi.routing import APIRoute

from orna_atlas.app.modules.collections.router import router as collections_router
from orna_atlas.app.modules.collections.schemas import CollectionDetailRead
from orna_atlas.app.modules.media.schemas import PublicMediaAssetRead
from orna_atlas.app.modules.sessions.router import router as sessions_router
from orna_atlas.app.modules.sessions.schemas import (
    PublicBirdVocalPartRead,
    PublicSessionAnnotationRead,
    PublicSessionRead,
    SessionDetailRead,
)


def _route(router, path: str, method: str) -> APIRoute:
    return next(
        route
        for route in router.routes
        if isinstance(route, APIRoute) and route.path == path and method in route.methods
    )


def test_public_session_models_are_allowlists_without_internal_metadata() -> None:
    forbidden_session_fields = {"metadata", "created_at", "updated_at"}
    forbidden_asset_fields = {
        "metadata",
        "checksum",
        "size_bytes",
        "source_asset_id",
        "archived_at",
        "created_at",
        "storage_key",
        "processing_jobs",
    }

    assert forbidden_session_fields.isdisjoint(PublicSessionRead.model_fields)
    assert forbidden_session_fields.isdisjoint(SessionDetailRead.model_fields)
    assert forbidden_asset_fields.isdisjoint(PublicMediaAssetRead.model_fields)
    assert "metadata" not in PublicBirdVocalPartRead.model_fields
    assert "metadata" not in PublicSessionAnnotationRead.model_fields


def test_public_session_serialization_drops_internal_canary_values() -> None:
    canary = "internal-canary-must-not-leak"
    session_id = uuid4()
    payload = PublicSessionRead.model_validate(
        {
            "id": session_id,
            "location_id": uuid4(),
            "slug": "public-session",
            "title": "Public session",
            "description": None,
            "recorded_at": datetime.now(UTC),
            "access_level": "public",
            "metadata": {"internal_note": canary},
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "media_assets": [
                {
                    "id": uuid4(),
                    "session_id": session_id,
                    "kind": "streaming_rendition",
                    "mime_type": "application/vnd.apple.mpegurl",
                    "processing_status": "ready",
                    "duration_seconds": 60,
                    "storage_key": canary,
                    "metadata": {"raw_error": canary},
                    "checksum": canary,
                }
            ],
        }
    ).model_dump(mode="json")

    assert canary not in str(payload)
    assert "metadata" not in payload
    assert "storage_key" not in payload["media_assets"][0]


def test_public_collection_model_omits_internal_metadata_and_timestamps() -> None:
    assert {"metadata", "created_at", "updated_at"}.isdisjoint(
        CollectionDetailRead.model_fields
    )
    assert CollectionDetailRead.model_fields["sessions"].annotation == list[PublicSessionRead]


def test_public_routes_use_public_allowlist_models() -> None:
    assert _route(sessions_router, "/sessions", "GET").response_model == list[PublicSessionRead]
    assert (
        _route(sessions_router, "/sessions/{locator}", "GET").response_model
        is SessionDetailRead
    )
    assert (
        _route(collections_router, "/collections/{slug}", "GET").response_model
        is CollectionDetailRead
    )
