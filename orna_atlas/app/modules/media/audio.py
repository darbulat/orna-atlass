from __future__ import annotations

import hashlib
import math
import wave
from array import array
from pathlib import Path
from uuid import UUID

from orna_atlas.app.integrations.s3 import get_object_storage_client
from orna_atlas.app.modules.media.models import MediaAsset
from orna_atlas.app.modules.media.storage import materialize_storage, storage_reference

WAVEFORM_BUCKETS = 64
PRIVATE_METADATA_KEYS = {"object_key", "s3_key", "source_storage_key", "storage_key"}


def extract_audio_metadata(asset: MediaAsset) -> dict:
    metadata = asset.metadata_ if isinstance(asset.metadata_, dict) else {}
    with materialize_storage(asset.storage_key) as path:
        if path is not None:
            wav_metadata = _extract_wav_metadata(path)
            return {
                **wav_metadata,
                "checksum": asset.checksum or sha256_file(path),
                "source": "wave",
            }
    declared_duration = asset.duration_seconds or int_or_none(metadata.get("duration_seconds"))
    return {
        "bit_depth": metadata.get("bit_depth"),
        "channels": metadata.get("channels"),
        "checksum": asset.checksum,
        "duration_seconds": declared_duration,
        "frame_rate_hz": metadata.get("frame_rate_hz"),
        "size_bytes": asset.size_bytes,
        "source": "declared",
    }


def generate_waveform(asset: MediaAsset, *, metadata: dict | None = None) -> dict:
    with materialize_storage(asset.storage_key) as path:
        peaks = _waveform_peaks_from_wav(path) if path is not None else _deterministic_peaks(asset)
    duration_seconds = int_or_none((metadata or {}).get("duration_seconds")) or asset.duration_seconds
    sample_rate = max(1, round(len(peaks) / duration_seconds)) if duration_seconds else 1
    return {"peaks": peaks, "sample_rate": sample_rate, "status": "generated"}


def upload_streaming_rendition(source_asset: MediaAsset, rendition: MediaAsset) -> None:
    storage_client = get_object_storage_client()
    if not storage_client.is_configured():
        raise RuntimeError("Object storage is not configured")
    source_ref = storage_reference(source_asset.storage_key, client=storage_client)
    if source_ref.kind == "s3" and source_ref.key is not None:
        storage_client.copy_object(
            source_ref.key,
            rendition.storage_key,
            source_bucket=source_ref.bucket,
            content_type=rendition.mime_type,
        )
        return
    with materialize_storage(source_asset.storage_key, client=storage_client) as path:
        if path is None:
            raise FileNotFoundError(f"Source audio not found: {source_asset.storage_key}")
        storage_client.upload_file(path, rendition.storage_key, content_type=rendition.mime_type)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def streaming_rendition_key(asset: MediaAsset, rendition_id: UUID | None = None) -> str:
    version_id = rendition_id or asset.id
    return f"sessions/{asset.session_id}/renditions/{asset.id}/{version_id}.wav"


def public_audio_metadata(metadata: dict) -> dict:
    return {key: value for key, value in metadata.items() if key not in PRIVATE_METADATA_KEYS}


def int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_wav_metadata(path: Path) -> dict:
    with wave.open(str(path), "rb") as wav_file:
        frame_count = wav_file.getnframes()
        frame_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
    return {
        "bit_depth": sample_width * 8,
        "channels": channels,
        "duration_seconds": int(round(frame_count / frame_rate)) if frame_rate else None,
        "frame_count": frame_count,
        "frame_rate_hz": frame_rate,
        "size_bytes": path.stat().st_size,
    }


def _waveform_peaks_from_wav(path: Path, buckets: int = WAVEFORM_BUCKETS) -> list[float]:
    with wave.open(str(path), "rb") as wav_file:
        sample_width = wav_file.getsampwidth()
        total_samples = wav_file.getnframes() * wav_file.getnchannels()
        if total_samples <= 0:
            return []
        bucket_count = min(buckets, total_samples)
        bucket_size = max(1, math.ceil(total_samples / bucket_count))
        raw_peaks = [0] * bucket_count
        sample_index = 0
        while raw := wav_file.readframes(8192):
            for sample in _pcm_samples(raw, sample_width):
                bucket_index = min(sample_index // bucket_size, bucket_count - 1)
                raw_peaks[bucket_index] = max(raw_peaks[bucket_index], abs(sample))
                sample_index += 1
    max_amplitude = float(max(1, 2 ** (sample_width * 8 - 1) - 1))
    return [round(min(1.0, peak / max_amplitude), 4) for peak in raw_peaks]


def _pcm_samples(raw: bytes, sample_width: int) -> list[int]:
    if sample_width == 1:
        return [byte - 128 for byte in raw]
    if sample_width in {2, 4}:
        samples = array("h" if sample_width == 2 else "i")
        samples.frombytes(raw)
        return list(samples)
    if sample_width == 3:
        return [
            int.from_bytes(raw[index : index + 3], "little", signed=True)
            for index in range(0, len(raw) - 2, 3)
        ]
    return []


def _deterministic_peaks(asset: MediaAsset, buckets: int = WAVEFORM_BUCKETS) -> list[float]:
    seed = hashlib.sha256(f"{asset.storage_key}:{asset.checksum or ''}".encode()).digest()
    values: list[int] = []
    while len(values) < buckets:
        seed = hashlib.sha256(seed).digest()
        values.extend(seed)
    return [round(0.05 + (value / 255) * 0.9, 4) for value in values[:buckets]]
