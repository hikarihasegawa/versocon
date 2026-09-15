"""FEAT-C2: video — estrazione audio (MP3/M4A) e creazione GIF animata.

Copre: validazioni senza ffmpeg, comportamento con ffmpeg assente, esecuzione
reale con ffmpeg presente (skip automatico se manca), contratto HTTP con
round-trip /api/file, nomi file unicode, soglia di tempo e controlli statici UI.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from converters import video as vidconv  # noqa: E402
from PIL import Image  # noqa: E402

STATIC = ROOT / "static"
I18N = STATIC / "i18n"
LANGS = ("it", "en", "es", "fr", "de", "pt", "zh", "ja")


def _ff() -> str | None:
    return vidconv._find_ffmpeg()


requires_ffmpeg = pytest.mark.skipif(_ff() is None, reason="ffmpeg non installato")


@pytest.fixture()
def client():
    return TestClient(app)


def _make_video(d: Path, name: str = "src.mp4", with_audio: bool = False) -> Path:
    """Genera un breve video di test (testsrc, 1s 128x96@10fps), con audio opzionale."""
    src = d / name
    cmd = [_ff(), "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=128x96:rate=10"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-loglevel", "error", str(src)]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if r.returncode != 0 or not src.exists():
        pytest.skip(f"impossibile creare video sorgente: {r.stderr.decode('utf-8', 'replace')[-200:]}")
    return src


# ── unit: validazioni (indipendenti da ffmpeg) ──

def test_extract_audio_rejects_missing_src():
    with tempfile.TemporaryDirectory() as d:
        with pytest.raises(ValueError):
            vidconv.extract_audio(str(Path(d) / "manca.mp4"), str(Path(d) / "out.mp3"))


def test_extract_audio_rejects_bad_fmt():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src.mp4"
        src.write_bytes(b"finto")
        with pytest.raises(ValueError, match="non supportato"):
            vidconv.extract_audio(str(src), str(Path(d) / "out.ogg"), fmt="ogg")


def test_gif_rejects_out_of_range_params():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src.mp4"
        src.write_bytes(b"finto")
        out = Path(d) / "out.gif"
        for kwargs in ({"fps": 0}, {"fps": 99}, {"width": 10}, {"width": 99999},
                       {"start": -1}, {"duration": 0}):
            with pytest.raises(ValueError):
                vidconv.video_to_gif(str(src), str(out), **kwargs)


def test_gif_forces_gif_suffix():
    """Un percorso senza estensione .gif viene corretto dal converter."""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src.mp4"
        src.write_bytes(b"finto")
        vidconv._FFMPEG_CACHE = (True, None)  # ffmpeg assente: si ferma dopo le validazioni
        try:
            with pytest.raises(vidconv.MissingFfmpegError):
                vidconv.video_to_gif(str(src), str(Path(d) / "out.mp4"))
        finally:
            vidconv._reset_ffmpeg_cache()


def test_missing_ffmpeg_raises_clear_error(monkeypatch):
    monkeypatch.setattr(vidconv, "_find_ffmpeg", lambda: None)
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src.mp4"
        src.write_bytes(b"finto")
        with pytest.raises(vidconv.MissingFfmpegError) as e1:
            vidconv.extract_audio(str(src), str(Path(d) / "out.mp3"))
        with pytest.raises(vidconv.MissingFfmpegError) as e2:
            vidconv.video_to_gif(str(src), str(Path(d) / "out.gif"))
    assert "ffmpeg" in str(e1.value).lower()
    assert "ffmpeg" in str(e2.value).lower()


# ── unit: esecuzione reale (solo con ffmpeg) ──

@requires_ffmpeg
def test_extract_audio_mp3_real():
    with tempfile.TemporaryDirectory() as d:
        src = _make_video(Path(d), with_audio=True)
        dst = Path(d) / "out.mp3"
        size = vidconv.extract_audio(str(src), str(dst), fmt="mp3")
        assert dst.exists() and size == dst.stat().st_size > 0
        head = dst.read_bytes()[:3]
        assert head == b"ID3" or head[0] == 0xFF, f"header MP3 inatteso: {head!r}"


@requires_ffmpeg
def test_extract_audio_m4a_real():
    with tempfile.TemporaryDirectory() as d:
        src = _make_video(Path(d), with_audio=True)
        dst = Path(d) / "out.m4a"
        size = vidconv.extract_audio(str(src), str(dst), fmt="m4a")
        assert dst.exists() and size == dst.stat().st_size > 0
        assert b"ftyp" in dst.read_bytes()[:16], "container M4A senza box ftyp"


@requires_ffmpeg
def test_extract_audio_no_track_clean_error():
    """Un video muto non deve produrre un errore ffmpeg grezzo ma NoAudioTrackError."""
    with tempfile.TemporaryDirectory() as d:
        src = _make_video(Path(d), with_audio=False)
        with pytest.raises(vidconv.NoAudioTrackError) as e:
            vidconv.extract_audio(str(src), str(Path(d) / "out.mp3"))
    assert "audio" in str(e.value).lower()


@requires_ffmpeg
def test_gif_is_animated_and_scaled():
    with tempfile.TemporaryDirectory() as d:
        src = _make_video(Path(d))
        dst = Path(d) / "out.gif"
        size = vidconv.video_to_gif(str(src), str(dst), fps=10, width=96)
        assert dst.exists() and size == dst.stat().st_size > 0
        assert dst.read_bytes()[:6] in (b"GIF87a", b"GIF89a")
        with Image.open(dst) as im:
            assert im.format == "GIF"
            assert im.is_animated and im.n_frames > 1
            assert im.width == 96


@requires_ffmpeg
def test_gif_start_duration_trims():
    """Il ritaglio (start/duration) deve ridurre i frame rispetto al video intero."""
    with tempfile.TemporaryDirectory() as d:
        src = _make_video(Path(d))
        full, cut = Path(d) / "full.gif", Path(d) / "cut.gif"
        vidconv.video_to_gif(str(src), str(full), fps=10, width=96)
        vidconv.video_to_gif(str(src), str(cut), fps=10, width=96, start=0.2, duration=0.4)
        with Image.open(full) as a, Image.open(cut) as b:
            assert b.n_frames < a.n_frames, (b.n_frames, a.n_frames)


@requires_ffmpeg
def test_gif_time_threshold():
    """Soglia non funzionale: una GIF da 1s deve chiudersi in tempi ragionevoli."""
    with tempfile.TemporaryDirectory() as d:
        src = _make_video(Path(d))
        t0 = time.perf_counter()
        vidconv.video_to_gif(str(src), str(Path(d) / "out.gif"), fps=10, width=240)
        elapsed = time.perf_counter() - t0
    assert elapsed < 60, f"GIF troppo lenta: {elapsed:.1f}s"


# ── contratto HTTP ──

def test_api_video_audio_rejects_non_video(client):
    r = client.post("/api/video-audio", files={"file": ("nota.txt", b"ciao", "text/plain")})
    assert r.status_code == 400


def test_api_video_audio_rejects_empty(client):
    r = client.post("/api/video-audio", files={"file": ("a.mp4", b"", "video/mp4")})
    assert r.status_code == 400


def test_api_video_audio_rejects_bad_fmt(client):
    r = client.post("/api/video-audio", data={"fmt": "ogg"},
                    files={"file": ("a.mp4", b"xxx", "video/mp4")})
    assert r.status_code == 400


def test_api_video_gif_rejects_bad_params(client):
    r = client.post("/api/video-gif", data={"width": "5"},
                    files={"file": ("a.mp4", b"xxx", "video/mp4")})
    assert r.status_code == 400


@requires_ffmpeg
def test_api_video_audio_real_roundtrip(client):
    with tempfile.TemporaryDirectory() as d:
        data = _make_video(Path(d), with_audio=True).read_bytes()
        r = client.post("/api/video-audio", data={"fmt": "mp3"},
                        files={"file": ("clip.mp4", data, "video/mp4")})
        assert r.status_code == 200, r.text
        res = r.json()["results"][0]
        assert res["name"] == "clip.mp3" and res["size"] > 0
        dl = client.get(res["download"])
        assert dl.status_code == 200
        assert len(dl.content) == res["size"]


@requires_ffmpeg
def test_api_video_gif_real_unicode_name(client):
    with tempfile.TemporaryDirectory() as d:
        data = _make_video(Path(d)).read_bytes()
        name = "café 動画.mp4"
        r = client.post("/api/video-gif", data={"fps": "5", "width": "64"},
                        files={"file": (name, data, "video/mp4")})
        assert r.status_code == 200, r.text
        res = r.json()["results"][0]
        assert res["name"] == "café 動画.gif", res["name"]
        dl = client.get(res["download"])
        assert dl.status_code == 200
        assert dl.content[:6] in (b"GIF87a", b"GIF89a")


# ── UI statica + i18n ──

def test_video_tab_has_operation_selector():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for el in ['id="videoOp"', 'id="vidTranscodeRow"', 'id="vidGifRow"',
               'id="videoGifFps"', 'id="videoGifWidth"', 'id="videoGifStart"', 'id="videoGifDur"']:
        assert el in html, f"{el} mancante"
    assert html.count('<option value="audio_') == 2


def test_app_js_dispatches_new_endpoints():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '"/api/video-audio"' in js
    assert '"/api/video-gif"' in js
    assert 'fd.append("fmt", op === "audio_m4a" ? "m4a" : "mp3")' in js


def test_i18n_keys_present_all_languages():
    import json
    for lang in LANGS:
        data = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))
        for key in ("vid.op", "vid.op_gif", "vid.gif_fps", "vid.gif_width",
                    "vid.gif_start", "vid.gif_duration", "dyn.audio_extracted",
                    "dyn.gif_created", "api.video_no_audio"):
            assert key in data, f"{lang}: manca {key}"
