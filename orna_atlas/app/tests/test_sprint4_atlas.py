from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from fastapi.testclient import TestClient

from orna_atlas.app.main import app
from orna_atlas.app.modules.atlas import service
from orna_atlas.app.modules.locations.models import Location


def test_sprint4_routes_are_registered() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/atlas/points" in schema["paths"]
    assert "/api/v1/locations/{locator}" in schema["paths"]
    assert "/api/v1/search" in schema["paths"]
    points_params = schema["paths"]["/api/v1/atlas/points"]["get"]["parameters"]
    time_mode = next(param for param in points_params if param["name"] == "time_mode")
    assert time_mode["schema"]["enum"] == ["local", "utc", "dawn"]


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
        metadata_={"source_image": "https://images.example/island-wetland.jpg"},
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
    assert payload["photo_url"] == "https://images.example/island-wetland.jpg"
    assert "exact_latitude" not in payload


def test_atlas_point_rejects_non_http_or_malformed_location_photo_urls() -> None:
    for source_image in (
        "photo.jpg",
        "javascript:alert(1)",
        "https://",
        "https://[broken",
        "https://example.com:bad/photo.jpg",
        "https://host name.example/photo.jpg",
        "https://user:secret@example.com/photo.jpg",
        " https://example.com/photo.jpg",
    ):
        location = cast(Location, SimpleNamespace(metadata_={"source_image": source_image}))
        assert service._normalize_location_photo_url(location) is None

    assert service._normalize_location_photo_url(cast(Location, SimpleNamespace())) is None


async def test_low_zoom_atlas_applies_limit_after_clustering(monkeypatch) -> None:
    requested_limits = []

    async def fake_list_atlas_clusters(session, *, bbox, habitats, zoom, limit):
        requested_limits.append(limit)
        return [
            SimpleNamespace(
                id=f"{zoom}:cluster-{index}",
                latitude=-45.0 + index,
                longitude=169.0,
                count=index + 1,
                habitats=["wetland"],
            )
            for index in range(limit)
        ]

    monkeypatch.setattr(service.repository, "list_atlas_clusters", fake_list_atlas_clusters)

    response = await service.get_atlas_points(
        SimpleNamespace(),
        bbox=None,
        zoom=3,
        habitats=None,
        time_mode="local",
        limit=2,
    )

    assert requested_limits == [2]
    assert response.mode == "clusters"
    assert len(response.points) == 2
