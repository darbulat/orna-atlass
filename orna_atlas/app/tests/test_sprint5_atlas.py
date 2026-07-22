from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from orna_atlas.app.core.domain_errors import ValidationError
from orna_atlas.app.main import app
from orna_atlas.app.modules.atlas import service
from orna_atlas.app.modules.locations.models import Location


def test_sprint5_routes_are_registered() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/atlas/points" in schema["paths"]
    assert "/api/v1/search" in schema["paths"]

    points_params = schema["paths"]["/api/v1/atlas/points"]["get"]["parameters"]
    parameter_names = {param["name"] for param in points_params}
    assert {"bbox", "zoom", "habitat", "time_mode", "limit"} <= parameter_names


def test_atlas_bbox_validation_rejects_invalid_ranges() -> None:
    with pytest.raises(ValidationError):
        service.parse_bbox("-181,-10,10,10")

    with pytest.raises(ValidationError):
        service.parse_bbox("10,20,30,0")

    assert service.parse_bbox("170,-10,-170,10").east == -170


def test_atlas_point_teases_published_members_only_session_without_media_or_exact_coordinates() -> None:
    now = datetime.now(UTC)
    location = SimpleNamespace(
        id=uuid4(),
        slug="member-marsh",
        name="Member Marsh",
        description=None,
        country_code="EE",
        region="Laanemaa",
        habitat="wetland",
        latitude=58.91,
        longitude=23.72,
        timezone="Europe/Tallinn",
        sensitivity_level="protected",
        coordinate_visibility="approximate_public",
        sessions=[
            SimpleNamespace(
                id=uuid4(),
                slug="member-marsh-long-form",
                title="Member Marsh Long Form",
                recorded_at=now,
                duration_seconds=7200,
                access_level="members_only",
                publication_status="published",
            )
        ],
    )

    payload = service.point_from_location(location, include_locked=True).model_dump(mode="json")

    assert payload["session_count"] == 1
    assert payload["latest_session"]["access_level"] == "members_only"
    assert set(payload["latest_session"]) == {
        "id", "slug", "title", "recorded_at", "duration_seconds", "access_level"
    }
    assert "exact_latitude" not in payload
    assert "media_assets" not in payload["latest_session"]


def test_mixed_location_keeps_its_public_preview_when_a_newer_member_session_exists() -> None:
    now = datetime.now(UTC)
    location = SimpleNamespace(
        id=uuid4(),
        slug="mixed-marsh",
        name="Mixed Marsh",
        description=None,
        country_code="EE",
        region="Laanemaa",
        habitat="wetland",
        latitude=58.91,
        longitude=23.72,
        timezone="Europe/Tallinn",
        sensitivity_level="normal",
        coordinate_visibility="exact_public",
        sessions=[
            SimpleNamespace(
                id=uuid4(),
                slug="new-member-session",
                title="New Member Session",
                recorded_at=now,
                duration_seconds=7200,
                access_level="members_only",
                publication_status="published",
            ),
            SimpleNamespace(
                id=uuid4(),
                slug="public-preview",
                title="Public Preview",
                recorded_at=now - timedelta(days=1),
                duration_seconds=1800,
                access_level="public",
                publication_status="published",
            ),
        ],
    )

    payload = service.point_from_location(location, include_locked=True).model_dump(mode="json")

    assert payload["session_count"] == 2
    assert payload["latest_session"]["slug"] == "public-preview"
    assert payload["latest_session"]["access_level"] == "public"


def test_protected_location_uses_public_coordinates() -> None:
    now = datetime.now(UTC)
    location = SimpleNamespace(
        id=uuid4(),
        slug="protected-marsh",
        name="Protected Marsh",
        description=None,
        country_code="EE",
        region="Laanemaa",
        habitat="wetland",
        latitude=58.91,
        longitude=23.72,
        timezone="Europe/Tallinn",
        sensitivity_level="protected",
        sessions=[
            SimpleNamespace(
                id=uuid4(),
                slug="protected-marsh-dawn",
                title="Protected Marsh Dawn",
                recorded_at=now,
                duration_seconds=1800,
                access_level="public",
            )
        ],
    )

    payload = service.point_from_location(location).model_dump(mode="json")

    assert payload["latitude"] == 58.91
    assert payload["longitude"] == 23.72
    assert payload["sensitivity_level"] == "protected"


async def test_search_trims_short_queries_and_maps_locations(monkeypatch) -> None:
    calls = []
    location_id = uuid4()

    async def fake_search(session, *, query, limit, offset):
        calls.append((query, limit, offset))
        location = Location(
            id=location_id,
            slug="oak-forest",
            name="Oak Forest",
            region="Vidzeme",
            country_code="LV",
            habitat="forest",
            exact_latitude=57.3,
            exact_longitude=25.2,
            public_latitude=None,
            public_longitude=None,
            coordinate_visibility="exact_public",
            sensitivity_level="none",
            timezone="Europe/Riga",
        )
        location.sessions = []
        return [location]

    monkeypatch.setattr(service.repository, "search_locations_and_sessions", fake_search)

    assert await service.search(SimpleNamespace(), query="o", limit=5, offset=0) == []

    results = await service.search(SimpleNamespace(), query=" oak ", limit=5, offset=2)

    assert calls == [("oak", 5, 2)]
    assert results[0].type == "location"
    assert results[0].id == location_id
    assert results[0].slug == "oak-forest"
    assert results[0].atlas_point is not None
    assert results[0].atlas_point.slug == "oak-forest"
    assert results[0].atlas_point.timezone == "Europe/Riga"
