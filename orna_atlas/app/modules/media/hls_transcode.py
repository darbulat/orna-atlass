from __future__ import annotations

import subprocess
from pathlib import Path


class TranscodeError(RuntimeError):
    pass


def ffmpeg_hls_command(source: Path, output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-f",
        "hls",
        "-hls_time",
        "10",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_type",
        "fmp4",
        "-hls_fmp4_init_filename",
        "init.mp4",
        "-hls_segment_filename",
        str(output_dir / "segment_%06d.m4s"),
        str(output_dir / "index.m3u8"),
    ]


def transcode_wav_to_hls(source: Path, output_dir: Path) -> Path:
    command = ffmpeg_hls_command(source, output_dir)
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", None)
        raise TranscodeError(f"ffmpeg HLS transcode failed: {stderr or exc}") from exc
    playlist = output_dir / "index.m3u8"
    if not playlist.is_file():
        raise TranscodeError("ffmpeg did not produce index.m3u8")
    return playlist


def ffprobe_duration_ms(source: Path) -> int:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(source),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        duration_ms = round(float(result.stdout.strip()) * 1000)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise TranscodeError(f"ffprobe duration failed: {exc}") from exc
    if duration_ms <= 0:
        raise TranscodeError("ffprobe returned a non-positive duration")
    return duration_ms
