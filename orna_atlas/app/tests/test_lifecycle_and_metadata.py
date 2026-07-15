import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from orna_atlas.app.main import app as _app  # noqa: F401
from orna_atlas.app.modules.locations import repository as locations_repository
from orna_atlas.app.modules.media import repository as media_repository
from orna_atlas.app.modules.media import service as media_service
from orna_atlas.app.modules.media.models import StorageCleanupJob
from orna_atlas.app.modules.sessions import repository as sessions_repository
from orna_atlas.app.modules.sessions.schemas import SessionCreate, SessionUpdate
from orna_atlas.app.modules.sessions.service import (
    annotations_for_session,
    waveform_for_session,
)
from orna_atlas.app.seed_atlas import (
    SEED_OWNER,
    _assert_seed_allowed,
    _is_seed_owned,
)
from orna_atlas.app.workers import pipeline_recovery, storage_cleanup


@pytest.mark.asyncio
async def test_session_archive_is_a_tombstone() -> None:
    recording = SimpleNamespace(
        archived_at=None,
        publication_status="published",
        is_featured=True,
        featured_sort_order=2,
    )
    db = AsyncMock()

    await sessions_repository.archive_session(db, recording)

    assert recording.archived_at is not None
    assert recording.publication_status == "archived"
    assert recording.is_featured is False
    assert recording.featured_sort_order is None
    db.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_location_archive_is_a_tombstone() -> None:
    location = SimpleNamespace(archived_at=None)
    db = AsyncMock()

    await locations_repository.archive_location(db, location)

    assert location.archived_at is not None
    db.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_cleanup_job_is_scheduled_once_per_asset() -> None:
    now = datetime.now(UTC)
    asset = SimpleNamespace(
        id=uuid4(),
        storage_key=f"sessions/{uuid4()}/source.wav",
        storage_deleted_at=None,
    )
    result = MagicMock()
    result.scalars.return_value = []
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.return_value = result

    jobs = await media_repository.schedule_storage_cleanup(
        db,
        [asset],
        retain_until=now,
    )

    assert len(jobs) == 1
    assert isinstance(jobs[0], StorageCleanupJob)
    assert jobs[0].storage_key == asset.storage_key
    assert jobs[0].next_attempt_at == now
    db.add.assert_called_once_with(jobs[0])


@pytest.mark.asyncio
async def test_storage_cleanup_is_idempotent_and_marks_tombstone(monkeypatch) -> None:
    now = datetime.now(UTC)
    asset = SimpleNamespace(storage_deleted_at=None)
    job = SimpleNamespace(
        id=uuid4(),
        status="pending",
        retain_until=now - timedelta(minutes=1),
        next_attempt_at=now - timedelta(minutes=1),
        locked_at=None,
        attempt_count=0,
        error_code=None,
        error_message=None,
        storage_key=f"sessions/{uuid4()}/source.wav",
        completed_at=None,
        asset=asset,
    )
    storage = SimpleNamespace(
        is_configured=lambda: True,
        object_exists=MagicMock(return_value=True),
        delete_object=MagicMock(),
    )
    db = AsyncMock()
    monkeypatch.setattr(
        media_service.repository,
        "get_storage_cleanup_job_for_update",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(media_service, "get_object_storage_client", lambda: storage)

    assert await media_service.process_storage_cleanup_job(db, job.id, now=now) is True

    assert job.status == "succeeded"
    assert job.attempt_count == 1
    assert job.completed_at is not None
    assert asset.storage_deleted_at == job.completed_at
    storage.delete_object.assert_called_once_with(job.storage_key)
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_hls_cleanup_deletes_only_persisted_inventory(monkeypatch) -> None:
    now = datetime.now(UTC)
    prefix = f"sessions/{uuid4()}/hls/generation"
    inventory = [
        f"{prefix}/init_0001.mp4",
        f"{prefix}/segment_000000.m4s",
        f"{prefix}/index.m3u8",
    ]
    asset = SimpleNamespace(storage_deleted_at=None)
    job = SimpleNamespace(
        id=uuid4(),
        status="pending",
        retain_until=now,
        next_attempt_at=now,
        locked_at=None,
        attempt_count=0,
        error_code=None,
        error_message=None,
        storage_key=inventory[-1],
        object_keys=inventory,
        completed_at=None,
        asset=asset,
    )
    storage = SimpleNamespace(
        is_configured=lambda: True,
        object_exists=MagicMock(return_value=True),
        delete_object=MagicMock(),
    )
    db = AsyncMock()
    monkeypatch.setattr(
        media_service.repository,
        "get_storage_cleanup_job_for_update",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(media_service, "get_object_storage_client", lambda: storage)

    assert await media_service.process_storage_cleanup_job(db, job.id, now=now) is True

    assert [call.args[0] for call in storage.delete_object.call_args_list] == inventory
    assert not hasattr(storage, "delete_prefix")
    assert asset.storage_deleted_at == job.completed_at


@pytest.mark.asyncio
async def test_storage_cleanup_failure_is_persisted_for_retry(monkeypatch) -> None:
    now = datetime.now(UTC)
    job = SimpleNamespace(
        id=uuid4(),
        status="pending",
        retain_until=now,
        next_attempt_at=now,
        locked_at=None,
        attempt_count=0,
        error_code=None,
        error_message=None,
        storage_key=f"sessions/{uuid4()}/source.wav",
        completed_at=None,
        asset=None,
    )
    db = AsyncMock()
    monkeypatch.setattr(
        media_service.repository,
        "get_storage_cleanup_job_for_update",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(
        media_service,
        "get_object_storage_client",
        lambda: SimpleNamespace(is_configured=lambda: False),
    )

    with pytest.raises(RuntimeError, match="not configured"):
        await media_service.process_storage_cleanup_job(db, job.id, now=now)

    assert job.status == "failed"
    assert job.attempt_count == 1
    assert job.error_code == "RuntimeError"
    assert job.next_attempt_at > now
    assert db.commit.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_module", [storage_cleanup, pipeline_recovery])
async def test_maintenance_worker_survives_iteration_failure(
    monkeypatch,
    worker_module,
) -> None:
    run_once = AsyncMock(
        side_effect=[RuntimeError("temporary database outage"), asyncio.CancelledError()]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(worker_module, "run_once", run_once)
    monkeypatch.setattr(worker_module.asyncio, "sleep", sleep)

    with pytest.raises(asyncio.CancelledError):
        await worker_module.run_worker(limit=1, interval_seconds=1)

    assert run_once.await_count == 2
    sleep.assert_awaited_once_with(1)


def test_new_session_metadata_rejects_malformed_structures() -> None:
    base = {
        "location_id": uuid4(),
        "slug": "invalid-metadata",
        "title": "Invalid metadata",
        "recorded_at": datetime.now(UTC),
    }
    with pytest.raises(ValidationError):
        SessionCreate(**base, metadata={"waveform": {"peaks": [float("nan")]}})
    with pytest.raises(ValidationError):
        SessionUpdate(metadata={"annotations": [{"offset_seconds": -1, "label": "bad"}]})


def test_legacy_metadata_is_projected_without_failing_public_read() -> None:
    recording = SimpleNamespace(
        id=uuid4(),
        duration_seconds=60,
        metadata_={
            "waveform": {"peaks": [float("inf")], "sample_rate": 0},
            "annotations": [
                {"offset_seconds": -1, "label": "invalid"},
                {"offset_seconds": 4, "duration_seconds": 2, "label": "valid"},
                "corrupt",
            ],
        },
    )

    waveform = waveform_for_session(recording)
    annotations = annotations_for_session(recording)

    assert waveform.status == "placeholder"
    assert waveform.peaks == []
    assert [annotation.label for annotation in annotations] == ["valid"]


def test_seed_requires_local_or_test_and_explicit_force() -> None:
    with pytest.raises(RuntimeError, match="local or test"):
        _assert_seed_allowed(force=True, environment="production")
    with pytest.raises(RuntimeError, match="--force"):
        _assert_seed_allowed(force=False, environment="local")
    _assert_seed_allowed(force=True, environment="test")


def test_seed_ownership_marker_does_not_claim_user_content() -> None:
    assert _is_seed_owned(SimpleNamespace(metadata_={"seed": True})) is False
    assert _is_seed_owned(
        SimpleNamespace(metadata_={"seed": True, "seed_owner": SEED_OWNER})
    ) is True
    assert _is_seed_owned(SimpleNamespace(metadata_={"seed": False})) is False
    assert _is_seed_owned(SimpleNamespace(metadata_={})) is False
