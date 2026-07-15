from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from orna_atlas.app.modules.atlas import repository as atlas_repository
from orna_atlas.app.modules.atlas import router as atlas_router
from orna_atlas.app.modules.media import service as media_service
from orna_atlas.app.modules.media.models import ProcessingJob


@pytest.mark.asyncio
async def test_search_applies_one_global_page_to_union() -> None:
    location = SimpleNamespace(id=uuid4())
    recording = SimpleNamespace(id=uuid4())
    result = MagicMock()
    result.unique.return_value.all.return_value = [
        ("location", location, None),
        ("session", None, recording),
    ]
    db = AsyncMock()
    db.execute.return_value = result

    rows = await atlas_repository.search_locations_and_sessions(
        db,
        query="marsh",
        limit=8,
        offset=3,
    )

    assert rows == [location, recording]
    db.execute.assert_awaited_once()
    sql = str(db.execute.await_args.args[0]).upper()
    assert "UNION ALL" in sql
    assert sql.count(" OFFSET ") == 1
    assert sql.count(" LIMIT ") == 1


class _CachePayload(BaseModel):
    value: str


class _CorruptCache:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.stored: list[tuple[str, str, int]] = []
        self.closed = False

    async def get(self, _key: str) -> str:
        return '{"value":'

    async def delete(self, key: str) -> None:
        self.deleted.append(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        self.stored.append((key, value, ex))

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_corrupt_cache_entry_is_deleted_and_regenerated(monkeypatch) -> None:
    cache = _CorruptCache()
    producer = AsyncMock(return_value=_CachePayload(value="fresh"))
    monkeypatch.setattr(atlas_router, "get_redis_client", lambda: cache)

    response = await atlas_router._cached_response(
        "atlas:points:broken",
        _CachePayload,
        producer,
        ttl=60,
    )

    assert response == _CachePayload(value="fresh")
    assert cache.deleted == ["atlas:points:broken"]
    assert cache.stored == [("atlas:points:broken", '{"value":"fresh"}', 60)]
    assert cache.closed


def test_processing_job_persists_individual_stage_states() -> None:
    assert "stage_states" in ProcessingJob.__table__.columns
    assert "request_id" in ProcessingJob.__table__.columns
    assert "queue_job_id" in ProcessingJob.__table__.columns
    assert "heartbeat_at" in ProcessingJob.__table__.columns


def test_pipeline_running_lease_distinguishes_live_and_stale_jobs() -> None:
    now = datetime.now(UTC)

    assert not media_service._job_is_stale(
        SimpleNamespace(heartbeat_at=now - timedelta(minutes=5)),
        now=now,
    )
    assert media_service._job_is_stale(
        SimpleNamespace(heartbeat_at=now - timedelta(hours=8)),
        now=now,
    )
    assert media_service._job_is_stale(
        SimpleNamespace(
            status="queued",
            heartbeat_at=None,
            updated_at=now - timedelta(hours=8),
            created_at=now - timedelta(hours=8),
        ),
        now=now,
    )


@pytest.mark.asyncio
async def test_failed_pipeline_stage_can_be_retried_with_new_attempt(monkeypatch) -> None:
    job = SimpleNamespace(stage_states={})
    db = AsyncMock()
    stage_metric = MagicMock()
    monkeypatch.setattr(media_service, "PIPELINE_STAGE_DURATION", stage_metric)

    async def fail() -> None:
        raise TimeoutError("storage unavailable")

    result = await media_service._run_pipeline_stage(
        db,
        job,
        "rendition_verify",
        fail,
        optional=True,
    )

    assert result is None
    assert job.stage_states["rendition_verify"] == {
        "status": "failed",
        "attempt_count": 1,
        "error_code": "TimeoutError",
        "error_message": "storage unavailable",
        "started_at": job.stage_states["rendition_verify"]["started_at"],
        "finished_at": job.stage_states["rendition_verify"]["finished_at"],
    }

    async def succeed() -> str:
        return "verified"

    assert await media_service._run_pipeline_stage(
        db,
        job,
        "rendition_verify",
        succeed,
    ) == "verified"
    assert job.stage_states["rendition_verify"]["status"] == "succeeded"
    assert job.stage_states["rendition_verify"]["attempt_count"] == 2
    assert job.stage_states["rendition_verify"]["error_code"] is None
    assert [item.args for item in stage_metric.labels.call_args_list] == [
        ("rendition_verify", "failed"),
        ("rendition_verify", "succeeded"),
    ]
    assert stage_metric.labels.return_value.observe.call_count == 2


@pytest.mark.asyncio
async def test_rq_enqueue_is_offloaded_from_async_service(monkeypatch) -> None:
    asset_id = uuid4()
    offload = AsyncMock(return_value="job-id")
    monkeypatch.setattr(media_service.asyncio, "to_thread", offload)

    assert await media_service.enqueue_asset_processing(asset_id, 4) == "job-id"

    function, queued_asset_id, revision = offload.await_args.args
    assert function.__name__ == "enqueue_audio_processing"
    assert queued_asset_id == asset_id
    assert revision == 4
    assert offload.await_args.kwargs == {
        "request_id": None,
        "processing_job_id": None,
        "duration_seconds": None,
    }


@pytest.mark.asyncio
async def test_enqueue_persists_request_to_queue_job_correlation(monkeypatch) -> None:
    asset = SimpleNamespace(id=uuid4(), revision=7)
    job = SimpleNamespace(id=uuid4(), request_id="request-42", queue_job_id=None)
    db = AsyncMock()
    enqueue = AsyncMock(return_value="audio-rq-job")
    monkeypatch.setattr(media_service, "enqueue_asset_processing", enqueue)

    await media_service._enqueue_or_mark_failed(db, asset, job)

    enqueue.assert_awaited_once_with(
        asset.id,
        7,
        request_id="request-42",
        processing_job_id=job.id,
        duration_seconds=None,
    )
    assert job.queue_job_id == "audio-rq-job"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_media_cache_invalidation_uses_shared_after_commit_boundary(monkeypatch) -> None:
    invalidate = AsyncMock()
    recording = SimpleNamespace(id=uuid4(), slug="marsh-dawn")
    monkeypatch.setattr(media_service, "invalidate_atlas_cache", invalidate)

    await media_service._clear_processing_caches(recording)

    invalidate.assert_awaited_once_with(
        session_keys=(
            f"session:{recording.id}",
            "session:marsh-dawn",
        )
    )
