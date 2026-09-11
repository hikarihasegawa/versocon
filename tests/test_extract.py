"""Test estrazione testo PDF (nativo) + OCR (Tesseract, opzionale)."""
from __future__ import annotations

import io
import os
import shutil
import sys
from pathlib import Path

import pytest
import pymupdf
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Assicura che pytesseract trovi il binary anche se non è nel PATH della shell.
_tess = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if _tess and os.path.isfile(_tess) and not os.environ.get("TESSERACT_CMD"):
    os.environ["TESSERACT_CMD"] = _tess

from converters import documents as docconv  # noqa: E402
from converters import extract as ex  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402

CLIENT = TestClient(app)
ENABLED = ex.ocr_enabled()


def _png(color=(200, 30, 30), size=(120, 80)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, format="PNG")
    return b.getvalue()


def _text_pdf(text: str = "Ciao mondo VersoCon", n: int = 1) -> bytes:
    doc = pymupdf.Document()
    for _ in range(n):
        p = doc.new_page()
        p.insert_text((72, 100), text, fontsize=20)
    out = doc.tobytes()
    doc.close()
    return out


def _scanned_pdf(n: int = 1) -> bytes:
    imgs = [("p.png", _png((i * 40 % 200 + 20, 30, 30))) for i in range(n)]
    return docconv.images_to_pdf(imgs)


# ---------- modulo: nativo ----------
def test_page_texts_native():
    texts = ex.page_texts(_text_pdf())
    assert len(texts) == 1
    assert "Ciao" in texts[0]


def test_page_texts_multi():
    texts = ex.page_texts(_text_pdf(n=3))
    assert len(texts) == 3


def test_page_texts_empty_raises():
    with pytest.raises(ValueError):
        ex.page_texts(b"")


def test_page_texts_invalid_raises():
    with pytest.raises(ValueError):
        ex.page_texts(b"non e un pdf")


def test_page_image_png_is_png():
    data = ex.page_image_png(_text_pdf(), 0, dpi=100)
    assert data[:4] == b"\x89PNG"


def test_page_image_png_out_of_range():
    with pytest.raises(ValueError):
        ex.page_image_png(_text_pdf(), 99)


# ---------- modulo: OCR ----------
def test_ocr_enabled_is_bool():
    assert isinstance(ex.ocr_enabled(), bool)


def test_ocr_info_shape():
    info = ex.ocr_info()
    assert set(info) >= {"available", "version", "languages"}
    if info["available"]:
        assert info["languages"]
    else:
        assert info["languages"] == []
        assert info["version"] is None


@pytest.mark.skipif(ENABLED, reason="Tesseract è installato: percorso 'mancante' non testabile")
def test_ocr_missing_raises():
    with pytest.raises(ex.OcrEngineMissingError):
        ex.ocr_image_bytes(_png(), lang="ita")


def test_extract_off_native():
    out = ex.extract_text(_text_pdf(), mode="off")
    assert "Ciao" in out[0]


def test_extract_off_scanned_gives_blank():
    out = ex.extract_text(_scanned_pdf(), mode="off")
    assert out == [""] or all(not t.strip() for t in out)


def test_extract_auto_native_uses_native():
    out = ex.extract_text(_text_pdf(), mode="auto")
    assert "Ciao" in out[0]


@pytest.mark.skipif(ENABLED, reason="Tesseract installato: auto su pagina senza testo non deve raise")
def test_extract_auto_scanned_without_engine_raises():
    with pytest.raises(ex.OcrEngineMissingError):
        ex.extract_text(_scanned_pdf(), mode="auto")


@pytest.mark.skipif(ENABLED, reason="Tesseract installato: on senza motore non testabile")
def test_extract_on_without_engine_raises():
    with pytest.raises(ex.OcrEngineMissingError):
        ex.extract_text(_text_pdf(), mode="on")


def test_extract_invalid_mode():
    with pytest.raises(ValueError):
        ex.extract_text(_text_pdf(), mode="laser")


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_ocr_real_scanned_page():
    """E2E: pagina 'scanned' (solo immagine) → OCR legge il testo."""
    from PIL import Image, ImageDraw
    im = Image.new("L", (400, 120), 255)
    d = ImageDraw.Draw(im)
    d.text((20, 40), "Ciao 123", fill=0)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    pdf_bytes = docconv.images_to_pdf([("page.png", buf.getvalue())], 1280)
    pages = ex.extract_text(pdf_bytes, mode="on", lang="eng")
    assert isinstance(pages, list)
    assert "Ciao" in pages[0] or "123" in pages[0]


def test_extract_empty():
    with pytest.raises(ValueError):
        ex.extract_text(b"", mode="off")


@pytest.fixture()
def client():
    return TestClient(app)


# ---------- API ----------
def test_api_pdf_to_text_off(client):
    res = client.post(
        "/api/pdf-to-text",
        data={"ocr": "off", "lang": "ita"},
        files=[("file", ("a.pdf", _text_pdf(), "application/pdf"))],
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["results"][0]["name"].endswith(".txt")
    assert "Ciao" in data["text"]
    assert len(data["pages"]) == 1


def test_api_pdf_to_text_rejects_non_pdf(client):
    res = client.post(
        "/api/pdf-to-text",
        data={"ocr": "off"},
        files=[("file", ("a.png", _png(), "image/png"))],
    )
    assert res.status_code == 400


def test_api_pdf_to_text_invalid_mode(client):
    res = client.post(
        "/api/pdf-to-text",
        data={"ocr": "bogus"},
        files=[("file", ("a.pdf", _text_pdf(), "application/pdf"))],
    )
    assert res.status_code == 400


def test_api_config_has_ocr(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    assert "ocr" in res.json()


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_api_forced_ocr_on_native_pdf_warns(client):
    """OCR forzato su un PDF che ha già testo: l'utente viene indirizzato ad «Automatico»."""
    res = client.post(
        "/api/pdf-to-text",
        data={"ocr": "on", "lang": "eng"},
        files=[("file", ("a.pdf", _text_pdf(n=2), "application/pdf"))],
    )
    assert res.status_code == 200, res.text
    assert "2" in res.json().get("warning", "")


def test_api_auto_on_native_pdf_has_no_warning(client):
    res = client.post(
        "/api/pdf-to-text",
        data={"ocr": "auto", "lang": "ita"},
        files=[("file", ("a.pdf", _text_pdf(), "application/pdf"))],
    )
    assert res.status_code == 200, res.text
    if ENABLED:
        assert "warning" not in res.json()


# ---------- testo nativo: righe spezzate (PDF con testo giustificato) ----------
_WORDS = "Questo documento descrive la metrica adottata per misurare".split()


def _split_words_pdf() -> bytes:
    """Parole scritte una a una sulla stessa linea con spazi larghi, come nel testo
    giustificato: get_text("text") le restituisce su righe separate."""
    doc = pymupdf.Document()
    page = doc.new_page()
    x = 72.0
    for w in _WORDS:
        page.insert_text((x, 100), w + " ", fontsize=11)
        x += pymupdf.get_text_length(w + " ", fontsize=11) * 1.4
    page.insert_text((72, 130), "Seconda riga normale.", fontsize=11)
    out = doc.tobytes()
    doc.close()
    return out


def test_native_split_words_are_rejoined():
    data = _split_words_pdf()
    raw = pymupdf.Document(stream=data, filetype="pdf")[0].get_text("text")
    assert raw.splitlines()[0].strip() == "Questo"  # il PDF riproduce il difetto
    lines = [ln.strip() for ln in ex.page_texts(data)[0].splitlines()]
    assert lines == [" ".join(_WORDS), "Seconda riga normale."]


def test_extract_auto_rejoins_split_words():
    assert " ".join(_WORDS) in ex.extract_text(_split_words_pdf(), mode="auto")[0]


def test_native_text_keeps_every_character():
    for data in (_split_words_pdf(), _text_pdf(n=2)):
        doc = pymupdf.Document(stream=data, filetype="pdf")
        expected = ["".join(p.get_text("text").split()) for p in doc]
        assert ["".join(t.split()) for t in ex.page_texts(data)] == expected


def test_native_text_unchanged_without_split_lines():
    data = _text_pdf(n=2)
    doc = pymupdf.Document(stream=data, filetype="pdf")
    assert ex.page_texts(data) == [p.get_text("text") for p in doc]
