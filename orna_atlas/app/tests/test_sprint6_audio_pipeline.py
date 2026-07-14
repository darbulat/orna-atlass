from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import math
import struct
import wave
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from orna_atlas.app.main import app
from orna_atlas.app.modules.media.models import MediaAsset
from orna_atlas.app.modules.media.service import (
    extract_audio_metadata,
    generate_waveform,
    public_audio_metadata,
    should_enqueue_audio_pipeline,
    streaming_rendition_key,
)
from orna_atlas.app.workers.audio_pipeline import enqueue_audio_processing


def test_sprint6_routes_are_registered() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/api/v1/admin/sessions/{session_id}/assets" in schema["paths"]
    assert "/api/v1/admin/sessions/{session_id}/processing" in schema["paths"]
    assert "/api/v1/admin/media-assets/{asset_id}/process" in schema["paths"]


def test_wav_metadata_and_waveform_are_generated(tmp_path: Path) -> None:
    wav_path = tmp_path / "source.wav"
    _write_test_wav(wav_path)
    asset = MediaAsset(
        id=uuid4(),
        session_id=uuid4(),
        kind="source_audio",
        storage_key=str(wav_path),
        mime_type="audio/wav",
        duration_seconds=None,
        size_bytes=None,
        checksum=None,
        metadata_={},
    )

    metadata = extract_audio_metadata(asset)
    waveform = generate_waveform(asset, metadata=metadata)

    assert metadata["duration_seconds"] == 1
    assert metadata["channels"] == 1
    assert metadata["frame_rate_hz"] == 8000
    assert metadata["source"] == "wave"
    assert "storage_key" not in metadata
    assert waveform["status"] == "generated"
    assert len(waveform["peaks"]) == 64
    assert max(waveform["peaks"]) > 0


def test_public_audio_metadata_strips_private_storage_keys() -> None:
    metadata = public_audio_metadata(
        {
            "duration_seconds": 10,
            "storage_key": "private/source.wav",
            "source_storage_key": "private/source.wav",
        }
    )

    assert metadata == {"duration_seconds": 10}


def test_audio_pipeline_only_enqueues_source_assets() -> None:
    assert should_enqueue_audio_pipeline("source_audio")
    assert should_enqueue_audio_pipeline("master_audio")
    assert not should_enqueue_audio_pipeline("image")
    assert not should_enqueue_audio_pipeline("source_audio", enqueue_processing=False)


def test_audio_pipeline_uses_rq_safe_deterministic_job_id(monkeypatch) -> None:
    asset_id = uuid4()
    enqueue = MagicMock(return_value=SimpleNamespace(id="queued"))
    monkeypatch.setattr("rq.Queue.enqueue", enqueue)
    monkeypatch.setattr("redis.Redis.from_url", MagicMock())

    assert enqueue_audio_processing(asset_id, revision=3) == "queued"
    assert enqueue.call_args.kwargs["job_id"] == f"audio-{asset_id}-r3"


def test_streaming_rendition_key_is_deterministic() -> None:
    session_id = uuid4()
    asset = MediaAsset(
        id=uuid4(),
        session_id=session_id,
        kind="source_audio",
        storage_key="masters/test.wav",
        mime_type="audio/wav",
        duration_seconds=60,
        size_bytes=1024,
        checksum="abc",
        metadata_={},
    )

    assert streaming_rendition_key(asset) == (
        f"sessions/{session_id}/renditions/{asset.id}/{asset.id}.wav"
    )


def _write_test_wav(path: Path) -> None:
    sample_rate = 8000
    frames = []
    for index in range(sample_rate):
        amplitude = int(12000 * math.sin(2 * math.pi * 440 * index / sample_rate))
        frames.append(struct.pack("<h", amplitude))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"".join(frames))
