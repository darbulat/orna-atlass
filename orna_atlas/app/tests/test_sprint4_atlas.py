from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from orna_atlas.app.main import app
from orna_atlas.app.modules.atlas import service


def test_sprint4_routes_are_registered() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/atlas/points" in schema["paths"]
    assert "/api/v1/locations/{locator}" in schema["paths"]
    assert "/api/v1/search" in schema["paths"]


def test_atlas_cache_key_is_stable_for_normalized_filters() -> None:
    bbox = service.parse_bbox("170,-10,-170,10")
    first = service.stable_cache_key(
        bbox=bbox,
        zoom=4,
        habitats=service.normalize_habitats(["Wetland", "forest", "wetland"]),
        time_mode="local",
        limit=100,
    )
    second = service.stable_cache_key(
        bbox=bbox,
        zoom=4,
        habitats=service.normalize_habitats(["forest", "wetland"]),
        time_mode="local",
        limit=100,
    )

    assert first == second
    assert first.startswith("atlas:points:")
    assert service.parse_bbox("170,-10,-170,10").west == 170


def test_atlas_point_uses_public_coordinates_and_latest_public_session() -> None:
    now = datetime.now(UTC)
    location = SimpleNamespace(
        id=uuid4(),
        slug="island-wetland",
        name="Island Wetland",
        description="A protected wetland.",
        country_code="NZ",
        region="South Island",
        habitat="wetland",
        latitude=-45.2,
        longitude=169.1,
        timezone="Pacific/Auckland",
        sensitivity_level="high",
        sessions=[
            SimpleNamespace(
                id=uuid4(),
                slug="private-draft",
                title="Draft",
                recorded_at=now,
                duration_seconds=120,
                access_level="draft",
            ),
            SimpleNamespace(
                id=uuid4(),
                slug="dawn-public",
                title="Dawn Public",
                recorded_at=now,
                duration_seconds=3600,
                access_level="public",
            ),
        ],
    )

    point = service.point_from_location(location)

    assert point is not None
    payload = point.model_dump(mode="json")
    assert payload["latitude"] == -45.2
    assert payload["latest_session"]["slug"] == "dawn-public"
    assert payload["session_count"] == 1
    assert "exact_latitude" not in payload
