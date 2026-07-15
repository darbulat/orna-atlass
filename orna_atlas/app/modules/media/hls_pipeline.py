from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from orna_atlas.app.modules.media.hls import assemble_vod_playlist
from orna_atlas.app.modules.media.hls_transcode import ffprobe_duration_ms, transcode_wav_to_hls


class HlsStorage(Protocol):
    def download_file(self, key: str, destination: Path | str, *, bucket: str | None = None) -> None: ...
    def upload_file(
        self,
        source: Path | str,
        key: str,
        *,
        bucket: str | None = None,
        content_type: str | None = None,
    ) -> None: ...
    def put_bytes(
        self,
        key: str,
        body: bytes,
        *,
        bucket: str | None = None,
        content_type: str | None = None,
    ) -> None: ...
    def object_exists(self, storage_key: str, *, bucket: str | None = None) -> bool: ...


@dataclass(frozen=True)
class PackagedHls:
    manifest_key: str
    object_keys: tuple[str, ...]
    duration_ms: tuple[int, ...]


def _playlist_body(playlist: str) -> tuple[int, list[str]]:
    target = 0
    body: list[str] = []
    for line in playlist.splitlines():
        if line.startswith("#EXT-X-TARGETDURATION:"):
            target = int(line.partition(":")[2])
        elif line not in {
            "#EXTM3U",
            "#EXT-X-VERSION:7",
            "#EXT-X-PLAYLIST-TYPE:VOD",
            "#EXT-X-MEDIA-SEQUENCE:0",
            "#EXT-X-ENDLIST",
        }:
            body.append(line)
    return target, body


def package_segmented_hls(
    storage: HlsStorage,
    source_keys: list[str],
    generation_prefix: str,
    uploaded_keys: list[str] | None = None,
) -> PackagedHls:
    """Package sources sequentially, publishing the final manifest last."""
    if not source_keys:
        raise ValueError("At least one source is required")
    prefix = generation_prefix.strip("/")
    if not prefix:
        raise ValueError("A generation prefix is required")

    media_index = 0
    target_duration = 0
    bodies: list[list[str]] = []
    object_keys: list[str] = []
    durations: list[int] = []

    for source_index, source_key in enumerate(source_keys, start=1):
        with tempfile.TemporaryDirectory(prefix="orna-hls-") as temporary:
            root = Path(temporary)
            source = root / "source.wav"
            output = root / "hls"
            storage.download_file(source_key, source)
            durations.append(ffprobe_duration_ms(source))
            child = transcode_wav_to_hls(source, output)
            normalized, objects = assemble_vod_playlist(
                [child], media_start=media_index, source_start=source_index
            )
            media_index += sum(name.endswith(".m4s") for _, name in objects)
            part_target, body = _playlist_body(normalized)
            target_duration = max(target_duration, part_target)

            for local_path, object_name in objects:
                key = f"{prefix}/{object_name}"
                content_type = "video/mp4" if object_name.endswith(".mp4") else "video/iso.segment"
                storage.upload_file(local_path, key, content_type=content_type)
                if uploaded_keys is not None:
                    uploaded_keys.append(key)
                if not storage.object_exists(key):
                    raise RuntimeError(f"Uploaded HLS object cannot be verified: {key}")
                object_keys.append(key)
            bodies.append(body)

    manifest_lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        f"#EXT-X-TARGETDURATION:{target_duration}",
        "#EXT-X-MEDIA-SEQUENCE:0",
    ]
    for index, body in enumerate(bodies):
        if index:
            manifest_lines.append("#EXT-X-DISCONTINUITY")
        manifest_lines.extend(body)
    manifest_lines.append("#EXT-X-ENDLIST")
    manifest_key = f"{prefix}/index.m3u8"
    storage.put_bytes(
        manifest_key,
        ("\n".join(manifest_lines) + "\n").encode(),
        content_type="application/vnd.apple.mpegurl",
    )
    if uploaded_keys is not None:
        uploaded_keys.append(manifest_key)
    if not storage.object_exists(manifest_key):
        raise RuntimeError("Published HLS manifest cannot be verified")
    object_keys.append(manifest_key)
    return PackagedHls(manifest_key, tuple(object_keys), tuple(durations))
