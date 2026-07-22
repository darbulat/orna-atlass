from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from orna_atlas.app.main import app
from orna_atlas.app.modules.sessions import service
from orna_atlas.app.modules.sessions.schemas import SessionDetailRead


def test_sprint3_public_audio_routes_are_registered() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/sessions/{locator}" in schema["paths"]
    assert "/api/v1/sessions/{session_id}/playback-grants" in schema["paths"]
    assert "/api/v1/sessions/{session_id}/waveform" in schema["paths"]
    assert "/api/v1/sessions/{session_id}/annotations" in schema["paths"]


def test_session_detail_schema_contains_location_integrity_and_safe_media() -> None:
    now = datetime.now(UTC)
    location = SimpleNamespace(
        id=uuid4(),
        slug="misty-wetland",
        name="Misty Wetland",
        description="A quiet marsh at dawn.",
        country_code="MN",
        region="Khentii",
        habitat="wetland",
        latitude=48.1,
        longitude=107.2,
        public_latitude=48.1,
        public_longitude=107.2,
        coordinate_visibility="approximate_public",
        sensitivity_level="medium",
        timezone="Asia/Ulaanbaatar",
        metadata_={},
        created_at=now,
        updated_at=now,
    )
    media = SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        kind="audio_stream",
        storage_key="private/sessions/master.wav",
        mime_type="audio/mpeg",
        duration_seconds=3600,
        size_bytes=120,
        checksum="abc",
        metadata_={},
        created_at=now,
    )
    recording = SimpleNamespace(
        id=media.session_id,
        location_id=location.id,
        slug="misty-dawn",
        title="Misty Dawn",
        description="Long-form dawn chorus.",
        recorded_at=now,
        duration_seconds=3600,
        recorder="ORNA field team",
        weather="Light rain",
        access_level="public",
        metadata_={
            "context": {
                "photo_url": "https://cdn.example.test/wetland.jpg",
                "altitude_meters": 42,
                "temperature_celsius": 12.5,
                "wind_speed_kph": 8.4,
                "humidity_percent": 78,
                "moon_phase": "Waxing crescent",
            },
            "recording_integrity": {
                "human_noise_level": "none_detected",
                "post_processing": "No loops, no studio layers",
                "microphone_setup": "ORTF pair",
                "recordist_notes": "Recorded before sunrise.",
            },
            "waveform": {"peaks": [0.1, 0.5], "duration_seconds": 3600},
            "annotations": [
                {"offset_seconds": 42, "duration_seconds": 5, "label": "First bird call"}
            ],
        },
        created_at=now,
        updated_at=now,
        media_assets=[media],
        location=location,
    )

    detail = SessionDetailRead.model_validate(recording).model_dump(mode="json")

    assert detail["location"]["slug"] == "misty-wetland"
    assert detail["photo_url"] == "https://cdn.example.test/wetland.jpg"
    assert detail["altitude_meters"] == 42
    assert detail["temperature_celsius"] == 12.5
    assert detail["wind_speed_kph"] == 8.4
    assert detail["humidity_percent"] == 78
    assert detail["moon_phase"] == "Waxing crescent"
    assert detail["recording_integrity"]["human_noise_level"] == "none_detected"
    assert detail["waveform"]["peaks"] == [0.1, 0.5]
    assert detail["annotations"][0]["label"] == "First bird call"
    assert "storage_key" not in detail["media_assets"][0]


def test_playback_grant_schema_documents_protected_lifecycle() -> None:
    schema = TestClient(app).get("/openapi.json").json()
    grant_schema = schema["components"]["schemas"]["PlaybackGrantRead"]["properties"]

    assert {"session_id", "status", "stream_url", "expires_at", "refresh_after_seconds"}.issubset(
        grant_schema
    )


def test_waveform_metadata_overrides_defaults_without_duplicate_kwargs() -> None:
    session_id = uuid4()
    recording = SimpleNamespace(
        id=session_id,
        duration_seconds=3600,
        metadata_={"waveform": {"duration_seconds": 120, "peaks": [0.2], "status": "ready"}},
    )

    waveform = service.waveform_for_session(recording)

    assert waveform.session_id == session_id
    assert waveform.duration_seconds == 120
    assert waveform.peaks == [0.2]
    assert waveform.status == "ready"


def test_session_detail_ignores_non_list_annotation_metadata() -> None:
    now = datetime.now(UTC)
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
        coordinate_visibility="approximate_public",
        sensitivity_level="medium",
        timezone="Asia/Ulaanbaatar",
        metadata_={},
        created_at=now,
        updated_at=now,
    )
    recording = SimpleNamespace(
        id=uuid4(),
        location_id=location.id,
        slug="misty-dawn",
        title="Misty Dawn",
        description=None,
        recorded_at=now,
        duration_seconds=3600,
        recorder=None,
        weather=None,
        access_level="public",
        metadata_={"annotations": None},
        created_at=now,
        updated_at=now,
        media_assets=[],
        location=location,
    )

    detail = SessionDetailRead.model_validate(recording)

    assert detail.annotations == []
