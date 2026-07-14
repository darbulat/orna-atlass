"""Measure long-form metadata/waveform stages without storing generated audio in git."""

from __future__ import annotations

import argparse
import json
import resource
import struct
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from orna_atlas.app.modules.media.audio import extract_audio_metadata, generate_waveform
from orna_atlas.app.workers.audio_pipeline import audio_job_timeout_seconds


def _write_sparse_wav(path: Path, *, duration_seconds: int, sample_rate: int) -> None:
    channels = 1
    sample_width = 2
    data_size = duration_seconds * sample_rate * channels * sample_width
    if data_size > 0xFFFFFFFF - 36:
        raise ValueError("generated WAV would exceed the RIFF 32-bit size limit")
    byte_rate = sample_rate * channels * sample_width
    block_align = channels * sample_width
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,
        b"data",
        data_size,
    )
    with path.open("wb") as output:
        output.write(header)
        output.truncate(len(header) + data_size)


def _measure(duration_hours: float, *, sample_rate: int) -> dict[str, float | int]:
    duration_seconds = round(duration_hours * 3600)
    with tempfile.TemporaryDirectory(prefix="orna-long-form-") as directory:
        path = Path(directory) / f"{duration_hours:g}h.wav"
        _write_sparse_wav(
            path,
            duration_seconds=duration_seconds,
            sample_rate=sample_rate,
        )
        asset = SimpleNamespace(
            id=uuid4(),
            session_id=uuid4(),
            storage_key=str(path),
            checksum=None,
            duration_seconds=None,
            size_bytes=None,
            metadata_={},
        )
        started = time.perf_counter()
        metadata = extract_audio_metadata(asset)
        metadata_seconds = time.perf_counter() - started
        started = time.perf_counter()
        waveform = generate_waveform(asset, metadata=metadata)
        waveform_seconds = time.perf_counter() - started
        stat = path.stat()
        return {
            "duration_hours": duration_hours,
            "duration_seconds": duration_seconds,
            "logical_size_bytes": stat.st_size,
            "allocated_size_bytes": stat.st_blocks * 512,
            "metadata_seconds": round(metadata_seconds, 4),
            "waveform_seconds": round(waveform_seconds, 4),
            "total_seconds": round(metadata_seconds + waveform_seconds, 4),
            "waveform_points": len(waveform["peaks"]),
            "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "configured_job_timeout_seconds": audio_job_timeout_seconds(
                duration_seconds
            ),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hours",
        type=float,
        nargs="+",
        default=[1.0, 6.0],
        help="WAV durations to measure (default: 1 6)",
    )
    parser.add_argument("--sample-rate", type=int, default=8000)
    args = parser.parse_args()
    if args.sample_rate < 1000 or any(hours <= 0 for hours in args.hours):
        parser.error("--sample-rate and every --hours value must be positive")
    payload = {
        "sample_rate_hz": args.sample_rate,
        "channels": 1,
        "sample_width_bytes": 2,
        "sparse_fixture": True,
        "runs": [_measure(hours, sample_rate=args.sample_rate) for hours in args.hours],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
