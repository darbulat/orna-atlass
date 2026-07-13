from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from orna_atlas.app.main import app as _app  # noqa: F401
from orna_atlas.app.core.domain_types import PublicationStatus, SessionAccess
from orna_atlas.app.integrations.sunrise import dawn_window, get_timezone
from orna_atlas.app.modules.media import service as media_service
from orna_atlas.app.modules.media.audio import streaming_rendition_key, upload_streaming_rendition
from orna_atlas.app.modules.media.models import MediaAsset, ProcessingJob
from orna_atlas.app.modules.sessions.models import RecordingSession
from orna_atlas.app.modules.sessions import repository as sessions_repository
from orna_atlas.app.modules.sessions.schemas import SessionCreate
from orna_atlas.app.modules.sessions.service import _ready_streaming_rendition


def test_publication_access_and_processing_are_independent() -> None:
    session = SessionCreate(
        location_id=uuid4(),
        slug="members-preview",
        title="Members preview",
        recorded_at=datetime.now(UTC),
        access_level=SessionAccess.MEMBERS_ONLY,
        publication_status=PublicationStatus.DRAFT,
        processing_status="ready",
    )

    assert session.access_level is SessionAccess.MEMBERS_ONLY
    assert session.publication_status is PublicationStatus.DRAFT
    assert session.processing_status == "ready"


def test_sprint3_partial_unique_indexes_are_in_model_metadata() -> None:
    index_names = {
        index.name
        for table in (MediaAsset.__table__, ProcessingJob.__table__)
        for index in table.indexes
    }

    assert {
        "uq_media_assets_active_source",
        "uq_media_assets_active_rendition",
        "uq_processing_jobs_active_asset_type",
    } <= index_names
    assert "publication_status" in RecordingSession.__table__.columns


@pytest.mark.asyncio
async def test_public_slug_lookup_requires_published_state() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result

    await sessions_repository.get_visible_session_by_slug(
        db,
        "draft-session",
        access_levels=("public",),
    )

    statement = db.execute.await_args.args[0]
    assert "recording_sessions.publication_status" in str(statement)


@pytest.mark.parametrize(
    "storage_key",
    [
        "/tmp/source.wav",
        "file:///tmp/source.wav",
        "s3://another-bucket/source.wav",
        "sessions/../secret.wav",
        "uploads/source.wav",
    ],
)
def test_admin_media_rejects_unmanaged_paths_and_buckets(storage_key: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        media_service.validate_managed_storage_key(storage_key)

    assert exc_info.value.status_code == 422


def test_rendition_keys_are_versioned_per_attempt() -> None:
    source = SimpleNamespace(id=uuid4(), session_id=uuid4(), kind="source_audio")

    first = streaming_rendition_key(source, uuid4())
    second = streaming_rendition_key(source, uuid4())

    assert first != second
    assert first.startswith(f"sessions/{source.session_id}/renditions/{source.id}/")


def test_unconfigured_storage_cannot_report_successful_upload(monkeypatch) -> None:
    source = SimpleNamespace(storage_key="sessions/source.wav")
    rendition = SimpleNamespace(storage_key="sessions/rendition.wav", mime_type="audio/wav")
    client = SimpleNamespace(is_configured=lambda: False)
    monkeypatch.setattr("orna_atlas.app.modules.media.audio.get_object_storage_client", lambda: client)

    with pytest.raises(RuntimeError, match="not configured"):
        upload_streaming_rendition(source, rendition)


def test_playback_uses_only_active_unarchived_rendition() -> None:
    archived = SimpleNamespace(
        kind="streaming_rendition",
        processing_status="ready",
        is_active=False,
        archived_at=datetime.now(UTC),
    )
    active = SimpleNamespace(
        kind="streaming_rendition",
        processing_status="ready",
        is_active=True,
        archived_at=None,
    )

    assert _ready_streaming_rendition(SimpleNamespace(media_assets=[archived, active])) is active


@pytest.mark.asyncio
async def test_retry_returns_existing_active_processing_job(monkeypatch) -> None:
    asset = SimpleNamespace(
        id=uuid4(),
        session_id=uuid4(),
        kind="source_audio",
        is_active=True,
        archived_at=None,
    )
    active_job = SimpleNamespace(status="running")
    status_payload = SimpleNamespace(session_id=asset.session_id)
    db = AsyncMock()
    create_job = AsyncMock()
    monkeypatch.setattr(media_service, "require_asset", AsyncMock(return_value=asset))
    monkeypatch.setattr(
        media_service.repository,
        "active_processing_job",
        AsyncMock(return_value=active_job),
    )
    monkeypatch.setattr(media_service.repository, "create_processing_job", create_job)
    monkeypatch.setattr(
        media_service,
        "processing_status_for_session",
        AsyncMock(return_value=status_payload),
    )

    result = await media_service.retry_asset_processing(db, asset.id)

    assert result is status_payload
    create_job.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_solar_phase_distinguishes_polar_day_and_night() -> None:
    summer = dawn_window(
        latitude=78.2232,
        longitude=15.6469,
        timezone="Arctic/Longyearbyen",
        now=datetime(2026, 6, 21, 12, tzinfo=UTC),
    )
    winter = dawn_window(
        latitude=78.2232,
        longitude=15.6469,
        timezone="Arctic/Longyearbyen",
        now=datetime(2026, 12, 21, 12, tzinfo=UTC),
    )

    assert summer.solar_phase == "polar_day"
    assert winter.solar_phase == "polar_night"


def test_invalid_timezone_does_not_fall_back_to_utc() -> None:
    with pytest.raises(ValueError, match="Unknown IANA timezone"):
        get_timezone("Mars/Olympus")
