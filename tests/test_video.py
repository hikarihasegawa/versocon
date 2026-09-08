"""Test converter video: validazioni, caso ffmpeg assente, transcode reale (se ffmpeg è presente)."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converters import video as vidconv  # noqa: E402


def test_video_is_supported():
    assert vidconv.video_is_supported("clip.MP4")
    assert vidconv.video_is_supported("a.mkv")
    assert vidconv.video_is_supported(".mov")
    assert not vidconv.video_is_supported("a.txt")
    assert not vidconv.video_is_supported("a.png")


def test_out_container_mp4():
    ext, vcodec, acodec = vidconv._out_container("mp4")
    assert ext == "mp4"
    assert vcodec == "libx264"
    assert acodec == "aac"


def test_out_container_webm():
    ext, vcodec, acodec = vidconv._out_container("webm")
    assert ext == "webm"
    assert vcodec == "libvpx-vp9"
    assert acodec == "libvorbis"


def test_out_container_alias_h264():
    assert vidconv._out_container("h264")[0] == "mp4"


def test_out_container_rejects():
    with pytest.raises(ValueError):
        vidconv._out_container("avi")


def test_transcode_rejects_missing_src():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(ValueError):
            vidconv.transcode(str(Path(d) / "manca.mp4"), str(Path(d) / "out.mp4"))


def test_missing_ffmpeg_raises_clear_error(monkeypatch):
    """Con ffmpeg forzato assente il transcode alza MissingFfmpegError (non un crash)."""
    monkeypatch.setattr(vidconv, "_find_ffmpeg", lambda: None)
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src.mp4"
        src.write_bytes(b"finto")
        with pytest.raises(vidconv.MissingFfmpegError) as exc:
            vidconv.transcode(str(src), str(Path(d) / "out.mp4"))
    assert "ffmpeg" in str(exc.value).lower()


# ---------------- transcode reale (solo se ffmpeg è installato) ----------------

def _ff() -> str | None:
    return vidconv._find_ffmpeg()


def _make_source_video(d: Path, name: str = "src.mp4") -> Path:
    """Crea un breve video sorgente valido (lavfi testsrc) con ffmpeg in d/name."""
    src = d / name
    cmd = [
        _ff(), "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=128x96:rate=10",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-loglevel", "error", str(src),
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if r.returncode != 0 or not src.exists():
        pytest.skip(f"impossibile creare video sorgente: {r.stderr.decode('utf-8', 'replace')[-200:]}")
    return src


@pytest.mark.skipif(_ff() is None, reason="ffmpeg non installato")
def test_transcode_real_mp4():
    with tempfile.TemporaryDirectory() as d:
        src = _make_source_video(Path(d))
        dst = Path(d) / "out.mp4"
        size = vidconv.transcode(str(src), str(dst), fmt="mp4")
        assert dst.exists() and dst.stat().st_size > 0
        assert size == dst.stat().st_size


@pytest.mark.skipif(_ff() is None, reason="ffmpeg non installato")
def test_transcode_real_webm():
    with tempfile.TemporaryDirectory() as d:
        src = _make_source_video(Path(d))
        dst = Path(d) / "out.webm"
        size = vidconv.transcode(str(src), str(dst), fmt="webm", crf=30)
        assert dst.exists() and dst.stat().st_size > 0
        assert size == dst.stat().st_size


@pytest.mark.skipif(_ff() is None, reason="ffmpeg non installato")
def test_transcode_corrupt_src_fails_cleanly():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "garbage.mp4"
        src.write_bytes(b"non sono un video \x00\x01\x02")
        with pytest.raises(ValueError):
            vidconv.transcode(str(src), str(Path(d) / "out.mp4"), fmt="mp4")


@pytest.mark.skipif(_ff() is None, reason="ffmpeg non installato")
def test_ffmpeg_available_flag():
    assert vidconv.ffmpeg_available() is True


def test_reset_cache_no_crash():
    vidconv._reset_ffmpeg_cache()
    _ = vidconv.ffmpeg_available()  # non deve crashare; valore dipende dall'ambiente
