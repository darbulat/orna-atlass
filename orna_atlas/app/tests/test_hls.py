from pathlib import Path

import pytest

from orna_atlas.app.modules.media.hls import (
    HlsError,
    assemble_vod_playlist,
    validate_hls_object_name,
)
from orna_atlas.app.modules.media.models import HlsProcessingJob, RecordingSegment
from orna_atlas.app.modules.media.schemas import RecordingSegmentBatchCreate


def test_assemble_vod_playlist_uses_discontinuity_and_per_source_init(tmp_path: Path):
    first = tmp_path / "first.m3u8"
    first.write_text(
        "#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXT-X-MAP:URI=\"init.mp4\"\n"
        "#EXTINF:10.0,\nsegment_000.m4s\n#EXT-X-ENDLIST\n"
    )
    second = tmp_path / "second.m3u8"
    second.write_text(
        "#EXTM3U\n#EXT-X-TARGETDURATION:8\n#EXT-X-MAP:URI=\"init.mp4\"\n"
        "#EXTINF:8.0,\nsegment_000.m4s\n#EXT-X-ENDLIST\n"
    )

    playlist, objects = assemble_vod_playlist([first, second])

    assert playlist.count("#EXT-X-DISCONTINUITY") == 1
    assert playlist.count("#EXT-X-MEDIA-SEQUENCE:") == 1
    assert playlist.count("#EXT-X-MAP") == 2
    assert '#EXT-X-MAP:URI="init_0002.mp4"' in playlist
    assert "segment_000000.m4s" in playlist
    assert "segment_000001.m4s" in playlist
    assert playlist.endswith("#EXT-X-ENDLIST\n")
    assert objects == [
        (first.parent / "init.mp4", "init_0001.mp4"),
        (first.parent / "segment_000.m4s", "segment_000000.m4s"),
        (second.parent / "init.mp4", "init_0002.mp4"),
        (second.parent / "segment_000.m4s", "segment_000001.m4s"),
    ]


@pytest.mark.parametrize("name", ["../secret", "/absolute", "https://evil/x", "a/b.m4s"])
def test_validate_hls_object_name_rejects_unsafe_uri(name: str):
    with pytest.raises(HlsError):
        validate_hls_object_name(name)


def test_segment_batch_requires_contiguous_sequence():
    batch = RecordingSegmentBatchCreate.model_validate(
        {
            "segments": [
                {"sequence_number": 1, "storage_key": "sessions/x/part1.wav"},
                {"sequence_number": 2, "storage_key": "sessions/x/part2.wav"},
            ]
        }
    )
    assert [item.sequence_number for item in batch.segments] == [1, 2]

    with pytest.raises(ValueError, match="contiguous"):
        RecordingSegmentBatchCreate.model_validate(
            {
                "segments": [
                    {"sequence_number": 1, "storage_key": "sessions/x/part1.wav"},
                    {"sequence_number": 3, "storage_key": "sessions/x/part3.wav"},
                ]
            }
        )


def test_hls_models_are_session_scoped():
    assert RecordingSegment.__tablename__ == "recording_segments"
    assert RecordingSegment.__table__.c.processing_status.default.arg == "pending"
    assert HlsProcessingJob.__tablename__ == "hls_processing_jobs"
