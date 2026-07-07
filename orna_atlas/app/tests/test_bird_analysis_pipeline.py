from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from orna_atlas.app.modules.media.service import _analyze_and_store_bird_parts


@pytest.mark.asyncio
async def test_analyze_and_store_bird_parts_clears_stale_rows_on_failure() -> None:
    session_id = uuid4()
    recording = SimpleNamespace(
        id=session_id,
        metadata_={},
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

    replace_parts.assert_awaited_once()
    assert replace_parts.await_args.args[2] == []
    assert recording.metadata_["bird_analysis"]["status"] == "failed"
    assert recording.metadata_["bird_analysis"]["error_code"] == "RuntimeError"
