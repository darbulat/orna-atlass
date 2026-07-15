from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from orna_atlas.app.integrations.bird_analysis import BirdDetection
from orna_atlas.app.modules.media import service


@pytest.mark.asyncio
async def test_segment_bird_analysis_isolates_failure_and_keeps_sibling_results(monkeypatch):
    segments = [
        SimpleNamespace(
            id=uuid4(),
            sequence_number=index,
            processing_status="pending",
            processing_attempt_count=0,
            processing_error_code=None,
            processing_error_message=None,
            start_offset_ms=(index - 1) * 1000,
            source_asset=SimpleNamespace(storage_key=f"sessions/s/source-{index}.wav"),
        )
        for index in (1, 2, 3)
    ]
    recording = SimpleNamespace(
        id=uuid4(),
        location=SimpleNamespace(exact_latitude=1.0, exact_longitude=2.0),
        recorded_at=service.datetime(2026, 7, 15, tzinfo=service.UTC),
    )
    detection = BirdDetection(
        species_code="bird",
        species_common_name="Bird",
        species_scientific_name=None,
        starts_at_seconds=0.25,
        ends_at_seconds=0.75,
        confidence=0.9,
    )

    def detect(asset, **_kwargs):
        if asset.storage_key.endswith("source-2.wav"):
            raise RuntimeError("segment failed")
        return [detection]

    savepoint = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    session = SimpleNamespace(
        begin_nested=AsyncMock(return_value=savepoint),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    store = AsyncMock()
    monkeypatch.setattr(service, "_detect_bird_parts", detect)
    monkeypatch.setattr(service.sessions_repository, "replace_segment_bird_vocal_parts", store)

    succeeded, failed = await service._analyze_hls_segments(session, recording, segments)

    assert (succeeded, failed) == (2, 1)
    assert store.await_count == 2
    first_detections = store.await_args_list[0].args[3]
    third_detections = store.await_args_list[1].args[3]
    assert first_detections[0].starts_at_seconds == 0.25
    assert third_detections[0].starts_at_seconds == 2.25
    assert session.rollback.await_count == 1
    assert [segment.processing_status for segment in segments] == ["ready", "failed", "ready"]
    assert [segment.processing_attempt_count for segment in segments] == [1, 1, 1]
    assert segments[1].processing_error_code == "RuntimeError"
    assert segments[1].processing_error_message == "segment failed"
