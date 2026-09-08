"""Test modulo compress (immagine + PDF) — funzionale, errore, API."""
from __future__ import annotations

import io
import random
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from converters import compress as comp  # noqa: E402
from converters import documents as docconv  # noqa: E402


def _noise_png(size=(420, 300), seed=7) -> bytes:
    rng = random.Random(seed)
    img = Image.new("RGB", size, (0, 0, 0))
    px = img.load()
    for y in range(size[1]):
        for x in range(size[0]):
            px[x, y] = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
    b = io.BytesIO()
    img.save(b, format="PNG")
    return b.getvalue()


def _one_page_pdf() -> bytes:
    return docconv.images_to_pdf([("x.png", _noise_png((200, 140), seed=1))])


@pytest.fixture()
def client():
    return TestClient(app)


# ── compress_image: modalità qualità ──
def test_compress_image_quality_smaller_than_png():
    src = _noise_png()
    out, meta = comp.compress_image(src, out_format="jpeg", quality=70)
    assert len(out) > 0
    assert len(out) < len(src), "jpeg dovrebbe pesare meno del png a rumore"
    assert meta["format"] == "jpeg"
    assert meta["width"] == 420 and meta["height"] == 300


def test_compress_image_max_side_reduces():
    src = _noise_png((800, 600))
    out, meta = comp.compress_image(src, out_format="jpeg", quality=80, max_side=300)
    assert max(meta["width"], meta["height"]) <= 300
    with Image.open(io.BytesIO(out)) as im:
        assert max(im.size) <= 300


def test_compress_image_invalid_format_raises():
    with pytest.raises(ValueError):
        comp.compress_image(_noise_png(), out_format="tiff")


def test_compress_image_empty_raises():
    with pytest.raises(ValueError):
        comp.compress_image(b"", out_format="jpeg")


def test_image_is_compressible():
    assert comp.image_is_compressible("a.heic")
    assert comp.image_is_compressible("a.jpg")
    assert comp.image_is_compressible("A.PNG")
    assert not comp.image_is_compressible("doc.pdf")


# ── compress_image: modalità target ──
def test_compress_image_target_respected():
    src = _noise_png((900, 700), seed=11)
    target = 40 * 1024
    out, meta = comp.compress_image(src, out_format="jpeg", target_bytes=target)
    assert meta["reached_target"] is True
    assert len(out) <= target


def test_compress_image_target_larger_than_source():
    src = _noise_png((120, 120), seed=3)  # piccolo
    target = 10 * 1024 * 1024
    out, meta = comp.compress_image(src, out_format="jpeg", target_bytes=target)
    assert meta["reached_target"] is True
    assert len(out) <= target


# ── compress_pdf ──
def test_compress_pdf_preserves_pages():
    src = docconv.images_to_pdf([
        ("a.png", _noise_png((200, 140), 1)),
        ("b.png", _noise_png((200, 140), 2)),
        ("c.png", _noise_png((200, 140), 3)),
    ])
    for lvl in ("low", "medium", "high"):
        out, meta = comp.compress_pdf(src, level=lvl)
        assert meta["pages"] == 3, lvl
        assert len(out) > 0


def test_compress_pdf_invalid_level_raises():
    with pytest.raises(ValueError):
        comp.compress_pdf(_one_page_pdf(), level="extreme")


def test_compress_pdf_empty_raises():
    with pytest.raises(ValueError):
        comp.compress_pdf(b"")


# ── API: compress-image ──
def test_api_compress_image(client):
    res = client.post(
        "/api/compress-image",
        data={"fmt": "jpeg", "target_bytes": "40960"},
        files=[("file", ("img.png", _noise_png(), "image/png"))],
    )
    assert res.status_code == 200, res.text
    r = res.json()["results"][0]
    assert r["name"].endswith(".jpg")
    assert r["size"] <= 40960
    assert r["src_size"] > 0
    dl = client.get(r["download"])
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("image/jpeg")


def test_api_compress_image_quality_mode(client):
    res = client.post(
        "/api/compress-image",
        data={"fmt": "webp", "quality": "60"},
        files=[("file", ("img.png", _noise_png(), "image/png"))],
    )
    assert res.status_code == 200, res.text
    r = res.json()["results"][0]
    assert r["name"].endswith(".webp")


def test_api_compress_image_wrong_type(client):
    res = client.post(
        "/api/compress-image",
        data={"fmt": "jpeg"},
        files=[("file", ("doc.txt", b"hello", "text/plain"))],
    )
    assert res.status_code == 400


def test_api_compress_image_empty(client):
    res = client.post(
        "/api/compress-image",
        data={"fmt": "jpeg"},
        files=[("file", ("empty.png", b"", "image/png"))],
    )
    assert res.status_code == 400


# ── API: compress-pdf ──
def test_api_compress_pdf(client):
    src = docconv.images_to_pdf([("a.png", _noise_png((200, 140), 5))])
    res = client.post(
        "/api/compress-pdf",
        data={"level": "medium"},
        files=[("file", ("doc.pdf", src, "application/pdf"))],
    )
    assert res.status_code == 200, res.text
    r = res.json()["results"][0]
    assert r["name"].endswith(".pdf")
    assert r["pages"] == 1
    dl = client.get(r["download"])
    assert dl.status_code == 200
    assert dl.headers["content-type"] == "application/pdf"


def test_api_compress_pdf_wrong_type(client):
    res = client.post(
        "/api/compress-pdf",
        data={"level": "medium"},
        files=[("file", ("img.png", _noise_png(), "image/png"))],
    )
    assert res.status_code == 400
