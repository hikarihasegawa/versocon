"""Test FEAT-B: sicurezza PDF (password) e OCR (immagini, PDF ricercabile).

Copre il livello converter (`pdfedit.protect/unprotect`, `extract.searchable_pdf`,
`extract.ocr_image_file`, `extract.image_to_searchable_pdf`) e il contratto HTTP
(`POST /api/pdf-edit` azioni protect/unprotect/searchable, `POST /api/image-ocr`)
con round-trip reale dei file prodotti via `/api/file/<name>`.
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402

from app.main import app  # noqa: E402
from converters import extract as ex  # noqa: E402
from converters import pdfedit  # noqa: E402

ENABLED = ex.ocr_enabled()
WORDS = "RICERCABILE VersoCon 123"


def _make_pdf(n_pages: int = 2, text: str = "Ciao mondo") -> bytes:
    doc = pymupdf.Document()
    for i in range(n_pages):
        page = doc.new_page(width=300, height=200)
        page.insert_text((20, 100), f"PAGINA-{i + 1} {text}", fontsize=18)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _scan_png(text: str = WORDS) -> bytes:
    """PNG di una pagina di testo (simula una scansione, nessun testo nativo)."""
    doc = pymupdf.Document()
    page = doc.new_page(width=300, height=200)
    page.insert_text((30, 100), text, fontsize=20)
    png = doc[0].get_pixmap(dpi=150).tobytes("png")
    doc.close()
    return png


def _scan_pdf(text: str = WORDS) -> bytes:
    """PDF con una sola immagine (scansione), zero testo estraibile."""
    out = pymupdf.Document()
    page = out.new_page(width=300, height=200)
    page.insert_image(page.rect, stream=_scan_png(text))
    buf = io.BytesIO()
    out.save(buf)
    out.close()
    return buf.getvalue()


def _load(b: bytes) -> pymupdf.Document:
    return pymupdf.Document(stream=b, filetype="pdf")


@pytest.fixture()
def client():
    return TestClient(app)


def _post_edit(client, pdf: bytes, **fields):
    name = fields.pop("name", "doc.pdf")
    data = {k: str(v) for k, v in fields.items()}
    return client.post("/api/pdf-edit", data=data,
                       files=[("file", (name, pdf, "application/pdf"))])


def _download(client, body) -> bytes:
    return client.get(body["results"][0]["download"]).content


# --------------------------------------------------------------------------
# Converter: protezione / rimozione password
# --------------------------------------------------------------------------
def test_protect_requires_password():
    with pytest.raises(pdfedit.PasswordError):
        pdfedit.protect(_make_pdf(1), "")


def test_protect_roundtrip_password():
    out = pdfedit.protect(_make_pdf(1), "pw123")
    doc = _load(out)
    assert doc.needs_pass
    assert doc.authenticate("sbagliata") == 0
    assert doc.authenticate("pw123") > 0
    assert "Ciao mondo" in doc[0].get_text()


def test_protect_permissions_restrict_copy_and_modify():
    out = pdfedit.protect(_make_pdf(1), "pw123", allow_copy=False, allow_modify=False)
    doc = _load(out)
    assert doc.authenticate("pw123") > 0
    p = doc.permissions
    assert p & pymupdf.PDF_PERM_PRINT
    assert not (p & pymupdf.PDF_PERM_COPY)
    assert not (p & pymupdf.PDF_PERM_MODIFY)
    assert not (p & pymupdf.PDF_PERM_ANNOTATE)


def test_protect_allow_modify_and_no_print():
    out = pdfedit.protect(_make_pdf(1), "pw123", allow_print=False, allow_modify=True)
    doc = _load(out)
    assert doc.authenticate("pw123") > 0
    p = doc.permissions
    assert not (p & pymupdf.PDF_PERM_PRINT)
    assert p & pymupdf.PDF_PERM_MODIFY


def test_unprotect_removes_password():
    plain = pdfedit.unprotect(pdfedit.protect(_make_pdf(1), "pw123"), "pw123")
    doc = _load(plain)
    assert not doc.needs_pass
    assert "Ciao mondo" in doc[0].get_text()


def test_unprotect_plain_is_noop():
    src = _make_pdf(1)
    assert pdfedit.unprotect(src) == src


def test_unprotect_wrong_password():
    with pytest.raises(pdfedit.PasswordError):
        pdfedit.unprotect(pdfedit.protect(_make_pdf(1), "pw123"), "nope")


def test_unprotect_non_pdf():
    with pytest.raises(ValueError):
        pdfedit.unprotect(b"non un pdf")


def test_is_protected():
    assert pdfedit.is_protected(pdfedit.protect(_make_pdf(1), "pw123")) is True
    assert pdfedit.is_protected(_make_pdf(1)) is False


# --------------------------------------------------------------------------
# Converter: OCR immagini e PDF ricercabile
# --------------------------------------------------------------------------
@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_ocr_image_file_effect():
    txt = ex.ocr_image_file(_scan_png(), lang="ita")
    assert "RICERCABILE" in txt.upper()


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_ocr_image_file_bad_language():
    with pytest.raises(ValueError, match="Lingua OCR"):
        ex.ocr_image_file(_scan_png(), lang="zzz")


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_image_to_searchable_pdf_effect():
    out = ex.image_to_searchable_pdf(_scan_png(), lang="ita")
    doc = _load(out)
    assert doc.page_count == 1
    assert "RICERCABILE" in doc[0].get_text().upper()
    pix = doc[0].get_pixmap(dpi=72)
    assert pix.samples != b"\xff" * len(pix.samples)  # l'immagine c'è


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_searchable_pdf_adds_invisible_text():
    scan = _scan_pdf()
    before = _load(scan)
    assert not before[0].get_text().strip()
    pix_before = before[0].get_pixmap(dpi=72).tobytes("png")
    before.close()

    t0 = time.monotonic()
    out = ex.searchable_pdf(scan, lang="ita")
    elapsed = time.monotonic() - t0

    doc = _load(out)
    assert doc.page_count == 1
    assert "RICERCABILE" in doc[0].get_text().upper()
    assert doc[0].get_pixmap(dpi=72).tobytes("png") == pix_before
    assert elapsed < 30, f"OCR di 1 pagina troppo lento: {elapsed:.1f}s"


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_searchable_pdf_skips_native_pages(monkeypatch):
    calls: list[int] = []
    real = ex._page_ocr_layer

    def spy(page, pyt, lang, dpi):
        calls.append(page.number)
        return real(page, pyt, lang, dpi)

    monkeypatch.setattr(ex, "_page_ocr_layer", spy)
    out = ex.searchable_pdf(_make_pdf(2), lang="ita")
    assert calls == []
    assert "PAGINA-1" in _load(out)[0].get_text()


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_searchable_pdf_explicit_pages_and_range(monkeypatch):
    calls: list[int] = []
    real = ex._page_ocr_layer

    def spy(page, pyt, lang, dpi):
        calls.append(page.number)
        return real(page, pyt, lang, dpi)

    monkeypatch.setattr(ex, "_page_ocr_layer", spy)
    ex.searchable_pdf(_make_pdf(2), lang="ita", pages=[2])
    assert calls == [1]
    with pytest.raises(ValueError, match="fuori range"):
        ex.searchable_pdf(_make_pdf(2), lang="ita", pages=[3])


def test_searchable_pdf_without_engine(monkeypatch):
    monkeypatch.setattr(ex, "_try_import_pytesseract", lambda: None)
    with pytest.raises(ex.OcrEngineMissingError):
        ex.searchable_pdf(_scan_pdf())


# --------------------------------------------------------------------------
# API: contratto HTTP
# --------------------------------------------------------------------------
def test_api_protect_unprotect_roundtrip(client):
    res = _post_edit(client, _make_pdf(1), action="protect",
                     pdf_pw="pw123", allow_copy="false")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["action"] == "protect"
    name, protected = body["results"][0]["name"], _download(client, body)
    assert name.startswith("doc_prot")
    doc = _load(protected)
    assert doc.needs_pass and doc.authenticate("pw123") > 0

    res2 = client.post("/api/pdf-edit", data={"action": "unprotect", "pdf_pw": "pw123"},
                       files=[("file", (name, protected, "application/pdf"))])
    assert res2.status_code == 200, res2.text
    plain = _download(client, res2.json())
    doc2 = _load(plain)
    assert not doc2.needs_pass
    assert "Ciao mondo" in doc2[0].get_text()


def test_api_protect_filename_unicode(client):
    res = _post_edit(client, _make_pdf(1), action="protect", pdf_pw="pw",
                     name="contratto àèì 2026.pdf")
    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["name"].startswith("contratto àèì 2026_prot")
    assert _download(client, res.json())  # il download reale risponde


def test_api_protect_missing_password_400(client):
    res = client.post("/api/pdf-edit", data={"action": "protect"},
                      files=[("file", ("d.pdf", _make_pdf(1), "application/pdf"))],
                      headers={"X-VersoCon-Lang": "en"})
    assert res.status_code == 400
    assert "Missing password" in res.json()["detail"]


def test_api_unprotect_wrong_password_400(client):
    protected = pdfedit.protect(_make_pdf(1), "pw123")
    res = client.post("/api/pdf-edit", data={"action": "unprotect", "pdf_pw": "no"},
                      files=[("file", ("d.pdf", protected, "application/pdf"))],
                      headers={"X-VersoCon-Lang": "en"})
    assert res.status_code == 400
    assert "Wrong password" in res.json()["detail"]


def test_api_unprotect_plain_noop_200(client):
    res = _post_edit(client, _make_pdf(1), action="unprotect")
    assert res.status_code == 200
    assert not _load(_download(client, res.json())).needs_pass


def test_api_searchable_without_engine_501(client, monkeypatch):
    monkeypatch.setattr(ex, "_try_import_pytesseract", lambda: None)
    res = _post_edit(client, _scan_pdf(), action="searchable")
    assert res.status_code == 501


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_api_searchable_roundtrip(client):
    res = _post_edit(client, _scan_pdf(), action="searchable", ocr_lang="ita")
    assert res.status_code == 200, res.text
    assert res.json()["action"] == "searchable"
    doc = _load(_download(client, res.json()))
    assert "RICERCABILE" in doc[0].get_text().upper()


def test_api_image_ocr_bad_mode_400(client):
    res = client.post("/api/image-ocr", data={"mode": "docx"},
                      files=[("file", ("img.png", _scan_png(), "image/png"))])
    assert res.status_code == 400


def test_api_image_ocr_non_image_400(client):
    res = client.post("/api/image-ocr", data={"mode": "text"},
                      files=[("file", ("note.txt", b"ciao", "text/plain"))])
    assert res.status_code == 400


def test_api_image_ocr_without_engine_501(client, monkeypatch):
    monkeypatch.setattr(ex, "_try_import_pytesseract", lambda: None)
    res = client.post("/api/image-ocr", data={"mode": "text"},
                      files=[("file", ("img.png", _scan_png(), "image/png"))])
    assert res.status_code == 501


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_api_image_ocr_text_roundtrip(client):
    res = client.post("/api/image-ocr", data={"mode": "text", "lang": "ita"},
                      files=[("file", ("foto.png", _scan_png(), "image/png"))])
    assert res.status_code == 200, res.text
    body = res.json()
    assert "RICERCABILE" in body["text"].upper()
    saved = client.get(body["results"][0]["download"]).content.decode("utf-8")
    assert "RICERCABILE" in saved.upper()


@pytest.mark.skipif(not ENABLED, reason="OCR non disponibile")
def test_api_image_ocr_pdf_roundtrip(client):
    from PIL import Image

    jpg = io.BytesIO()
    Image.open(io.BytesIO(_scan_png())).convert("RGB").save(jpg, format="JPEG", quality=90)
    res = client.post("/api/image-ocr", data={"mode": "pdf", "lang": "ita"},
                      files=[("file", ("foto.jpg", jpg.getvalue(), "image/jpeg"))])
    assert res.status_code == 200, res.text
    doc = _load(_download(client, res.json()))
    assert "RICERCABILE" in doc[0].get_text().upper()
