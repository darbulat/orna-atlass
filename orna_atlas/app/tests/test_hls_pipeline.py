from pathlib import Path

from orna_atlas.app.modules.media.hls_pipeline import package_segmented_hls


class FakeStorage:
    def __init__(self):
        self.events: list[tuple[str, str]] = []
        self.keys: set[str] = set()
        self.manifest = b""

    def download_file(self, key, destination, *, bucket=None):
        self.events.append(("download", key))
        Path(destination).write_bytes(b"wav")

    def upload_file(self, source, key, *, bucket=None, content_type=None):
        assert Path(source).exists()
        self.events.append(("upload", key))
        self.keys.add(key)

    def put_bytes(self, key, body, *, bucket=None, content_type=None):
        self.events.append(("put", key))
        self.keys.add(key)
        self.manifest = body

    def object_exists(self, storage_key, *, bucket=None):
        return storage_key in self.keys


def test_pipeline_processes_sources_sequentially_and_publishes_manifest_last(tmp_path, monkeypatch):
    durations = iter([1000, 2000])
    monkeypatch.setattr(
        "orna_atlas.app.modules.media.hls_pipeline.ffprobe_duration_ms",
        lambda source: next(durations),
    )

    def fake_transcode(source: Path, output: Path) -> Path:
        output.mkdir()
        (output / "init.mp4").write_bytes(b"init")
        (output / "segment_000000.m4s").write_bytes(b"segment")
        playlist = output / "index.m3u8"
        playlist.write_text(
            '#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXT-X-MAP:URI="init.mp4"\n'
            '#EXTINF:10.0,\nsegment_000000.m4s\n#EXT-X-ENDLIST\n'
        )
        return playlist

    monkeypatch.setattr(
        "orna_atlas.app.modules.media.hls_pipeline.transcode_wav_to_hls", fake_transcode
    )
    storage = FakeStorage()
    result = package_segmented_hls(storage, ["one.wav", "two.wav"], "sessions/s/hls/g")

    assert result.duration_ms == (1000, 2000)
    assert result.manifest_key == "sessions/s/hls/g/index.m3u8"
    assert storage.events[-1] == ("put", result.manifest_key)
    text = storage.manifest.decode()
    assert "#EXT-X-DISCONTINUITY" in text
    assert text.count("#EXT-X-MEDIA-SEQUENCE:") == 1
    assert 'URI="init_0001.mp4"' in text
    assert 'URI="init_0002.mp4"' in text
    assert "segment_000000.m4s" in text
    assert "segment_000001.m4s" in text
