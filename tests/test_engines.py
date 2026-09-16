"""Ricerca dei motori esterni (ffmpeg/Tesseract): PATH, WinGet, choco, scoop, bundle."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converters import engines  # noqa: E402
from converters import extract as ex  # noqa: E402
from converters import video as vid  # noqa: E402
from app.main import app  # noqa: E402


class _Done:
    """Risultato finto di subprocess.run (ffmpeg -version ok)."""

    def __init__(self):
        self.returncode, self.stdout, self.stderr = 0, b"", b""


def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"stub")
    return p


def test_find_binary_extra_dir(monkeypatch):
    monkeypatch.setattr(engines.shutil, "which", lambda name: None)
    with tempfile.TemporaryDirectory() as d:
        exe = _touch(Path(d) / "versocon-engine-test.exe")
        assert engines.find_binary(("versocon-engine-test.exe",), extra_dirs=[d]) == str(exe)


def test_find_binary_missing(monkeypatch):
    monkeypatch.setattr(engines.shutil, "which", lambda name: None)
    monkeypatch.setattr(engines, "search_dirs", lambda **kw: [])
    with tempfile.TemporaryDirectory() as d:
        assert engines.find_binary(("versocon-engine-test.exe",), extra_dirs=[d]) is None


def test_find_binary_which_priority(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        _touch(Path(d) / "ffmpeg.exe")
        monkeypatch.setattr(
            engines.shutil, "which", lambda name: r"C:\tools\ffmpeg.exe" if name == "ffmpeg" else None
        )
        assert engines.find_binary(("ffmpeg", "ffmpeg.exe"), extra_dirs=[d]) == r"C:\tools\ffmpeg.exe"


def _set_bundle(monkeypatch, root: Path) -> Path:
    """Simula un bundle PyInstaller in `root`; ritorna `_internal` (sys._MEIPASS)."""
    meipass = root / "bundle"
    monkeypatch.setattr(engines.sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(engines.sys, "executable", str(root / "app" / "Versocon.exe"))
    return meipass


def test_bundled_dirs_layout(monkeypatch):
    """_internal/tesseract, _internal/ffmpeg, bin/ prima, poi accanto all'exe."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        meipass = _set_bundle(monkeypatch, root)
        exe_dir = root / "app"
        assert engines.bundled_dirs() == [
            meipass / "tesseract",
            meipass / "ffmpeg",
            meipass / "bin",
            exe_dir / "tesseract",
            exe_dir / "ffmpeg",
            exe_dir / "bin",
        ]


def test_find_binary_bundle_priority(monkeypatch):
    """Il motore bundle vince su PATH e cartelle di sistema."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        bundled = _touch(_set_bundle(monkeypatch, root) / "tesseract" / "tesseract.exe")
        monkeypatch.setattr(engines.shutil, "which", lambda name: r"C:\tools\tesseract.exe")
        monkeypatch.setattr(engines, "search_dirs", lambda **kw: [Path(r"C:\system")])
        assert engines.find_binary(("tesseract", "tesseract.exe")) == str(bundled)


def test_video_prefers_bundled_ffmpeg(monkeypatch):
    """ffmpeg bundle usato al posto di quello nel PATH."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        bundled = _touch(_set_bundle(monkeypatch, root) / "ffmpeg" / "ffmpeg.exe")
        monkeypatch.setattr(engines.shutil, "which", lambda name: r"C:\tools\ffmpeg.exe")
        monkeypatch.setattr(vid, "_FFMPEG_CACHE", None)
        monkeypatch.setattr(vid.subprocess, "run", lambda *a, **kw: _Done())
        assert vid._find_ffmpeg() == str(bundled)
        vid._reset_ffmpeg_cache()


def test_extract_prefers_bundled_tesseract(monkeypatch):
    """tesseract bundle usato al posto di quello nel PATH."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        bundled = _touch(_set_bundle(monkeypatch, root) / "tesseract" / "tesseract.exe")
        monkeypatch.setattr(engines.shutil, "which", lambda name: r"C:\tools\tesseract.exe")
        monkeypatch.setenv("TESSERACT_CMD", "")
        monkeypatch.setattr(ex, "_TESS_RESOLVED", False)
        monkeypatch.setattr(ex, "_TESS_CACHE", None)
        assert ex._get_tesseract_cmd() == str(bundled)


def test_search_dirs_windows_layout():
    """WinGet Packages/*/bin (bug winget PATH root) e le altre cartelle note."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        local = root / "Local"
        pkg_bin = _touch(
            local / "Microsoft" / "WinGet" / "Packages"
            / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
            / "ffmpeg-test_build" / "bin" / "versocon-ffmpeg-test.exe"
        ).parent
        tess = _touch(local / "Programs" / "Tesseract-OCR" / "versocon-tess-test.exe")
        env = {
            "LOCALAPPDATA": str(local),
            "ProgramData": str(root / "ProgramData"),
            "USERPROFILE": str(root / "home"),
        }
        dirs = engines.search_dirs(env=env)
        assert local / "Microsoft" / "WinGet" / "Links" in dirs
        assert pkg_bin in dirs
        assert root / "ProgramData" / "chocolatey" / "bin" in dirs
        assert root / "home" / "scoop" / "shims" in dirs
        assert engines.find_binary(("versocon-ffmpeg-test.exe",), env=env) == str(pkg_bin / "versocon-ffmpeg-test.exe")
        assert engines.find_binary(("versocon-tess-test.exe",), env=env) == str(tess)


def test_video_discovers_ffmpeg_outside_path(monkeypatch):
    """ffmpeg installato fuori PATH (winget per-utente) viene comunque trovato."""
    with tempfile.TemporaryDirectory() as d:
        exe = _touch(Path(d) / "ffmpeg.exe")
        monkeypatch.setattr(vid, "_FFMPEG_CACHE", None)
        monkeypatch.setattr(engines.shutil, "which", lambda name: None)
        monkeypatch.setattr(engines, "search_dirs", lambda **kw: [Path(d)])
        monkeypatch.setattr(vid.subprocess, "run", lambda *a, **kw: _Done())
        assert vid._find_ffmpeg() == str(exe)
        vid._reset_ffmpeg_cache()


def test_extract_discovers_tesseract_outside_path(monkeypatch):
    with tempfile.TemporaryDirectory() as d:
        exe = _touch(Path(d) / "tesseract.exe")
        monkeypatch.setattr(engines, "search_dirs", lambda **kw: [Path(d)])
        monkeypatch.setattr(engines.shutil, "which", lambda name: None)
        monkeypatch.setenv("TESSERACT_CMD", "")
        monkeypatch.setattr(ex, "_TESS_RESOLVED", False)
        monkeypatch.setattr(ex, "_TESS_CACHE", None)
        assert ex._get_tesseract_cmd() == str(exe)


def test_reset_ocr_cache():
    ex.reset_ocr_cache()
    assert ex._TESS_RESOLVED is False
    assert ex._TESS_CACHE is None
    assert ex._PROBE is None


def test_recheck_endpoint(monkeypatch):
    called = []
    monkeypatch.setattr(vid, "_reset_ffmpeg_cache", lambda: called.append("vid"))
    monkeypatch.setattr(ex, "reset_ocr_cache", lambda: called.append("ocr"))
    monkeypatch.setattr(vid, "ffmpeg_available", lambda: True)
    monkeypatch.setattr(ex, "ocr_info", lambda: {"available": False, "version": None, "languages": []})
    r = TestClient(app).post("/api/engines/recheck")
    assert r.status_code == 200
    assert r.json() == {
        "video": {"ffmpeg_available": True},
        "ocr": {"available": False, "version": None, "languages": []},
    }
    assert called == ["vid", "ocr"]
