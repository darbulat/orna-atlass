from pathlib import Path

from orna_atlas.app.modules.media.hls_transcode import ffmpeg_hls_command, ffprobe_duration_ms


def test_ffmpeg_hls_command_preserves_channel_layout(tmp_path: Path):
    command = ffmpeg_hls_command(tmp_path / "source.wav", tmp_path / "out")
    assert command[0] == "ffmpeg"
    assert "-ac" not in command
    assert command[command.index("-b:a") + 1] == "160k"
    assert command[command.index("-ar") + 1] == "48000"
    assert command[command.index("-hls_time") + 1] == "10"
    assert command[command.index("-hls_segment_type") + 1] == "fmp4"
    assert command[-1].endswith("index.m3u8")


def test_ffprobe_duration_ms_parses_fraction(monkeypatch):
    class Result:
        stdout = "7200.125000\n"

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: Result())
    assert ffprobe_duration_ms(Path("source.wav")) == 7_200_125
