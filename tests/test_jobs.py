"""ARCH-1: job in background — progresso reale e annullamento.

Copre: registry (done/errore/annullo/scadenza), progresso reale per pagina sulla
pulizia scansioni, annullo reale di ffmpeg, contratto HTTP dei job (avvio 202,
polling, risultato con round-trip /api/file, cancel) e latenza di avvio.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402

from app import jobs as jobsmod  # noqa: E402
from app.main import app  # noqa: E402
from converters import report as reportmod  # noqa: E402
from converters import scan as scanconv  # noqa: E402
from converters import video as vidconv  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


def _ff() -> str | None:
    return vidconv._find_ffmpeg()


requires_ffmpeg = pytest.mark.skipif(_ff() is None, reason="ffmpeg non installato")
requires_cv = pytest.mark.skipif(not scanconv.available(), reason="OpenCV non installato")


def _wait(job, timeout: float = 10.0):
    end = time.monotonic() + timeout
    while job.status not in jobsmod.TERMINAL:
        if time.monotonic() > end:
            raise AssertionError(f"job non terminato: {job.status}")
        time.sleep(0.02)
    return job


def _poll(client: TestClient, job_id: str, timeout: float = 15.0) -> dict:
    end = time.monotonic() + timeout
    while True:
        r = client.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200, r.text
        state = r.json()
        if state["status"] in ("done", "error", "cancelled"):
            return state
        if time.monotonic() > end:
            raise AssertionError(f"job non terminato: {state}")
        time.sleep(0.05)


def _make_pdf_pages(n: int = 3) -> bytes:
    doc = pymupdf.open()
    for i in range(n):
        page = doc.new_page(width=200, height=150)
        page.insert_text((30, 60), f"pagina di prova {i + 1}", fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def _png_bytes() -> bytes:
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(buf, format="PNG")
    return buf.getvalue()


def _make_video(d: Path, seconds: int = 2, name: str = "src.mp4") -> Path:
    src = d / name
    cmd = [
        _ff(), "-y", "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=160x120:rate=10",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-loglevel", "error", str(src),
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    if r.returncode != 0 or not src.exists():
        pytest.skip("impossibile creare il video di test")
    return src


# ── unit: registry dei job ──

def test_job_lifecycle_done(tmp_path):
    mgr = jobsmod.JobManager(tmp_path)
    updates = []

    def worker(j):
        j.progress(done=1, total=3, key="job.scan", unit="file")
        updates.append(j.snapshot()["done"])
        return {"results": [{"name": "a"}]}

    job = mgr.create("test", "it", total=3, unit="file")
    mgr.start(job, worker)
    _wait(job)
    assert job.status == "done"
    assert job.result == {"results": [{"name": "a"}]}
    assert job.done == 1 and job.total == 3
    assert updates == [1]
    assert not job.work_dir.exists()          # cartella di lavoro ripulita


def test_job_error_porta_risultati_parziali(tmp_path):
    mgr = jobsmod.JobManager(tmp_path)

    def worker(_j):
        raise jobsmod.JobError("niente da fare", result={"results": [{"name": "x", "error": "no"}]})

    job = mgr.create("test", "it")
    mgr.start(job, worker)
    _wait(job)
    assert job.status == "error"
    assert job.error == "niente da fare"
    assert job.result == {"results": [{"name": "x", "error": "no"}]}


def test_job_errore_inatteso(tmp_path):
    mgr = jobsmod.JobManager(tmp_path)

    def worker(_j):
        raise RuntimeError("boom")

    job = mgr.create("test", "it")
    mgr.start(job, worker)
    _wait(job)
    assert job.status == "error"
    assert "boom" in (job.error or "")


def test_job_cancel_cooperativo(tmp_path):
    mgr = jobsmod.JobManager(tmp_path)

    def worker(j):
        for _ in range(500):
            time.sleep(0.01)
            reportmod.check_cancelled(lambda: j.cancelled)
        return {}

    job = mgr.create("test", "it")
    mgr.start(job, worker)
    time.sleep(0.1)
    assert job.request_cancel() is True
    _wait(job)
    assert job.status == "cancelled"
    assert job.request_cancel() is False      # già terminale


def test_manager_scadenza_e_discard(tmp_path):
    mgr = jobsmod.JobManager(tmp_path, ttl_s=0.05)
    job = mgr.create("test", "it")
    mgr.start(job, lambda _j: {})
    _wait(job)
    time.sleep(0.12)
    assert mgr.get(job.id) is None

    j2 = mgr.create("test", "it")
    work_dir = j2.work_dir
    assert work_dir.exists()
    mgr.discard(j2)
    assert not work_dir.exists() and mgr.get(j2.id) is None


# ── converter: progresso per pagina e annullo (scan) ──

@requires_cv
def test_clean_pdf_progresso_per_pagina():
    seen = []
    scanconv.clean_pdf(_make_pdf_pages(3), progress=lambda d, t, p: seen.append((d, t, p)))
    assert seen[0] == (0, 3, "pages")
    assert seen[-1] == (3, 3, "pages")
    assert seen == [(0, 3, "pages"), (1, 3, "pages"), (2, 3, "pages"), (3, 3, "pages")]


@requires_cv
def test_clean_pdf_annullo_tra_pagine():
    calls = {"n": 0}

    def cancel():
        calls["n"] += 1
        return calls["n"] >= 2

    with pytest.raises(reportmod.OperationCancelled):
        scanconv.clean_pdf(_make_pdf_pages(3), cancel=cancel)


# ── converter: progresso reale e annullo di ffmpeg ──

@requires_ffmpeg
def test_transcode_progresso_reale(tmp_path):
    src = _make_video(tmp_path, seconds=2)
    seen = []
    size = vidconv.transcode(
        str(src), str(tmp_path / "out.mp4"),
        progress=lambda d, t, p: seen.append((d, t, p)),
    )
    assert size > 0
    assert seen[0][0] == 0 and seen[0][2] == "seconds"
    total = seen[0][1]
    assert total and seen[-1] == (total, total, "seconds")


@requires_ffmpeg
def test_transcode_annullo_termina_ffmpeg_e_pulisce(tmp_path):
    src = _make_video(tmp_path, seconds=3, name="lungo.mp4")
    dst = tmp_path / "out.webm"
    with pytest.raises(reportmod.OperationCancelled):
        vidconv.transcode(str(src), str(dst), fmt="webm", cancel=lambda: True)
    assert not dst.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [src.name]  # nessun temp residuo


def test_video_core_annullo_non_diventa_errore(monkeypatch, tmp_path):
    """Regressione: l'annullo di un job video deve restare cancelled, non errore 500."""
    from app import main as m

    def cancelled(*_a, **_kw):
        raise reportmod.OperationCancelled()

    monkeypatch.setattr(m.vidconv, "transcode", cancelled)
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"x")
    with pytest.raises(reportmod.OperationCancelled):
        m._video_convert_run("it", src, "clip.mp4", "mp4", None, cancel=lambda: True)


# ── contratto HTTP dei job ──

@requires_cv
def test_api_job_scan_roundtrip(client):
    r = client.post(
        "/api/jobs/scan-clean",
        files={"files": ("prova.png", _png_bytes(), "image/png")},
        data={"deskew": "false", "fmt": "png"},
    )
    assert r.status_code == 202, r.text
    state = _poll(client, r.json()["id"])
    assert state["status"] == "done", state
    assert state["unit"] == "file" and state["total"] == 1 and state["done"] == 1
    assert state["message"]
    entry = state["result"]["results"][0]
    assert entry["name"] == "prova_clean.png"
    assert entry["download"] == "/api/file/prova_clean.png"
    dl = client.get(entry["download"])
    assert dl.status_code == 200 and dl.content[:8] == b"\x89PNG\r\n\x1a\n"


@requires_cv
def test_api_job_start_immediato_e_cancel(client, monkeypatch):
    def slow_clean(data, **kw):
        for _ in range(500):
            time.sleep(0.02)
            reportmod.check_cancelled(kw.get("cancel"))
        return data

    monkeypatch.setattr("app.main.scanconv.clean_pdf", slow_clean)
    started = time.monotonic()
    r = client.post(
        "/api/jobs/scan-clean",
        files={"files": ("lento.pdf", _make_pdf_pages(1), "application/pdf")},
        data={"deskew": "false", "dpi": "72"},
    )
    elapsed = time.monotonic() - started
    assert r.status_code == 202, r.text
    assert elapsed < 1.0, f"l'avvio ha bloccato per {elapsed:.2f}s"
    job_id = r.json()["id"]
    time.sleep(0.15)
    mid = client.get(f"/api/jobs/{job_id}").json()
    assert mid["status"] in ("queued", "running"), mid

    c = client.post(f"/api/jobs/{job_id}/cancel")
    assert c.status_code == 200
    state = _poll(client, job_id)
    assert state["status"] == "cancelled"


@requires_cv
def test_api_job_scan_tutti_falliti_riporta_risultati(client):
    r = client.post(
        "/api/jobs/scan-clean",
        files={"files": ("nota.txt", b"ciao", "text/plain")},
    )
    assert r.status_code == 202, r.text
    state = _poll(client, r.json()["id"])
    assert state["status"] == "error", state
    assert state["error"]
    assert state["result"]["results"][0]["error"]


def test_api_job_sconosciuto(client):
    r = client.get("/api/jobs/inesistente")
    assert r.status_code == 404 and "trovata" in r.json()["detail"]
    assert client.post("/api/jobs/inesistente/cancel").status_code == 404


def test_api_job_video_rifiuta_input_non_video(client):
    for url in ("/api/jobs/video-convert", "/api/jobs/video-audio", "/api/jobs/video-gif"):
        r = client.post(url, files={"file": ("nota.txt", b"x", "text/plain")})
        assert r.status_code == 400, (url, r.text)


@requires_ffmpeg
def test_api_job_video_gif_roundtrip(client, tmp_path):
    """Contratto dell'endpoint usato dalla UI: avvio, polling, GIF con intervallo start/end."""
    src = _make_video(tmp_path, seconds=1)
    with src.open("rb") as fh:
        r = client.post(
            "/api/jobs/video-gif",
            files={"file": ("clip.mp4", fh, "video/mp4")},
            data={"fps": "10", "width": "96", "start": "0.2", "end": "0.6"},
        )
    assert r.status_code == 202, r.text
    state = _poll(client, r.json()["id"])
    assert state["status"] == "done", state
    entry = state["result"]["results"][0]
    assert entry["name"] == "clip.gif"
    dl = client.get(entry["download"])
    assert dl.status_code == 200 and dl.content[:6] in (b"GIF87a", b"GIF89a")
    import io

    from PIL import Image
    with Image.open(io.BytesIO(dl.content)) as im:
        assert im.is_animated and 3 <= im.n_frames <= 5, im.n_frames
