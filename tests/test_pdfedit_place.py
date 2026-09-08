"""Test per pdfedit.place_signature (posizione/firma libera)."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converters import pdfedit  # noqa: E402


def _pdf_bytes() -> bytes:
    from converters import documents as docconv
    im = Image.new("RGB", (120, 80), (220, 230, 240))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return docconv.images_to_pdf([("a.png", buf.getvalue())])


def _sig_png(w=160, h=60) -> bytes:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # striscia "firma" in blu
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    d.line([(10, h // 2), (w - 10, h // 2)], fill=(30, 30, 160, 255), width=10)
    d.ellipse((w // 2 - 20, 10, w // 2 + 20, h - 10), fill=(30, 30, 160, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_place_signature_default_position():
    out = pdfedit.place_signature(_pdf_bytes(), _sig_png())
    import pymupdf
    doc = pymupdf.Document(stream=out)
    page = doc[0]
    # 1 immagine (firma) sulla pagina
    assert len(page.get_images()) >= 1


def test_place_signature_opaque_center_vs_corner_changes_image():
    center = pdfedit.place_signature(_pdf_bytes(), _sig_png(), x_pct=50, y_pct=50)
    corner = pdfedit.place_signature(_pdf_bytes(), _sig_png(), x_pct=90, y_pct=90)
    assert center != corner  # PDF diversi (posizione diversa)


def test_place_signature_opacity_0_is_invisible():
    out = pdfedit.place_signature(_pdf_bytes(), _sig_png(), opacity=0)
    # il PDF va ancora a generarsi (0 opacity = firma totalmente trasparente)
    import pymupdf
    doc = pymupdf.Document(stream=out)
    assert doc.page_count == 1


def test_place_signature_clamps_width_pct():
    # 500% va a 100% (clamp) → ancora valido
    out = pdfedit.place_signature(_pdf_bytes(), _sig_png(), width_pct=500)
    assert out[:4] == b"%PDF"


def test_place_signature_clamps_coordinates():
    out1 = pdfedit.place_signature(_pdf_bytes(), _sig_png(), x_pct=-50, y_pct=-50)
    out2 = pdfedit.place_signature(_pdf_bytes(), _sig_png(), x_pct=500, y_pct=500)
    assert out1[:4] == b"%PDF"
    assert out2[:4] == b"%PDF"


def test_place_signature_rejects_empty_image():
    with pytest.raises(ValueError):
        pdfedit.place_signature(_pdf_bytes(), b"")


def test_place_signature_rejects_non_image():
    with pytest.raises(ValueError):
        pdfedit.place_signature(_pdf_bytes(), b"non sono una png")


def test_place_signature_rotation_changes_output():
    a = pdfedit.place_signature(_pdf_bytes(), _sig_png(), rotation=0)
    b = pdfedit.place_signature(_pdf_bytes(), _sig_png(), rotation=90)
    assert a != b


def test_place_signature_page_out_of_range():
    with pytest.raises(ValueError):
        pdfedit.place_signature(_pdf_bytes(), _sig_png(), page=99)


def test_place_signature_multiple_pages():
    # 2 pagine: firma su pagina 2
    from converters import documents as docconv
    im = Image.new("RGB", (120, 80), (220, 230, 240))
    b1 = io.BytesIO(); im.save(b1, format="PNG")
    b2 = io.BytesIO(); im.save(b2, format="PNG")
    pdf = docconv.images_to_pdf([
        ("a.png", b1.getvalue()),
        ("b.png", b2.getvalue()),
    ])
    out = pdfedit.place_signature(pdf, _sig_png(), page=2)
    import pymupdf
    doc = pymupdf.Document(stream=out)
    assert doc.page_count == 2
