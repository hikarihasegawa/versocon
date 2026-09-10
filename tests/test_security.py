"""Regressioni di sicurezza: path traversal, DNS rebinding, CSRF, limiti upload."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as m
from app.security import _strip_port, safe_child


@pytest.fixture()
def client():
    return TestClient(m.app)


# ── safe_child: identico su Linux e Windows ─────────────────────────────────
@pytest.mark.parametrize("bad", [
    "", ".", "..", "../x", "..\\x", "a/b", "a\\b",
    "C:\\Windows\\win.ini", "C:win.ini", "\server\\share\\f",
    "/etc/passwd", "file.txt:stream", "x\x00.png",
])
def test_safe_child_rejects(tmp_path, bad):
    assert safe_child(tmp_path, bad) is None


def test_safe_child_accepts_plain_name(tmp_path):
    (tmp_path / "foto-1.jpeg").write_bytes(b"x")
    assert safe_child(tmp_path, "foto-1.jpeg") == (tmp_path / "foto-1.jpeg").resolve()


# ── /api/file e /api/download ──────────────────────────────────────────────
@pytest.mark.parametrize("enc", [
    "C:%5CWindows%5Cwin.ini", "..%5C..%5Csecret.txt", "..", "C:win.ini",
])
def test_file_endpoint_blocks_traversal(client, enc):
    r = client.get(f"/api/file/{enc}")
    assert r.status_code == 404


def test_file_endpoint_serves_own_output(client):
    (m.OUT_DIR / "ok.txt").write_text("ciao", encoding="utf-8")
    r = client.get("/api/file/ok.txt")
    assert r.status_code == 200 and r.content == b"ciao"


def test_download_zip_ignores_traversal(client):
    (m.OUT_DIR / "inzip.txt").write_text("a", encoding="utf-8")
    r = client.get("/api/download", params={"names": "inzip.txt,..\\..\\x.txt,C:\\Windows\\win.ini"})
    assert r.status_code == 200
    import io
    import zipfile
    assert zipfile.ZipFile(io.BytesIO(r.content)).namelist() == ["inzip.txt"]


# ── Host / Origin ──────────────────────────────────────────────────────────
def test_foreign_host_rejected(client):
    r = client.get("/api/config", headers={"Host": "evil.example.com"})
    assert r.status_code == 400


@pytest.mark.parametrize("host", ["127.0.0.1:54321", "localhost:8321", "[::1]:9000"])
def test_local_hosts_accepted(client, host):
    assert client.get("/api/config", headers={"Host": host}).status_code == 200


def test_strip_port():
    assert _strip_port("127.0.0.1:1") == "127.0.0.1"
    assert _strip_port("[::1]:1") == "::1"
    assert _strip_port("LOCALHOST") == "localhost"


@pytest.mark.parametrize("origin", ["https://evil.example.com", "null", "file://"])
def test_cross_origin_post_rejected(client, origin):
    r = client.post("/api/support", headers={"Origin": origin})
    assert r.status_code == 403


def test_same_origin_post_passes_middleware(client, monkeypatch):
    monkeypatch.setattr(m, "_open_support_in_browser", lambda: None)
    r = client.post("/api/support", headers={"Origin": "http://127.0.0.1:54321"})
    assert r.status_code == 200


def test_cross_origin_get_still_allowed_for_readonly(client):
    # GET cross-origin non può leggere la risposta (niente CORS): resta permesso.
    assert client.get("/api/config", headers={"Origin": "https://evil.example.com"}).status_code == 200


# ── Letture limitate e sorgente video ──────────────────────────────────────
def test_read_capped_never_reads_everything():
    import io

    class U:
        file = io.BytesIO(b"x" * 1000)

    assert len(m._read_capped(U(), 10)) == 11


def test_video_source_is_unique_and_removed(client, monkeypatch):
    seen = []

    def fake_transcode(src, dst, fmt="mp4", crf=None):
        seen.append(Path(src))
        assert Path(src).is_file()
        Path(dst).write_bytes(b"out")
        return 3

    monkeypatch.setattr(m.vidconv, "transcode", fake_transcode)
    for _ in range(2):
        r = client.post("/api/convert-video", files={"file": ("clip.mp4", b"data", "video/mp4")},
                        data={"fmt": "mp4"})
        assert r.status_code == 200, r.text
    assert seen[0] != seen[1]
    assert not any(p.exists() for p in seen)


def test_video_limit_enforced_without_full_read(client, monkeypatch):
    monkeypatch.setattr(m.vidconv, "MAX_VIDEO_BYTES", 5)
    r = client.post("/api/convert-video", files={"file": ("clip.mp4", b"0123456789", "video/mp4")},
                    data={"fmt": "mp4"})
    assert r.status_code == 400
    assert not list(m.OUT_DIR.glob(".src-*"))


def test_out_dir_is_private_session_dir():
    assert m.OUT_DIR.name.startswith("versocon-")
    assert m.OUT_DIR.parent == Path(m.tempfile.gettempdir())


def test_purge_stale_outputs(tmp_path, monkeypatch):
    import os
    import time
    monkeypatch.setattr(m, "_TMP_ROOT", tmp_path)
    legacy = tmp_path / "versocon"
    legacy.mkdir()
    (legacy / "firmato.pdf").write_bytes(b"%PDF")
    old = tmp_path / "versocon-old"
    old.mkdir()
    fresh = tmp_path / "versocon-fresh"
    fresh.mkdir()
    t = time.time() - m._STALE_AFTER_S - 60
    os.utime(old, (t, t))
    m._purge_stale_outputs()
    assert not (legacy / "firmato.pdf").exists() and not old.exists() and fresh.exists()


def test_purge_keeps_run_py_logs(tmp_path, monkeypatch):
    # Windows: %TEMP%\\versocon == %LOCALAPPDATA%\\Temp\\VersoCon (run.py) -> non cancellare i log.
    monkeypatch.setattr(m, "_TMP_ROOT", tmp_path)
    legacy = tmp_path / "versocon"
    (legacy / "sub").mkdir(parents=True)
    for n in ("crash.log", "current_url.txt", "vecchio.jpg", ".src.mp4"):
        (legacy / n).write_text("x", encoding="utf-8")
    m._purge_stale_outputs()
    assert sorted(p.name for p in legacy.iterdir()) == ["crash.log", "current_url.txt"]
