from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

_MAP_RE = re.compile(r'^#EXT-X-MAP:URI="([^"]+)"(?:,.*)?$')


class HlsError(ValueError):
    """Raised when generated HLS is unsafe or structurally invalid."""


def validate_hls_object_name(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or name.startswith("/")
        or "://" in name
        or len(path.parts) != 1
        or path.name in {".", ".."}
    ):
        raise HlsError(f"Unsafe HLS object URI: {name}")
    return name


def assemble_vod_playlist(
    playlists: list[Path], *, media_start: int = 0, source_start: int = 1
) -> tuple[str, list[tuple[Path, str]]]:
    """Combine independent media playlists without combining source audio.

    Every source keeps its own fMP4 initialization section. Media filenames are
    globally renumbered so all objects can share one immutable S3 prefix.
    """
    if not playlists:
        raise HlsError("At least one source playlist is required")

    output = ["#EXTM3U", "#EXT-X-VERSION:7", "#EXT-X-PLAYLIST-TYPE:VOD"]
    objects: list[tuple[Path, str]] = []
    bodies: list[list[str]] = []
    target_duration = 0
    media_index = media_start

    for source_index, path in enumerate(playlists, start=source_start):
        lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
        if not lines or lines[0] != "#EXTM3U" or "#EXT-X-ENDLIST" not in lines:
            raise HlsError(f"Not a complete VOD media playlist: {path}")
        body: list[str] = []
        has_map = False
        for line in lines[1:]:
            if line.startswith("#EXT-X-TARGETDURATION:"):
                target_duration = max(target_duration, int(line.partition(":")[2]))
            elif match := _MAP_RE.match(line):
                source_name = validate_hls_object_name(match.group(1))
                target_name = f"init_{source_index:04d}.mp4"
                objects.append((path.parent / source_name, target_name))
                body.append(f'#EXT-X-MAP:URI="{target_name}"')
                has_map = True
            elif line == "#EXT-X-ENDLIST" or line.startswith(
                ("#EXT-X-VERSION", "#EXT-X-PLAYLIST-TYPE", "#EXT-X-MEDIA-SEQUENCE")
            ):
                continue
            elif line.startswith("#"):
                if line.startswith("#EXT-X-KEY"):
                    raise HlsError("Encrypted child playlists are not supported")
                body.append(line)
            else:
                source_name = validate_hls_object_name(line)
                target_name = f"segment_{media_index:06d}.m4s"
                media_index += 1
                objects.append((path.parent / source_name, target_name))
                body.append(target_name)
        if not has_map:
            raise HlsError(f"fMP4 playlist is missing EXT-X-MAP: {path}")
        bodies.append(body)

    output.append(f"#EXT-X-TARGETDURATION:{target_duration}")
    output.append("#EXT-X-MEDIA-SEQUENCE:0")
    for index, body in enumerate(bodies):
        if index:
            output.append("#EXT-X-DISCONTINUITY")
        output.extend(body)
    output.append("#EXT-X-ENDLIST")
    return "\n".join(output) + "\n", objects
