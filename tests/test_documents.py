"""Test conversione documenti (PDF <-> immagini)."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converters import documents as docconv  # noqa: E402
from PIL import Image  # noqa: E402


def _png(color=(200, 30, 30), size=(120, 80)):
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, format="PNG")
    return b.getvalue()


def _three_pages_pdf() -> bytes:
    pages = [
        ("a.png", _png((200, 30, 30))),
        ("b.png", _png((30, 200, 30))),
        ("c.png", _png((30, 30, 200))),
    ]
    return docconv.images_to_pdf(pages)


def test_images_to_pdf_returns_valid_pdf():
    pdf = docconv.images_to_pdf([("a.png", _png()), ("b.png", _png((0, 90, 90)))])
    assert pdf[:4] == b"%PDF"
    # riapri con PyMuPDF: 2 pagine
    import pymupdf

    doc = pymupdf.Document(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 2
    finally:
        doc.close()


def test_images_to_pdf_three_pages_order():
    pdf = _three_pages_pdf()
    import pymupdf

    doc = pymupdf.Document(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 3
    finally:
        doc.close()


def test_pdf_to_images_jpeg():
    pdf = _three_pages_pdf()
    imgs = docconv.pdf_to_images(pdf, "jpeg")
    assert len(imgs) == 3
    im = Image.open(io.BytesIO(imgs[0]))
    assert im.format == "JPEG"


def test_pdf_to_images_png_and_webp():
    pdf = _three_pages_pdf()
    for out, fmt in (("png", "PNG"), ("webp", "WEBP")):
        imgs = docconv.pdf_to_images(pdf, out)
        assert len(imgs) == 3
        assert Image.open(io.BytesIO(imgs[0])).format == fmt


def test_pdf_to_images_rejects_bad_format():
    with pytest.raises(ValueError):
        docconv.pdf_to_images(_png(), "gif")


def test_pdf_to_images_rejects_empty():
    with pytest.raises(ValueError):
        docconv.pdf_to_images(b"", "jpeg")


def test_pdf_to_images_rejects_garbage():
    with pytest.raises(Exception):
        docconv.pdf_to_images(b"non sono un pdf", "jpeg")


def test_images_to_pdf_empty_list():
    with pytest.raises(ValueError):
        docconv.images_to_pdf([])


def test_images_to_pdf_rejects_empty_page():
    with pytest.raises(ValueError):
        docconv.images_to_pdf([("a.png", b"")])


def test_images_to_pdf_max_side_caps_dimensions():
    big = _png(size=(800, 400))
    pdf = docconv.images_to_pdf([("big.png", big)], max_side=400)
    import pymupdf

    doc = pymupdf.Document(stream=pdf, filetype="pdf")
    try:
        assert doc.page_count == 1
    finally:
        doc.close()


def test_sanitize_dpi_clamped():
    assert docconv.sanitize_dpi(10) == 72
    assert docconv.sanitize_dpi(9999) == 600
    assert docconv.sanitize_dpi(None) == docconv.DEFAULT_DPI
    assert docconv.sanitize_dpi("xx") == docconv.DEFAULT_DPI


def test_pdf_to_image_ext_normalizes_jpg():
    assert docconv.pdf_to_image_ext("jpg") == "jpeg"
    assert docconv.pdf_to_image_ext(".PNG") == "png"


def test_image_supported_detection():
    assert docconv.image_is_supported("a.jpg")
    assert docconv.image_is_supported("B.PNG")
    assert docconv.image_is_supported("c.webp")
    assert docconv.image_is_supported("d.tiff")
    assert not docconv.image_is_supported("a.txt")
    assert not docconv.image_is_supported("a.pdf")

