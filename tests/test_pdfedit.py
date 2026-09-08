"""Test per converters/pdfedit.py (Editor PDF su pymupdf).

Copro: riordino, eliminazione, rotazione (cumulativa), watermark testo (opacità + angoli +
rotazione valida/non valida), firma in immagine (angoli, dimensioni, validità immagine),
errori di validazione (PDF vuoto/bad permutazione/pagine fuori range/angolo watermark),
limiti (num pagine >500, immagine firma >20MB).
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

from converters import pdfedit  # noqa: E402


def _make_pdf(n_pages: int = 3, txt_per_page: str | None = None) -> bytes:
    doc = pymupdf.Document()
    for i in range(n_pages):
        page = doc.new_page(width=300, height=200)
        page.insert_text((20, 100), txt_per_page or f"PAGINA-{i + 1}", fontsize=24, color=(0, 0, 0))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _load(b: bytes) -> pymupdf.Document:
    return pymupdf.Document(stream=b, filetype="pdf")


# --------------------------------------------------------------------------
# Reorder
# --------------------------------------------------------------------------
def test_reorder_single_pdf():
    d = _make_pdf(3)
    out = pdfedit.reorder_pages(d, [3, 1, 2])
    doc = _load(out)
    assert doc.page_count == 3
    t0 = doc[0].get_text().strip()
    t1 = doc[1].get_text().strip()
    t2 = doc[2].get_text().strip()
    assert "PAGINA-3" in t0
    assert "PAGINA-1" in t1
    assert "PAGINA-2" in t2


def test_reorder_identity():
    d = _make_pdf(3)
    out = pdfedit.reorder_pages(d, [1, 2, 3])
    doc = _load(out)
    for i in range(3):
        assert f"PAGINA-{i + 1}" in doc[i].get_text()


def test_reorder_bad_permutation():
    d = _make_pdf(3)
    with pytest.raises(ValueError, match="permutazione"):
        pdfedit.reorder_pages(d, [1, 2])  # manca 3
    with pytest.raises(ValueError, match="permutazione"):
        pdfedit.reorder_pages(d, [1, 1, 2])  # duplicato
    with pytest.raises(ValueError, match="permutazione"):
        pdfedit.reorder_pages(d, [1, 2, 5])  # fuori range


def test_reorder_rejects_non_list():
    d = _make_pdf(3)
    with pytest.raises(ValueError):
        pdfedit.reorder_pages(d, 3)


def test_reorder_empty_pdf_raises():
    with pytest.raises(ValueError):
        pdfedit.reorder_pages(b"", [1])


# --------------------------------------------------------------------------
# Delete
# --------------------------------------------------------------------------
def test_delete_single_page():
    d = _make_pdf(3)
    out = pdfedit.delete_pages(d, [2])
    doc = _load(out)
    assert doc.page_count == 2
    assert "PAGINA-1" in doc[0].get_text()
    assert "PAGINA-3" in doc[1].get_text()
    assert "PAGINA-2" not in doc[0].get_text() + doc[1].get_text()


def test_delete_multiple_pages():
    d = _make_pdf(4)
    out = pdfedit.delete_pages(d, [1, 3])
    doc = _load(out)
    assert doc.page_count == 2
    assert "PAGINA-2" in doc[0].get_text()
    assert "PAGINA-4" in doc[1].get_text()


def test_delete_int_shorthand():
    d = _make_pdf(2)
    out = pdfedit.delete_pages(d, 1)
    doc = _load(out)
    assert doc.page_count == 1
    assert "PAGINA-2" in doc[0].get_text()


def test_delete_all_pages_forbidden():
    d = _make_pdf(3)
    with pytest.raises(ValueError, match="tutte le pagine"):
        pdfedit.delete_pages(d, [1, 2, 3])


def test_delete_out_of_range():
    d = _make_pdf(2)
    with pytest.raises(ValueError, match="fuori range"):
        pdfedit.delete_pages(d, [5])
    with pytest.raises(ValueError, match="fuori range"):
        pdfedit.delete_pages(d, [0])


def test_delete_noop_returns_data():
    d = _make_pdf(2)
    out = pdfedit.delete_pages(d, [])
    assert out == d  # stesso byte


# --------------------------------------------------------------------------
# Rotate
# --------------------------------------------------------------------------
def test_rotate_90_cw():
    d = _make_pdf(2)
    out = pdfedit.rotate_pages(d, [1], angle=90)
    doc = _load(out)
    assert doc[0].rotation == 90
    assert doc[1].rotation == 0


def test_rotate_cumulative():
    d = _make_pdf(1)
    out1 = pdfedit.rotate_pages(d, [1], angle=90)
    out2 = pdfedit.rotate_pages(out1, [1], angle=90)
    doc = _load(out2)
    assert doc[0].rotation == 180


def test_rotate_multiple_target():
    d = _make_pdf(3)
    out = pdfedit.rotate_pages(d, [1, 3], angle=180)
    doc = _load(out)
    assert doc[0].rotation == 180
    assert doc[1].rotation == 0
    assert doc[2].rotation == 180


@pytest.mark.parametrize("bad", [-90, 45, 720, -180, "abc", 5])
def test_rotate_invalid_angle(bad):
    d = _make_pdf(1)
    with pytest.raises(ValueError):
        pdfedit.rotate_pages(d, [1], angle=bad)


def test_rotate_270_ccw_valid():
    d = _make_pdf(1)
    out = pdfedit.rotate_pages(d, [1], angle=270)  # 270° CW = 90° CCW
    assert _load(out)[0].rotation == 270


def test_rotate_0_noop():
    d = _make_pdf(1)
    out = pdfedit.rotate_pages(d, [1], angle=0)
    assert out == d


# --------------------------------------------------------------------------
# Watermark testo
# --------------------------------------------------------------------------
def test_watermark_basic():
    d = _make_pdf(2)
    out = pdfedit.watermark_text(d, "DRFT", corner="center", opacity=0.3, font_size=40)
    doc = _load(out)
    assert doc.page_count == 2
    # il testo watermark è presente sulle pagine
    for i in range(2):
        assert "DRFT" in doc[i].get_text()


def test_watermark_all_corners_accepted():
    d = _make_pdf(1)
    for c in ("tl", "tr", "bl", "br", "center"):
        out = pdfedit.watermark_text(d, "X", corner=c)
        assert _load(out).page_count == 1


def test_watermark_invalid_corner_rejected():
    d = _make_pdf(1)
    with pytest.raises(ValueError, match="Angolo watermark"):
        pdfedit.watermark_text(d, "X", corner="middle")


def test_watermark_empty_text_rejected():
    d = _make_pdf(1)
    with pytest.raises(ValueError, match="Testo watermark vuoto"):
        pdfedit.watermark_text(d, "  ")


def test_watermark_invalid_rotate_rejected():
    d = _make_pdf(1)
    with pytest.raises(ValueError, match="non supportata"):
        pdfedit.watermark_text(d, "X", rotate=45)


def test_watermark_clamps_opacity_out_of_range():
    d = _make_pdf(1)
    # 1.5 e -0.5 sono clampati a 1.0 e 0.0 — non devono crashare
    out1 = pdfedit.watermark_text(d, "X", opacity=99)
    out2 = pdfedit.watermark_text(d, "X", opacity=-99)
    assert _load(out1).page_count == 1
    assert _load(out2).page_count == 1


def test_watermark_fontsize_clamped():
    d = _make_pdf(1)
    out = pdfedit.watermark_text(d, "A" * 50, font_size=999)
    doc = _load(out)
    assert doc.page_count == 1


# --------------------------------------------------------------------------
# Firma in immagine
# --------------------------------------------------------------------------
def _signature_img() -> bytes:
    im = Image.new("RGBA", (200, 80), (255, 255, 255, 255))
    from PIL import ImageDraw

    d = ImageDraw.Draw(im)
    d.line((20, 40, 180, 40), fill=(0, 0, 255, 255), width=4)
    d.ellipse((40, 20, 60, 60), outline=(0, 0, 255, 255), width=3)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_signature_basic_bottomleft():
    d = _make_pdf(1)
    out = pdfedit.add_signature(d, _signature_img(), page=1, corner="bl")
    doc = _load(out)
    # la firma è un'immagine → get_images non vuoto
    imgs = doc[0].get_images(full=True)
    assert len(imgs) >= 1


@pytest.mark.parametrize("c", ["tl", "tr", "bl", "br", "center"])
def test_signature_all_corners(c):
    d = _make_pdf(1)
    out = pdfedit.add_signature(d, _signature_img(), page=1, corner=c)
    doc = _load(out)
    assert len(doc[0].get_images(full=True)) >= 1


def test_signature_invalid_page():
    d = _make_pdf(2)
    with pytest.raises(ValueError, match="fuori range"):
        pdfedit.add_signature(d, _signature_img(), page=5)
    with pytest.raises(ValueError, match="fuori range"):
        pdfedit.add_signature(d, _signature_img(), page=0)


def test_signature_invalid_corner():
    d = _make_pdf(1)
    with pytest.raises(ValueError, match="[Pp]osizione firma"):
        pdfedit.add_signature(d, _signature_img(), corner="middle")


def test_signature_size_clamped():
    d = _make_pdf(1)
    # width estremo → clamped [0.3, 20]
    out1 = pdfedit.add_signature(d, _signature_img(), width=99)
    out2 = pdfedit.add_signature(d, _signature_img(), width=0.01)
    assert _load(out1).page_count == 1
    assert _load(out2).page_count == 1


def test_signature_rejects_empty_image():
    d = _make_pdf(1)
    with pytest.raises(ValueError, match="Immagine firma vuota"):
        pdfedit.add_signature(d, b"")


def test_signature_rejects_non_image():
    d = _make_pdf(1)
    with pytest.raises(ValueError, match="non valida"):
        pdfedit.add_signature(d, b"not an image at all")


def test_signature_rejects_oversized():
    d = _make_pdf(1)
    big = b"\x00" * (pdfedit.MAX_IMAGE_BYTES + 1)
    with pytest.raises(ValueError, match="20 MB"):
        pdfedit.add_signature(d, big)


def test_signature_grayscale_converts_to_rgba():
    d = _make_pdf(1)
    im = Image.new("L", (100, 50), 200)
    buf = io.BytesIO(); im.save(buf, format="PNG")
    out = pdfedit.add_signature(d, buf.getvalue())
    assert len(_load(out)[0].get_images(full=True)) >= 1


# --------------------------------------------------------------------------
# Limiti
# --------------------------------------------------------------------------
def test_empty_pdf_rejected_all_actions():
    with pytest.raises(ValueError, match="PDF vuoto"):
        pdfedit.reorder_pages(b"", [1])
    with pytest.raises(ValueError, match="PDF vuoto"):
        pdfedit.delete_pages(b"", [1])
    with pytest.raises(ValueError, match="PDF vuoto"):
        pdfedit.rotate_pages(b"", [1], 90)
    with pytest.raises(ValueError, match="PDF vuoto"):
        pdfedit.watermark_text(b"", "x")
    with pytest.raises(ValueError, match="PDF vuoto"):
        pdfedit.add_signature(b"", _signature_img())


def test_invalid_pdf_rejected():
    with pytest.raises(Exception, match="non valido|Empty"):
        pdfedit.reorder_pages(b"not a pdf at all", [1])
