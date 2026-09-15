"""FEAT-E (E1): anteprima live dell'editor PDF — dry-run lato server.

Copre `converters.pdfedit.render_page_png` (unità) e il contratto HTTP di
`POST /api/pdf-edit-preview`: stessi campi Form di `/api/pdf-edit` (verificato
sul contratto OpenAPI), azione applicata o non applicata, PNG valido, pagina
limitata dopo `delete`, nessun file scritto in OUT_DIR, `dpi`, errori tradotti,
nome file unicode e soglia di tempo per pagina.
"""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402

from app import main as mainmod  # noqa: E402
from app.main import app  # noqa: E402
from converters import pdfedit  # noqa: E402


def _make_pdf(n_pages: int = 2) -> bytes:
    doc = pymupdf.Document()
    for i in range(n_pages):
        page = doc.new_page(width=300, height=200)
        page.insert_text((20, 100), f"PAGINA-{i + 1}", fontsize=18)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _signature_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (80, 40), "black").save(buf, format="PNG")
    return buf.getvalue()


def _pixels(png: bytes) -> bytes:
    return Image.open(io.BytesIO(png)).convert("RGB").tobytes()


@pytest.fixture()
def client():
    return TestClient(app)


def _post_preview(client, pdf: bytes, name: str = "doc.pdf", sig: bytes | None = None, **fields):
    data = {k: str(v) for k, v in fields.items()}
    files = [("file", (name, pdf, "application/pdf"))]
    if sig is not None:
        files.append(("signature", ("firma.png", sig, "image/png")))
    return client.post("/api/pdf-edit-preview", data=data, files=files)


# --------------------------------------------------------------------------
# Unità: render_page_png
# --------------------------------------------------------------------------
def test_render_png_dimensioni_e_metadati():
    png, used, total = pdfedit.render_page_png(_make_pdf(2), page=1, dpi=72)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert (used, total) == (1, 2)
    im = Image.open(io.BytesIO(png))
    assert abs(im.width - 300) <= 2 and abs(im.height - 200) <= 2


def test_render_pagina_oltre_il_fine_viene_limitata():
    png, used, total = pdfedit.render_page_png(_make_pdf(3), page=99, dpi=60)
    assert (used, total) == (3, 3)
    assert png


def test_render_dpi_fuori_range():
    with pytest.raises(ValueError, match="dpi"):
        pdfedit.render_page_png(_make_pdf(1), dpi=10)
    with pytest.raises(ValueError, match="dpi"):
        pdfedit.render_page_png(_make_pdf(1), dpi=1000)


def test_render_pdf_protetto_richiede_password():
    protected = pdfedit.protect(_make_pdf(1), "segreta", owner_pw="padrone")
    with pytest.raises(ValueError, match="protetto"):
        pdfedit.render_page_png(protected, password="")
    with pytest.raises(ValueError, match="protetto"):
        pdfedit.render_page_png(protected, password="errata")
    png, used, _ = pdfedit.render_page_png(protected, password="segreta")
    assert png and used == 1


def test_render_rispetta_tetto_pixel(monkeypatch):
    monkeypatch.setattr(pdfedit, "MAX_PREVIEW_PIXELS", 100_000)
    png, _, _ = pdfedit.render_page_png(_make_pdf(1), dpi=300)
    im = Image.open(io.BytesIO(png))
    assert im.width * im.height <= 100_000


# --------------------------------------------------------------------------
# Contratto HTTP
# --------------------------------------------------------------------------
def test_contratto_stessi_campi_form_di_pdf_edit():
    comps = app.openapi()["components"]["schemas"]
    sync = comps["PdfEditForm"]
    prev = comps["PdfEditPreviewForm"]
    shared = set(sync["properties"])
    assert shared <= set(prev["properties"])
    assert set(prev["properties"]) - shared == {"page", "dpi"}
    for name in sorted(shared):
        assert prev["properties"][name] == sync["properties"][name], name
    assert set(sync.get("required", [])) <= set(prev.get("required", []))


def test_preview_azione_non_applicata_pagina_identica(client):
    pdf = _make_pdf(2)
    base = pdfedit.render_page_png(pdf, page=1, dpi=110)[0]
    r = _post_preview(client, pdf, action="rotate", angle=0, page=1, dpi=110)
    assert r.status_code == 200, r.text
    assert _pixels(r.content) == _pixels(base)
    assert r.headers["X-Page"] == "1" and r.headers["X-Pages"] == "2"
    assert r.headers["X-Action"] == "rotate"
    assert r.headers["Content-Type"].startswith("image/png")
    assert r.headers["Cache-Control"] == "no-store"


def test_preview_azione_applicata_pixel_cambiati(client):
    pdf = _make_pdf(1)
    base = _post_preview(client, pdf, action="rotate", angle=0, page=1)
    rot = _post_preview(client, pdf, action="rotate", angle=180, page=1)
    assert base.status_code == 200 and rot.status_code == 200
    assert _pixels(rot.content) != _pixels(base.content)


def test_preview_watermark_visibile(client):
    pdf = _make_pdf(1)
    base = _post_preview(client, pdf, action="rotate", angle=0, page=1)
    wm = _post_preview(client, pdf, action="watermark", wm_text="BOZZA", wm_size=40, wm_opacity=0.9)
    assert wm.status_code == 200, wm.text
    assert _pixels(wm.content) != _pixels(base.content)


def test_preview_firma_caricata(client):
    pdf = _make_pdf(1)
    base = _post_preview(client, pdf, action="rotate", angle=0, page=1)
    sig = _post_preview(client, pdf, action="signature", sig_page=1, sig_corner="center",
                        sig=_signature_png())
    assert sig.status_code == 200, sig.text
    assert _pixels(sig.content) != _pixels(base.content)


def test_preview_pagina_limitata_dopo_delete(client):
    r = _post_preview(client, _make_pdf(3), action="delete", pages="[3]", page=3)
    assert r.status_code == 200, r.text
    assert r.headers["X-Page"] == "2" and r.headers["X-Pages"] == "2"


def test_preview_stessi_dati_del_sync(client):
    pdf = _make_pdf(2)
    fields = dict(action="number", pages="1", num_position="br", text_size=10)
    sync = client.post("/api/pdf-edit", data=fields,
                       files=[("file", ("doc.pdf", pdf, "application/pdf"))])
    prev = _post_preview(client, pdf, **fields)
    assert sync.status_code == 200, sync.text
    assert prev.status_code == 200, prev.text


def test_preview_dpi_scala_le_dimensioni(client):
    pdf = _make_pdf(1)
    lo = _post_preview(client, pdf, action="rotate", angle=0, dpi=60)
    hi = _post_preview(client, pdf, action="rotate", angle=0, dpi=120)
    assert lo.status_code == 200 and hi.status_code == 200
    w_lo = Image.open(io.BytesIO(lo.content)).width
    w_hi = Image.open(io.BytesIO(hi.content)).width
    assert abs(w_hi - 2 * w_lo) <= 2


def test_preview_dpi_e_pagina_fuori_range_422(client):
    pdf = _make_pdf(1)
    assert _post_preview(client, pdf, action="rotate", dpi=10).status_code == 422
    assert _post_preview(client, pdf, action="rotate", dpi=1000).status_code == 422
    assert _post_preview(client, pdf, action="rotate", page=0).status_code == 422


def test_preview_non_scrive_output(client):
    before = {p.name for p in mainmod.OUT_DIR.iterdir()}
    r = _post_preview(client, _make_pdf(2), action="rotate", angle=90, page=1)
    assert r.status_code == 200
    after = {p.name for p in mainmod.OUT_DIR.iterdir()}
    assert after == before


def test_preview_nome_file_unicode(client):
    r = _post_preview(client, _make_pdf(1), name="caffè 日本 写真.pdf", action="rotate", angle=90)
    assert r.status_code == 200, r.text
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_errore_non_pdf_tradotto(client):
    r = client.post("/api/pdf-edit-preview", data={"action": "rotate"},
                    files=[("file", ("nota.txt", b"ciao", "text/plain"))])
    assert r.status_code == 400
    assert "nota.txt" in r.text and "PDF" in r.text


def test_preview_file_vuoto(client):
    r = client.post("/api/pdf-edit-preview", data={"action": "rotate"},
                    files=[("file", ("vuoto.pdf", b"", "application/pdf"))])
    assert r.status_code == 400
    assert "vuoto.pdf" in r.text


def test_preview_azione_invalida(client):
    r = _post_preview(client, _make_pdf(1), action="teleport")
    assert r.status_code == 400
    assert "teleport" in r.text


def test_preview_errore_converter_400(client):
    r = _post_preview(client, _make_pdf(1), action="annotate", page_num=1, needle="assente")
    assert r.status_code == 400


def test_preview_protect_renderizza_con_password(client):
    r = _post_preview(client, _make_pdf(1), action="protect", pdf_pw="segreta", page=1)
    assert r.status_code == 200, r.text
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_soglia_tempo(client):
    pdf = _make_pdf(3)
    _post_preview(client, pdf, action="rotate", angle=0, page=1)  # warmup
    t0 = time.perf_counter()
    r = _post_preview(client, pdf, action="rotate", angle=90, page=1, dpi=110)
    dt = time.perf_counter() - t0
    assert r.status_code == 200
    assert dt < 3.0, f"anteprima troppo lenta: {dt:.2f}s"
