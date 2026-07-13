from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from orna_atlas.app.integrations.s3 import ObjectStorageClient, ObjectStorageConfig, parse_storage_reference
from orna_atlas.app.modules.media.models import MediaAsset
from orna_atlas.app.modules.media.service import (
    _upload_streaming_rendition,
    extract_audio_metadata,
    streaming_rendition_key,
)
from orna_atlas.app.modules.media.storage import materialize_storage, storage_key_path
from orna_atlas.app.modules.sessions.service import create_playback_grant


def test_parse_storage_reference_supports_s3_uri_and_relative_keys() -> None:
    s3_ref = parse_storage_reference("s3://custom-bucket/path/to/file.wav", default_bucket="default")
    relative_ref = parse_storage_reference("sessions/abc/master.wav", default_bucket="orna-audio-private")

    assert s3_ref.kind == "s3"
    assert s3_ref.bucket == "custom-bucket"
    assert s3_ref.key == "path/to/file.wav"
    assert relative_ref.kind == "s3"
    assert relative_ref.bucket == "orna-audio-private"
    assert relative_ref.key == "sessions/abc/master.wav"


def test_materialize_storage_reads_local_file(tmp_path: Path) -> None:
    wav_path = tmp_path / "source.wav"
    wav_path.write_bytes(b"RIFF")

    with materialize_storage(str(wav_path)) as path:
        assert path == wav_path
        assert path.read_bytes() == b"RIFF"


def test_materialize_storage_downloads_s3_object_to_temp_file(tmp_path: Path) -> None:
    client = ObjectStorageClient(
        ObjectStorageConfig(
            endpoint_url="http://localhost:9000",
            access_key_id="test",
            secret_access_key="test",
        )
    )
    client._client = MagicMock()
    client._client.download_file.side_effect = lambda bucket, key, destination: Path(destination).write_bytes(
        b"downloaded-audio"
    )

    with materialize_storage("sessions/demo/source.wav", client=client) as path:
        assert path is not None
        assert path.read_bytes() == b"downloaded-audio"

    client._client.download_file.assert_called_once()
    bucket, key, destination = client._client.download_file.call_args.args
    assert bucket == "orna-audio-private"
    assert key == "sessions/demo/source.wav"
    assert Path(destination).exists() is False


def test_extract_audio_metadata_reads_from_s3_materialized_file(tmp_path: Path, monkeypatch) -> None:
    wav_path = tmp_path / "source.wav"
    _write_test_wav(wav_path)
    client = ObjectStorageClient(
        ObjectStorageConfig(
            endpoint_url="http://localhost:9000",
            access_key_id="test",
            secret_access_key="test",
        )
    )
    client._client = MagicMock()
    client._client.download_file.side_effect = lambda bucket, key, destination: Path(destination).write_bytes(
        wav_path.read_bytes()
    )
    import orna_atlas.app.modules.media.storage as media_storage

    monkeypatch.setattr(media_storage, "get_object_storage_client", lambda: client)

    asset = MediaAsset(
        id=uuid4(),
        session_id=uuid4(),
        kind="source_audio",
        storage_key="sessions/demo/source.wav",
        mime_type="audio/wav",
        duration_seconds=None,
        size_bytes=None,
        checksum=None,
        metadata_={},
    )

    metadata = extract_audio_metadata(asset)

    assert metadata["source"] == "wave"
    assert metadata["duration_seconds"] == 1
    assert metadata["channels"] == 1


def test_upload_streaming_rendition_copies_s3_source(monkeypatch) -> None:
    client = ObjectStorageClient(
        ObjectStorageConfig(
            endpoint_url="http://localhost:9000",
            access_key_id="test",
            secret_access_key="test",
        )
    )
    client._client = MagicMock()
    import orna_atlas.app.modules.media.audio as media_audio

    monkeypatch.setattr(media_audio, "get_object_storage_client", lambda: client)
    session_id = uuid4()
    source = MediaAsset(
        id=uuid4(),
        session_id=session_id,
        kind="source_audio",
        storage_key="s3://orna-audio-private/sessions/demo/source.wav",
        mime_type="audio/wav",
        duration_seconds=60,
        size_bytes=1024,
        checksum="abc",
        metadata_={},
    )
    rendition = MediaAsset(
        id=uuid4(),
        session_id=session_id,
        kind="streaming_rendition",
        storage_key=streaming_rendition_key(source),
        mime_type="audio/wav",
        duration_seconds=60,
        size_bytes=None,
        checksum="abc",
        metadata_={},
    )

    _upload_streaming_rendition(source, rendition)

    client._client.copy_object.assert_called_once()
    kwargs = client._client.copy_object.call_args.kwargs
    assert kwargs["Bucket"] == "orna-audio-private"
    assert kwargs["Key"] == streaming_rendition_key(source)
    assert kwargs["CopySource"] == {"Bucket": "orna-audio-private", "Key": "sessions/demo/source.wav"}


def test_create_playback_grant_uses_presigned_url_when_rendition_ready(monkeypatch) -> None:
    session_id = uuid4()
    rendition = SimpleNamespace(
        kind="streaming_rendition",
        processing_status="ready",
        storage_key=f"sessions/{session_id}/renditions/stream_rendition.wav",
    )
    recording = SimpleNamespace(id=session_id, media_assets=[rendition])
    client = ObjectStorageClient(
        ObjectStorageConfig(
            endpoint_url="http://minio:9000",
            public_endpoint_url="http://localhost:9000",
            access_key_id="test",
            secret_access_key="test",
            presign_expires_seconds=900,
        )
    )
    client._client = MagicMock()
    client._presign_client = MagicMock()
    client._presign_client.generate_presigned_url.return_value = "http://localhost:9000/presigned"
    client.object_exists = MagicMock(return_value=True)

    import orna_atlas.app.modules.sessions.service as sessions_service

    monkeypatch.setattr(sessions_service, "get_object_storage_client", lambda: client)

    grant = create_playback_grant(recording)

    assert grant.stream_url == "http://localhost:9000/presigned"
    assert grant.session_id == session_id
    assert grant.expires_at > datetime.now(UTC)
    client.object_exists.assert_called_once_with(rendition.storage_key)


def test_create_playback_grant_fails_closed_when_object_missing(monkeypatch) -> None:
    session_id = uuid4()
    rendition = SimpleNamespace(
        kind="streaming_rendition",
        processing_status="ready",
        storage_key=f"sessions/{session_id}/renditions/stream_rendition.wav",
    )
    recording = SimpleNamespace(id=session_id, media_assets=[rendition])
    client = ObjectStorageClient(
        ObjectStorageConfig(
            endpoint_url="http://minio:9000",
            access_key_id="test",
            secret_access_key="test",
        )
    )
    client.object_exists = MagicMock(return_value=False)

    import orna_atlas.app.modules.sessions.service as sessions_service

    monkeypatch.setattr(sessions_service, "get_object_storage_client", lambda: client)

    with pytest.raises(HTTPException) as error:
        create_playback_grant(recording)

    assert error.value.status_code == 409


def test_create_playback_grant_fails_closed_without_ready_rendition() -> None:
    session_id = uuid4()
    recording = SimpleNamespace(id=session_id, media_assets=[])

    with pytest.raises(HTTPException) as error:
        create_playback_grant(recording)

    assert error.value.status_code == 409


def test_object_storage_config_requires_credentials() -> None:
    assert ObjectStorageConfig(endpoint_url="http://localhost:9000").is_configured() is False
    assert ObjectStorageConfig(access_key_id="key", secret_access_key="secret").is_configured() is True


def test_presign_client_uses_public_endpoint() -> None:
    config = ObjectStorageConfig(
        endpoint_url="http://minio:9000",
        public_endpoint_url="http://localhost:9000",
        access_key_id="test",
        secret_access_key="test",
    )
    client = ObjectStorageClient(config)
    presign_client = client._get_presign_client()

    assert presign_client.meta.endpoint_url == "http://localhost:9000"


def test_storage_key_path_returns_local_file(tmp_path: Path) -> None:
    wav_path = tmp_path / "local.wav"
    wav_path.write_bytes(b"data")

    assert storage_key_path(str(wav_path)) == wav_path
    assert storage_key_path("sessions/remote.wav") is None


def _write_test_wav(path: Path) -> None:
    import math
    import struct
    import wave

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
