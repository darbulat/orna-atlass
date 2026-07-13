from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from orna_atlas.app.main import app
from orna_atlas.app.modules.atlas import service as atlas_service
from orna_atlas.app.modules.collections import service as collections_service
from orna_atlas.app.modules.locations.models import Location
from orna_atlas.app.modules.locations.schemas import LocationRead
from orna_atlas.app.modules.sessions import service as sessions_service
from orna_atlas.app.modules.sessions.schemas import SessionDetailRead


def test_sprint9_routes_are_registered() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/collections" in schema["paths"]
    assert "/api/v1/collections/{slug}" in schema["paths"]
    assert "/api/v1/sessions/featured" in schema["paths"]
    assert "/api/v1/sessions/{session_id}/bird-parts" in schema["paths"]
    assert "/api/v1/admin/collections" in schema["paths"]
    assert "/api/v1/admin/collections/{collection_id}" in schema["paths"]


def test_location_read_marks_protected_coordinates() -> None:
    now = datetime.now(UTC)
    protected = Location(
        id=uuid4(),
        slug="protected-marsh",
        name="Protected Marsh",
        exact_latitude=57.1567,
        exact_longitude=30.3186,
        public_latitude=57.21,
        public_longitude=30.42,
        coordinate_visibility="public_only",
        sensitivity_level="protected",
        timezone="Europe/Moscow",
        metadata_={},
        created_at=now,
        updated_at=now,
    )
    public = Location(
        id=uuid4(),
        slug="open-forest",
        name="Open Forest",
        exact_latitude=57.9,
        exact_longitude=33.2,
        coordinate_visibility="exact_public",
        sensitivity_level="none",
        timezone="Europe/Moscow",
        metadata_={},
        created_at=now,
        updated_at=now,
    )

    protected_payload = LocationRead.model_validate(protected).model_dump(mode="json")
    public_payload = LocationRead.model_validate(public).model_dump(mode="json")

    assert protected_payload["coordinates_protected"] is True
    assert protected_payload["latitude"] == 57.21
    assert protected_payload["longitude"] == 30.42
    assert "exact_latitude" not in protected_payload
    assert public_payload["coordinates_protected"] is False


def test_location_read_hides_exact_coordinates_for_sensitive_exact_public() -> None:
    now = datetime.now(UTC)
    sensitive = Location(
        id=uuid4(),
        slug="sensitive-but-exact-flag",
        name="Sensitive Exact Flag",
        exact_latitude=57.1567,
        exact_longitude=30.3186,
        public_latitude=57.21,
        public_longitude=30.42,
        coordinate_visibility="exact_public",
        sensitivity_level="protected",
        timezone="Europe/Moscow",
        metadata_={},
        created_at=now,
        updated_at=now,
    )

    payload = LocationRead.model_validate(sensitive).model_dump(mode="json")

    assert payload["coordinates_protected"] is True
    assert payload["latitude"] == 57.21
    assert payload["longitude"] == 30.42
    assert payload["latitude"] != 57.1567


def test_protected_location_point_uses_public_coordinates_only() -> None:
    now = datetime.now(UTC)
    location = SimpleNamespace(
        id=uuid4(),
        slug="protected-marsh",
        name="Protected Marsh",
        description=None,
        country_code="RU",
        region="Pskov Oblast",
        habitat="wetland",
        latitude=57.21,
        longitude=30.42,
        timezone="Europe/Moscow",
        coordinate_visibility="public_only",
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

    point = atlas_service.point_from_location(location)

    assert point is not None
    payload = point.model_dump(mode="json")
    assert payload["latitude"] == 57.21
    assert payload["longitude"] == 30.42
    assert payload["coordinate_visibility"] == "public_only"
    assert payload["sensitivity_level"] == "protected"
    assert "exact_latitude" not in payload


def test_session_detail_includes_bird_parts_from_relationship() -> None:
    now = datetime.now(UTC)
    session_id = uuid4()
    location = SimpleNamespace(
        id=uuid4(),
        slug="misty-wetland",
        name="Misty Wetland",
        description=None,
        country_code="MN",
        region=None,
        habitat="wetland",
        latitude=48.1,
        longitude=107.2,
        public_latitude=48.1,
        public_longitude=107.2,
        coordinate_visibility="exact_public",
        sensitivity_level="none",
        timezone="Asia/Ulaanbaatar",
        metadata_={},
        created_at=now,
        updated_at=now,
    )
    bird_part = SimpleNamespace(
        id=uuid4(),
        species_code="turdus_merula",
        species_common_name="Common blackbird",
        species_scientific_name="Turdus merula",
        starts_at_seconds=12.0,
        ends_at_seconds=18.0,
        confidence=0.9,
        channel=None,
        call_type="song",
        analysis_provider="external-bird-audio-service",
        analysis_model_version="2026-06",
        metadata_={},
    )
    recording = SimpleNamespace(
        id=session_id,
        location_id=location.id,
        slug="misty-dawn",
        title="Misty Dawn",
        description=None,
        recorded_at=now,
        duration_seconds=3600,
        recorder=None,
        weather=None,
        access_level="public",
        processing_status="ready",
        is_featured=True,
        featured_sort_order=0,
        metadata_={"annotations": []},
        created_at=now,
        updated_at=now,
        media_assets=[],
        location=location,
        bird_vocal_parts=[bird_part],
    )

    detail = SessionDetailRead.model_validate(recording).model_dump(mode="json")

    assert detail["bird_parts"]["session_id"] == str(session_id)
    assert detail["bird_parts"]["parts"][0]["species_common_name"] == "Common blackbird"


def test_bird_parts_for_session_returns_empty_payload_without_parts() -> None:
    recording = SimpleNamespace(id=uuid4(), bird_vocal_parts=[])

    payload = sessions_service.bird_parts_for_session(recording).model_dump(mode="json")

    assert payload["parts"] == []


def test_collection_summary_counts_public_sessions_only() -> None:
    collection = SimpleNamespace(
        id=uuid4(),
        slug="dawn-archive",
        title="Dawn Archive",
        description="Dawn journeys",
        sort_order=0,
        location_links=[
            SimpleNamespace(location=SimpleNamespace(coordinate_visibility="exact_public"))
        ],
        session_links=[
            SimpleNamespace(
                session=SimpleNamespace(
                    access_level="public",
                    location=SimpleNamespace(coordinate_visibility="exact_public"),
                )
            ),
            SimpleNamespace(session=SimpleNamespace(access_level="members_only")),
        ],
    )

    summary = collections_service.summary_from_collection(collection).model_dump(mode="json")

    assert summary["session_count"] == 1
    assert summary["location_count"] == 1


def test_collection_detail_includes_summary_counts() -> None:
    now = datetime.now(UTC)
    public_location = SimpleNamespace(coordinate_visibility="exact_public")
    public_session = SimpleNamespace(
        id=uuid4(),
        location_id=uuid4(),
        slug="public-session",
        title="Public Session",
        description=None,
        recorded_at=now,
        duration_seconds=1800,
        recorder=None,
        weather=None,
        access_level="public",
        processing_status="ready",
        is_featured=False,
        featured_sort_order=None,
        metadata_={},
        created_at=now,
        updated_at=now,
        media_assets=[],
        location=public_location,
    )
    collection = SimpleNamespace(
        id=uuid4(),
        slug="dawn-archive",
        title="Dawn Archive",
        description="Dawn journeys",
        sort_order=0,
        metadata_={},
        created_at=now,
        updated_at=now,
        location_links=[],
        session_links=[
            SimpleNamespace(session=public_session),
            SimpleNamespace(session=SimpleNamespace(access_level="members_only")),
        ],
    )

    detail = collections_service.detail_from_collection(collection).model_dump(mode="json")

    assert detail["location_count"] == 0
    assert detail["session_count"] == 1
    assert len(detail["sessions"]) == 1


def test_sync_links_deduplicates_ids() -> None:
    from orna_atlas.app.modules.collections.repository import _dedupe_ids

    first = uuid4()
    second = uuid4()
    assert _dedupe_ids([first, second, first]) == [first, second]
