from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from orna_atlas.app.modules.media.service import _analyze_and_store_bird_parts


@pytest.mark.asyncio
async def test_analyze_failure_preserves_last_successful_bird_parts() -> None:
    session_id = uuid4()
    recording = SimpleNamespace(
        id=session_id,
        metadata_={"bird_analysis": {"last_successful": {"status": "succeeded", "parts_count": 3}}},
        location=SimpleNamespace(exact_latitude=54.6, exact_longitude=28.3),
        recorded_at=None,
    )
    asset = SimpleNamespace(
        session_id=session_id,
        storage_key="sessions/test/source.wav",
        session=recording,
    )
    db_session = AsyncMock()

    with (
        patch(
            "orna_atlas.app.modules.media.service.materialize_storage",
            side_effect=RuntimeError("decoder unavailable"),
        ),
        patch(
            "orna_atlas.app.modules.media.service.sessions_repository.replace_bird_vocal_parts",
            new_callable=AsyncMock,
        ) as replace_parts,
    ):
        await _analyze_and_store_bird_parts(db_session, asset)

    replace_parts.assert_not_awaited()
    analysis = recording.metadata_["bird_analysis"]
    assert analysis["last_successful"]["parts_count"] == 3
    assert analysis["latest_attempt"]["status"] == "failed"
    assert analysis["latest_attempt"]["error_code"] == "RuntimeError"
