"""Test FEAT-D: pulizia scansioni (deskew, antishadow, bianco/nero, ritaglio prospettico).

Copre il livello converter (`scan.estimate_skew/deskew/remove_shadow/binarize/
crop_perspective/clean_bytes/clean_pdf`) e il contratto HTTP `POST /api/scan-clean`
con round-trip reale dei file prodotti via `/api/file/<name>`.
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover - ambiente senza OpenCV
    cv2 = None
    np = None

import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402
from converters import scan  # noqa: E402

ENABLED = scan.available()
pytestmark = pytest.mark.skipif(not ENABLED, reason="OpenCV non installato")


def _text_image(w: int = 800, h: int = 600):
    """Pagina sintetica: barre scure orizzontali su fondo bianco."""
    img = np.full((h, w, 3), 255, np.uint8)
    for i in range(10):
        cv2.rectangle(img, (80, 60 + i * 40), (w - 100, 60 + i * 40 + 14), (25, 25, 25), -1)
    return img


def _rotate(img, deg: float):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), deg, 1.0)
    return cv2.warpAffine(
        img, m, (w, h), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255),
    )


def _png(img) -> bytes:
    return cv2.imencode(".png", img)[1].tobytes()


def _png_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as im:
        return im.size


def _scan_pdf(n_pages: int = 2) -> bytes:
    """PDF tipo scansione: ogni pagina è una sola immagine, zero testo nativo."""
    src = pymupdf.open()
    for i in range(n_pages):
        page = src.new_page(width=300, height=200)
        page.insert_text((20, 100), f"PAGINA-{i + 1}", fontsize=18)
    imgs = [src[i].get_pixmap(dpi=120).tobytes("png") for i in range(n_pages)]
    src.close()
    out = pymupdf.open()
    for png in imgs:
        page = out.new_page(width=300, height=200)
        page.insert_image(page.rect, stream=png)
    data = out.tobytes()
    out.close()
    return data


@pytest.fixture()
def client():
    return TestClient(app)


def _post_scan(client, files, **fields):
    data = {k: str(v) for k, v in fields.items()}
    return client.post("/api/scan-clean", data=data, files=files)


def test_motore_disponibile():
    assert scan.available() is True
    assert scan.engine_info()["version"] == cv2.__version__


@pytest.mark.parametrize("deg", [-12.0, -7.0, 3.0, 7.0])
def test_raddrizza_riduce_inclinazione(deg):
    rot = _rotate(_text_image(), deg)
    assert scan.estimate_skew(rot) == pytest.approx(-deg, abs=1.0)
    fixed = scan.clean_bytes(_png(rot), deskew=True)
    assert abs(scan.estimate_skew(scan.decode_image(fixed))) <= 0.75
    kept = scan.clean_bytes(_png(rot), deskew=False)
    assert scan.estimate_skew(scan.decode_image(kept)) == pytest.approx(-deg, abs=1.0)


def test_pagina_bianca_nessuna_rotazione():
    blank = np.full((300, 400, 3), 255, np.uint8)
    assert scan.estimate_skew(blank) == 0.0
    out, ang = scan.deskew(blank)
    assert ang == 0.0


def test_antishadow_normalizza_illuminazione():
    grad = np.tile(np.linspace(70, 255, 800, dtype=np.uint8), (600, 1))
    img = cv2.cvtColor(grad, cv2.COLOR_GRAY2BGR)
    for i in range(10):
        cv2.rectangle(img, (80, 60 + i * 40), (720, 60 + i * 40 + 14), (20, 20, 20), -1)
    flat = scan.remove_shadow(img)
    before = img[500:560, :, 0].mean(axis=0).std()
    after = flat[500:560, :, 0].mean(axis=0).std()
    assert before > 20
    assert after < before * 0.2


def test_binarize_produce_solo_bianco_e_nero():
    out = scan.clean_bytes(_png(_rotate(_text_image(), 5)), deskew=True, binarize=True)
    arr = scan.decode_image(out)
    assert set(np.unique(arr).tolist()) <= {0, 255}


def test_ritaglio_prospettico_mappa_i_quattro_angoli():
    canvas = np.full((600, 800, 3), 255, np.uint8)
    quad = [(160, 120), (700, 90), (760, 500), (120, 520)]
    colors = [(0, 0, 255), (0, 200, 0), (255, 0, 0), (0, 165, 255)]  # BGR
    for (x, y), c in zip(quad, colors):
        cv2.circle(canvas, (x, y), 18, c, -1)
    corners = [[20.0, 20.0], [87.5, 15.0], [95.0, 83.33], [15.0, 86.67]]
    out = scan.crop_perspective(canvas, corners)
    assert out.shape[1] == pytest.approx(640, abs=3)
    assert out.shape[0] == pytest.approx(413, abs=3)
    h, w = out.shape[:2]
    spots = [(4, 4), (w - 4, 4), (w - 4, h - 4), (4, h - 4)]
    for (px, py), c in zip(spots, colors):
        patch = out[max(0, py - 4):py + 4, max(0, px - 4):px + 4].reshape(-1, 3).mean(axis=0)
        assert patch[0] == pytest.approx(c[0], abs=40)
        assert patch[1] == pytest.approx(c[1], abs=40)
        assert patch[2] == pytest.approx(c[2], abs=40)


def test_parse_corners_vuoto_e_non_valido():
    assert scan.parse_corners(None) is None
    assert scan.parse_corners("") is None
    for bad in ([], [[1, 2]], [[1, 2], [3, 4], [5, 6], [7, 200]], [[1, 2], [3, 4], [5, 6], ["a", "b"]]):
        with pytest.raises(ValueError):
            scan.parse_corners(bad)


def test_exif_orientation_rispettata():
    img = _text_image(400, 300)
    cv2.rectangle(img, (20, 20), (60, 60), (0, 0, 255), -1)  # marcatore rosso in alto a sinistra
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[274] = 6  # orientamento 6 = ruota 90° in senso orario
    Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(buf, format="JPEG", exif=exif.tobytes())
    out = scan.clean_bytes(buf.getvalue(), deskew=False)
    w, h = _png_size(out)
    assert (w, h) == (300, 400)
    arr = scan.decode_image(out)
    patch = arr[25:55, w - 55:w - 25].reshape(-1, 3).mean(axis=0)
    assert patch[2] > 150 and patch[2] > patch[0] + 80


def test_contratto_immagine_unicode_roundtrip(client):
    src = _png(_rotate(_text_image(), 6))
    r = _post_scan(
        client, [("files", ("scansione café 動画.png", src, "image/png"))],
        deskew="true", binarize="true",
    )
    assert r.status_code == 200, r.text
    entry = r.json()["results"][0]
    assert entry["name"] == "scansione café 動画_clean.png"
    assert entry["src"] == "scansione café 動画.png"
    got = client.get(entry["download"])
    assert got.status_code == 200
    assert got.content == Path(entry["path"]).read_bytes()
    assert set(np.unique(scan.decode_image(got.content)).tolist()) <= {0, 255}


def test_contratto_pdf_scansionato(client):
    r = _post_scan(client, [("files", ("contratto 日本.pdf", _scan_pdf(2), "application/pdf"))], deskew="true")
    assert r.status_code == 200, r.text
    entry = r.json()["results"][0]
    assert entry["name"] == "contratto 日本_clean.pdf"
    got = client.get(entry["download"]).content
    doc = pymupdf.open(stream=got, filetype="pdf")
    assert doc.page_count == 2
    assert len(doc[0].get_images()) >= 1
    assert doc[0].rect.width == pytest.approx(300, abs=1)
    assert doc[0].get_text().strip() == ""
    doc.close()


def test_contratto_due_file(client):
    r = _post_scan(
        client,
        [("files", ("a.png", _png(_text_image()), "image/png")),
         ("files", ("b.png", _png(_text_image(400, 500)), "image/png"))],
        deskew="false",
    )
    assert r.status_code == 200, r.text
    assert [x["name"] for x in r.json()["results"]] == ["a_clean.png", "b_clean.png"]


def test_corners_non_validi_400(client):
    r = _post_scan(client, [("files", ("a.png", _png(_text_image()), "image/png"))], corners="[[1,2],[3,4]]")
    assert r.status_code == 400
    assert "scan_corners_invalid" not in r.text


def test_estensione_rifiutata(client):
    r = _post_scan(client, [("files", ("note.txt", b"ciao", "text/plain"))])
    assert r.status_code == 422
    assert r.json()["detail"]["results"][0]["error"]


def test_motore_assente_501(client, monkeypatch):
    monkeypatch.setattr(scan, "_CV_AVAILABLE", False)
    r = _post_scan(client, [("files", ("a.png", _png(_text_image()), "image/png"))])
    assert r.status_code == 501
    assert "scan_engine_missing" not in r.text


def test_pulizia_completa_entro_soglia_tempo():
    img = np.full((1200, 1600, 3), 255, np.uint8)
    for i in range(30):
        cv2.rectangle(img, (100, 60 + i * 36), (1500, 60 + i * 36 + 14), (30, 30, 30), -1)
    rot = _rotate(img, 6)
    t0 = time.perf_counter()
    scan.clean_bytes(_png(rot), deskew=True, antishadow=True, binarize=True, fmt="jpg", quality=80)
    assert time.perf_counter() - t0 < 10.0


# ---------------- FEAT-D UI: controlli statici + motore in /api/config ----------------

STATIC = ROOT / "static"
I18N = STATIC / "i18n"
SCAN_UI_KEYS = [
    "pdf.sub.scan", "btn.scan_pick", "scan.hint", "scan.deskew",
    "scan.antishadow", "scan.binarize", "scan.fmt", "scan.crop_hint",
    "scan.clear_pts", "scan.result", "scan.preview_empty",
    "scan.preview_none", "scan.no_engine", "btn.scan", "btn.scanning",
    "dyn.scan_pick_first", "dyn.scan_done",
]


def test_config_espone_motore_scan(client):
    body = client.get("/api/config").json()
    assert body["scan"]["available"] is True
    assert body["scan"]["version"] == cv2.__version__


def test_config_motore_scan_assente(client, monkeypatch):
    monkeypatch.setattr(scan, "_CV_AVAILABLE", False)
    body = client.get("/api/config").json()
    assert body["scan"] == {"available": False, "version": None}


def test_subtab_scan_e_controlli():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'data-sub="scan"' in html
    assert 'id="subscan"' in html
    for el in ['id="scanIn"', 'id="scanDeskew"', 'id="scanShadow"',
               'id="scanBinarize"', 'id="scanFmt"', 'id="scanQ"', 'id="scanDpi"',
               'id="btnScan"', 'id="btnScanClearPts"', 'id="scanStatus"',
               'id="scanPage"', 'id="scanCanvas"', 'id="scanImg"', 'id="scanPoly"',
               'id="scanPt1"', 'id="scanPt4"', 'id="scanOut"', 'id="scanOutImg"']:
        assert el in html, f"{el} mancante"
    assert 'type="file" id="scanIn" multiple' in html


def test_js_invia_scansione_con_angoli_e_anteprima_risultato():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '"/api/jobs/scan-clean"' in js
    for field in ["deskew", "antishadow", "binarize", "fmt", "quality", "dpi", "corners"]:
        assert f'fd.append("{field}"' in js, f"FormData: {field} mancante"
    assert "JSON.stringify(scanCorners)" in js
    assert "scanCorners.length >= 4" in js          # quinto clic ricomincia
    assert "function scanDrawCorners" in js
    assert "function renderPdfFirstPage" in js
    assert "scanShowResult" in js and "scanOutImg" in js
    assert '#tabPdf .subtab.active[data-sub="scan"]' in js  # shell wide in Scansione
    assert 'IC.t("scan.no_engine")' in js                    # avviso motore assente


def test_scan_keys_translated_all_languages():
    js = (STATIC / "i18n.js").read_text(encoding="utf-8")
    langs = re.findall(r'"([a-z]{2})"', re.search(r"SUPPORTED\s*=\s*\[([^\]]+)\]", js).group(1))
    for lang in langs:
        data = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))
        missing = [k for k in SCAN_UI_KEYS if not data.get(k)]
        assert missing == [], f"{lang}.json: mancano {missing}"
        assert "{n}" in data["dyn.scan_done"]


def test_css_angoli_scan_presente():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    for rule in [".scan-pt", ".scan-poly", ".scan-out-card", "scan-has-preview"]:
        assert rule in css, f"{rule} mancante"
