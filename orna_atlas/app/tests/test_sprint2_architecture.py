from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from orna_atlas.app.core.domain_types import CoordinateVisibility
from orna_atlas.app.modules.locations import repository as locations_repository
from orna_atlas.app.modules.locations import service as locations_service
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.schemas import LocationCreate, LocationUpdate
from orna_atlas.app.modules.media.models import MediaAsset, ProcessingJob
from orna_atlas.app.modules.media.schemas import MediaAssetCreate
from orna_atlas.app.modules.sessions.models import BirdVocalPart, RecordingSession
from orna_atlas.app.modules.sessions.schemas import SessionCreate


def test_legacy_visibility_maps_to_canonical_enum() -> None:
    location = LocationCreate(
        slug="legacy",
        name="Legacy",
        exact_latitude=10,
        exact_longitude=20,
        public_latitude=10.1,
        public_longitude=20.1,
        coordinate_visibility="public_only",
    )

    assert location.coordinate_visibility is CoordinateVisibility.APPROXIMATE_PUBLIC


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            LocationCreate,
            {
                "slug": "bad-visibility",
                "name": "Bad visibility",
                "exact_latitude": 10,
                "exact_longitude": 20,
                "coordinate_visibility": "unknown",
            },
        ),
        (
            LocationCreate,
            {
                "slug": "bad-timezone",
                "name": "Bad timezone",
                "exact_latitude": 10,
                "exact_longitude": 20,
                "timezone": "Mars/Olympus",
            },
        ),
        (
            SessionCreate,
            {
                "location_id": "00000000-0000-0000-0000-000000000001",
                "slug": "bad-access",
                "title": "Bad access",
                "recorded_at": "2026-01-01T00:00:00Z",
                "access_level": "unknown",
            },
        ),
        (MediaAssetCreate, {"storage_key": "asset.wav", "kind": "unknown"}),
    ],
)
def test_unknown_domain_states_are_rejected(schema: type, payload: dict) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(payload)


def test_model_metadata_contains_domain_constraints() -> None:
    names = {
        constraint.name
        for table in (Location, RecordingSession, MediaAsset, ProcessingJob, BirdVocalPart)
        for constraint in table.__table__.constraints
    }

    assert {
        "ck_locations_coordinate_visibility",
        "ck_sessions_access_level",
        "ck_media_assets_processing_status",
        "ck_processing_jobs_status",
        "ck_bird_parts_interval",
    } <= names


@pytest.mark.asyncio
async def test_repository_flushes_without_owning_transaction() -> None:
    db = AsyncMock()
    db.add = MagicMock()
    data = LocationCreate(
        slug="transaction-owner",
        name="Transaction owner",
        exact_latitude=10,
        exact_longitude=20,
    )

    await locations_repository.create_location(db, data)

    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_commits_once_before_cache_invalidation(monkeypatch) -> None:
    events: list[str] = []
    db = AsyncMock()
    location = AsyncMock()

    async def persist(_session, _data):
        events.append("flushed")
        return location

    async def commit():
        events.append("committed")

    async def invalidate():
        events.append("invalidated")

    db.commit.side_effect = commit
    monkeypatch.setattr(
        locations_service.repository,
        "get_location_by_slug_for_admin",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(locations_service.repository, "create_location", persist)
    monkeypatch.setattr(locations_service, "invalidate_atlas_cache", invalidate)
    data = LocationCreate(
        slug="service-owner",
        name="Service owner",
        exact_latitude=10,
        exact_longitude=20,
    )

    await locations_service.create_location(db, data)

    assert events == ["flushed", "committed", "invalidated"]
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_location_update_requires_coordinates_when_switching_to_approximate(monkeypatch) -> None:
    location_id = uuid4()
    location = SimpleNamespace(
        id=location_id,
        slug="exact-location",
        public_latitude=None,
        public_longitude=None,
        coordinate_visibility=CoordinateVisibility.EXACT_PUBLIC,
    )
    persist = AsyncMock()
    monkeypatch.setattr(
        locations_service,
        "require_location_for_admin",
        AsyncMock(return_value=location),
    )
    monkeypatch.setattr(locations_service.repository, "update_location", persist)

    with pytest.raises(HTTPException) as exc_info:
        await locations_service.update_location(
            AsyncMock(),
            location_id,
            LocationUpdate(coordinate_visibility=CoordinateVisibility.APPROXIMATE_PUBLIC),
        )

    assert exc_info.value.status_code == 422
    persist.assert_not_awaited()


def test_seed_uses_canonical_coordinate_visibility_values() -> None:
    from orna_atlas.app.seed_atlas import SEED_LOCATIONS

    assert {item["coordinate_visibility"] for item in SEED_LOCATIONS} <= {
        visibility.value for visibility in CoordinateVisibility
    }


def test_placeholder_module_files_are_removed() -> None:
    placeholders = [
        path
        for path in Path("orna_atlas/app/modules").rglob("*.py")
        if path.name != "__init__.py" and path.stat().st_size == 0
    ]

    assert placeholders == []
