"""FEAT-C: privacy immagini — rimozione EXIF/GPS nella conversione.

Copre: rimozione reale del GPS IFD e degli altri tag EXIF, regressione sul
comportamento di default (EXIF preservata), orientamento applicato comunque,
formati jpeg/webp/png, contratto HTTP con round-trip /api/file e nomi unicode.
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from converters import images as imgconv  # noqa: E402
from PIL import Image  # noqa: E402

GPS_IFD = 0x8825
ORIENTATION = 0x0112
ARTIST = 0x013B


def _exif_with_gps(orientation: int | None = None) -> bytes:
    e = Image.Exif()
    e[ARTIST] = "VersoCon"
    if orientation is not None:
        e[ORIENTATION] = orientation
    gps = e.get_ifd(GPS_IFD)
    gps[1] = "N"
    gps[2] = (45.0, 0.0, 0.0)
    return e.tobytes()


def _jpeg_with_gps(size=(60, 40), orientation: int | None = None) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(
        buf, format="JPEG", exif=_exif_with_gps(orientation)
    )
    return buf.getvalue()


@pytest.fixture()
def client():
    return TestClient(app)


# ── unit ──

def test_sorgente_test_contiene_gps_sanity():
    ex = Image.open(io.BytesIO(_jpeg_with_gps())).getexif()
    assert ex.get(ARTIST) == "VersoCon"
    assert ex.get_ifd(GPS_IFD), "la sorgente di test deve contenere il GPS IFD"


def test_strip_exif_rimuove_gps_e_tag():
    out = imgconv.convert_bytes(_jpeg_with_gps(), "jpeg", strip_exif=True)
    ex = Image.open(io.BytesIO(out)).getexif()
    assert ex.get_ifd(GPS_IFD) == {}
    assert dict(ex) == {}


def test_default_preserva_exif_regressione():
    out = imgconv.convert_bytes(_jpeg_with_gps(), "jpeg")
    ex = Image.open(io.BytesIO(out)).getexif()
    assert ex.get(ARTIST) == "VersoCon"
    assert ex.get_ifd(GPS_IFD)


def test_strip_exif_webp():
    out = imgconv.convert_bytes(_jpeg_with_gps(), "webp", strip_exif=True)
    im = Image.open(io.BytesIO(out))
    assert im.format == "WEBP"
    assert im.getexif().get_ifd(GPS_IFD) == {}


def test_strip_exif_png_senza_chunk_exif():
    out = imgconv.convert_bytes(_jpeg_with_gps(), "png", strip_exif=True)
    im = Image.open(io.BytesIO(out))
    assert im.format == "PNG"
    assert not im.info.get("exif")
    assert im.getexif().get_ifd(GPS_IFD) == {}


def test_strip_exif_applica_orientation():
    src = _jpeg_with_gps(size=(60, 40), orientation=6)
    out = imgconv.convert_bytes(src, "jpeg", strip_exif=True)
    im = Image.open(io.BytesIO(out))
    assert im.size == (40, 60)
    assert im.getexif().get_ifd(GPS_IFD) == {}
    assert im.getexif().get(ORIENTATION) in (None, 1)


def test_strip_exif_prestazioni():
    src = _jpeg_with_gps(size=(1600, 1200))
    t0 = time.perf_counter()
    out = imgconv.convert_bytes(src, "jpeg", strip_exif=True)
    dt = time.perf_counter() - t0
    assert out
    assert dt < 3.0, f"conversione troppo lenta: {dt:.2f}s"


# ── contratto HTTP ──

def _convert_via_api(client: TestClient, name: str, strip: bool) -> bytes:
    data = {"fmt": "jpeg"}
    if strip:
        data["strip_exif"] = "1"
    res = client.post(
        "/api/convert",
        data=data,
        files=[("files", (name, _jpeg_with_gps(), "image/jpeg"))],
    )
    assert res.status_code == 200, res.text
    r = res.json()["results"][0]
    assert "error" not in r, r
    dl = client.get(r["download"])
    assert dl.status_code == 200
    return dl.content


def test_contract_strip_exif_round_trip(client):
    out = _convert_via_api(client, "gps.jpg", strip=True)
    assert Image.open(io.BytesIO(out)).getexif().get_ifd(GPS_IFD) == {}


def test_contract_default_preserva_gps(client):
    out = _convert_via_api(client, "gps.jpg", strip=False)
    assert Image.open(io.BytesIO(out)).getexif().get_ifd(GPS_IFD)


def test_contract_strip_exif_nome_unicode(client):
    out = _convert_via_api(client, "foto è città.jpg", strip=True)
    assert Image.open(io.BytesIO(out)).getexif().get_ifd(GPS_IFD) == {}


# ── UI statica ──

def test_ui_toggle_exif_presente_e_collegato():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="stripExif"' in html
    assert 'data-i18n="ctl.strip_exif"' in html
    assert 'fd.append("strip_exif", "1")' in js
