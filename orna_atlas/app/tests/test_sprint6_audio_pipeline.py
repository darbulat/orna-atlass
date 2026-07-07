from pathlib import Path
from uuid import uuid4
import math
import struct
import wave

from fastapi.testclient import TestClient

from orna_atlas.app.main import app
from orna_atlas.app.modules.media.models import MediaAsset
from orna_atlas.app.modules.media.service import (
    extract_audio_metadata,
    generate_waveform,
    streaming_rendition_key,
)


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
    assert waveform["status"] == "generated"
    assert len(waveform["peaks"]) > 8
    assert max(waveform["peaks"]) > 0


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

    assert streaming_rendition_key(asset) == f"sessions/{session_id}/renditions/stream_320.mp3"


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
