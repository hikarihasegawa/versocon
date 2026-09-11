"""Tesseract e ffmpeg vanno lanciati senza finestra console: l'exe non ha console
e su Windows ogni programma a riga di comando aprirebbe un cmd per un attimo."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converters import extract as ex  # noqa: E402
from converters import video as vid  # noqa: E402
from converters.proc import NO_WINDOW  # noqa: E402

FLAG = NO_WINDOW.get("creationflags", 0)


class _Done:
    """Risultato finto di subprocess.run."""

    def __init__(self, stdout: bytes = b""):
        self.returncode, self.stdout, self.stderr = 0, stdout, b""


def test_no_window_flag():
    if sys.platform == "win32":
        assert NO_WINDOW == {"creationflags": subprocess.CREATE_NO_WINDOW}
    else:
        assert NO_WINDOW == {}


def test_tesseract_probe_no_console_and_cached(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd[-1], kw.get("creationflags", 0)))
        if cmd[-1] == "--list-langs":
            return _Done(b'List of available languages in "C:/tessdata/" (3):\neng\nita\nosd\n')
        return _Done(b"tesseract v5.4.0.20240606\n leptonica-1.84.1\n")

    monkeypatch.setattr(ex, "_get_tesseract_cmd", lambda: "tesseract")
    monkeypatch.setattr(ex, "_PROBE", None)
    monkeypatch.setattr(ex.subprocess, "run", fake_run)
    for _ in range(3):
        assert ex._tesseract_probe() == {"version": "5.4.0.20240606", "languages": ["eng", "ita", "osd"]}
    assert calls == [("--version", FLAG), ("--list-langs", FLAG)]  # una volta sola, senza console


def test_tesseract_probe_missing_binary(monkeypatch):
    monkeypatch.setattr(ex, "_get_tesseract_cmd", lambda: None)
    monkeypatch.setattr(ex, "_PROBE", None)
    assert ex._tesseract_probe() == {"version": None, "languages": []}


def test_ffmpeg_probe_no_console(monkeypatch):
    calls = []
    monkeypatch.setattr(vid, "_FFMPEG_CACHE", None)
    monkeypatch.setattr(vid.shutil, "which", lambda name: "ffmpeg")
    monkeypatch.setattr(vid.subprocess, "run", lambda cmd, **kw: calls.append(kw.get("creationflags", 0)) or _Done())
    assert vid._find_ffmpeg() == "ffmpeg"
    assert calls == [FLAG]


def test_transcode_no_console(monkeypatch, tmp_path):
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    calls = []
    monkeypatch.setattr(vid, "_find_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(vid.subprocess, "run", lambda cmd, **kw: calls.append(kw.get("creationflags", 0)) or _Done())
    vid.transcode(str(src), str(tmp_path / "out.mp4"))
    assert calls == [FLAG]
