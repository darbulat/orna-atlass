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
    get_asset = AsyncMock(return_value=asset)
    monkeypatch.setattr(media_service.repository, "get_asset_for_processing", get_asset)
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
    get_asset.assert_awaited_once_with(db, asset.id)
    create_job.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_purge_fails_closed_when_object_storage_is_unconfigured(monkeypatch) -> None:
    asset = SimpleNamespace(
        id=uuid4(),
        storage_key="sessions/archive/source.wav",
        archived_at=datetime.now(UTC),
        is_active=False,
        session=SimpleNamespace(),
    )
    db = AsyncMock()
    delete_asset = AsyncMock()
    monkeypatch.setattr(media_service, "require_asset", AsyncMock(return_value=asset))
    monkeypatch.setattr(
        media_service,
        "get_object_storage_client",
        lambda: SimpleNamespace(is_configured=lambda: False),
    )
    monkeypatch.setattr(media_service.repository, "delete_asset", delete_asset)

    with pytest.raises(HTTPException) as exc_info:
        await media_service.purge_archived_asset(db, asset.id)

    assert exc_info.value.status_code == 503
    delete_asset.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_recording_status_uses_new_uploaded_source_not_old_rendition() -> None:
    old_source_id = uuid4()
    new_source_id = uuid4()
    recording = SimpleNamespace(
        media_assets=[
            SimpleNamespace(
                id=old_source_id,
                kind="source_audio",
                processing_status="ready",
                is_active=False,
                archived_at=datetime.now(UTC),
                source_asset_id=None,
            ),
            SimpleNamespace(
                id=new_source_id,
                kind="source_audio",
                processing_status="uploaded",
                is_active=True,
                archived_at=None,
                source_asset_id=None,
            ),
            SimpleNamespace(
                id=uuid4(),
                kind="streaming_rendition",
                processing_status="ready",
                is_active=True,
                archived_at=None,
                source_asset_id=old_source_id,
            ),
        ]
    )

    assert media_service._recording_processing_status(recording) == "uploaded"


@pytest.mark.asyncio
async def test_obsolete_queued_job_is_marked_superseded(monkeypatch) -> None:
    job = SimpleNamespace(
        status="queued",
        error_code=None,
        error_message=None,
        finished_at=None,
    )
    asset = SimpleNamespace(
        id=uuid4(),
        is_active=False,
        archived_at=datetime.now(UTC),
    )
    db = AsyncMock()
    monkeypatch.setattr(
        media_service.repository,
        "get_asset_for_processing",
        AsyncMock(return_value=asset),
    )
    monkeypatch.setattr(
        media_service.repository,
        "latest_processing_job",
        AsyncMock(return_value=job),
    )

    with pytest.raises(media_service.ObsoleteAssetRevisionError):
        await media_service.process_media_asset(db, asset.id)

    assert job.status == "failed"
    assert job.error_code == "superseded"
    assert job.finished_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_superseded_worker_does_not_fail_active_session(monkeypatch) -> None:
    session_id = uuid4()
    old_source = SimpleNamespace(
        id=uuid4(),
        session_id=session_id,
        kind="source_audio",
        storage_key="sessions/old.wav",
        processing_status="queued",
        is_active=True,
        archived_at=None,
        duration_seconds=None,
        size_bytes=None,
        checksum=None,
        metadata_={},
    )
    new_source = SimpleNamespace(
        id=uuid4(),
        session_id=session_id,
        kind="source_audio",
        processing_status="queued",
        is_active=True,
        archived_at=None,
        source_asset_id=None,
    )
    recording = SimpleNamespace(
        id=session_id,
        duration_seconds=None,
        processing_status="queued",
        metadata_={},
        media_assets=[old_source, new_source],
    )
    old_source.session = recording
    job = SimpleNamespace(
        status="queued",
        attempt_count=0,
        error_code=None,
        error_message=None,
        started_at=None,
        finished_at=None,
    )
    rendition = SimpleNamespace(
        id=uuid4(),
        kind="streaming_rendition",
        storage_key="sessions/rendition.wav",
        processing_status="processing",
        is_active=False,
        archived_at=None,
        source_asset_id=old_source.id,
    )
    recording.media_assets.append(rendition)
    db = AsyncMock()
    monkeypatch.setattr(
        media_service.repository,
        "get_asset_for_processing",
        AsyncMock(return_value=old_source),
    )
    monkeypatch.setattr(
        media_service.repository,
        "latest_processing_job",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(
        media_service,
        "extract_audio_metadata",
        lambda _asset: {"duration_seconds": 1, "size_bytes": 1},
    )
    monkeypatch.setattr(media_service, "generate_waveform", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        media_service,
        "_ensure_streaming_rendition",
        AsyncMock(return_value=rendition),
    )
    monkeypatch.setattr(media_service, "_upload_streaming_rendition", lambda *_args: None)
    monkeypatch.setattr(
        media_service,
        "get_object_storage_client",
        lambda: SimpleNamespace(object_exists=lambda _key: True),
    )
    monkeypatch.setattr(
        media_service.repository,
        "active_source_assets_for_update",
        AsyncMock(return_value=[new_source]),
    )

    with pytest.raises(media_service.ObsoleteAssetRevisionError):
        await media_service.process_media_asset(db, old_source.id)

    assert job.status == "failed"
    assert job.error_code == "superseded"
    assert recording.processing_status == "queued"
    assert rendition.processing_status == "failed"
    db.commit.assert_awaited()


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
