"""Test strumenti batch: merge PDF, split PDF, rinomina."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converters import documents as docconv  # noqa: E402
from converters import tools as toolconv  # noqa: E402
from PIL import Image  # noqa: E402


def _png(color=(200, 30, 30), size=(120, 80)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, format="PNG")
    return b.getvalue()


def _one_page_pdf(label: bytes = b"a") -> bytes:
    return docconv.images_to_pdf([("x.png", _png())])


def _three_pages_pdf() -> bytes:
    return docconv.images_to_pdf(
        [
            ("a.png", _png((200, 30, 30))),
            ("b.png", _png((30, 200, 30))),
            ("c.png", _png((30, 30, 200))),
        ]
    )


def test_pdf_page_count():
    assert toolconv.pdf_page_count(_one_page_pdf()) == 1
    assert toolconv.pdf_page_count(_three_pages_pdf()) == 3


def test_merge_two_pdfs():
    out = toolconv.merge_pdfs([("a.pdf", _one_page_pdf()), ("b.pdf", _one_page_pdf())])
    assert out[:4] == b"%PDF"
    assert toolconv.pdf_page_count(out) == 2


def test_merge_preserves_order_count():
    out = toolconv.merge_pdfs([(f"f{i}.pdf", _one_page_pdf()) for i in range(4)])
    assert toolconv.pdf_page_count(out) == 4


def test_merge_requires_pdf_ext():
    with pytest.raises(ValueError):
        toolconv.merge_pdfs([("a.txt", _png())])


def test_merge_rejects_empty():
    with pytest.raises(ValueError):
        toolconv.merge_pdfs([])


def test_merge_rejects_empty_file():
    with pytest.raises(ValueError):
        toolconv.merge_pdfs([("a.pdf", b"")])


def test_split_middle_range():
    data = _three_pages_pdf()
    out, pages, total = toolconv.split_pdf(data, start=2, end=2)
    assert total == 3
    assert pages == 1
    assert out[:4] == b"%PDF"
    assert toolconv.pdf_page_count(out) == 1


def test_split_tail_range():
    data = _three_pages_pdf()
    out, pages, total = toolconv.split_pdf(data, start=2, end=3)
    assert total == 3
    assert pages == 2
    assert toolconv.pdf_page_count(out) == 2


def test_split_defaults_full():
    data = _three_pages_pdf()
    out, pages, total = toolconv.split_pdf(data)
    assert total == 3
    assert pages == 3


def test_split_clamps_highbound():
    data = _three_pages_pdf()
    out, pages, total = toolconv.split_pdf(data, start=1, end=99)
    assert total == 3
    assert pages == 3


def test_split_empty_error():
    with pytest.raises(Exception):
        toolconv.split_pdf(b"")


# ---------------- rename ----------------
def test_rename_prefix():
    r = toolconv.rename_preview(["a.jpg", "b.jpg"], mode="prefix", value="viaggio")
    assert r == ["viaggioa.jpg", "viaggiob.jpg"]


def test_rename_suffix():
    r = toolconv.rename_preview(["a.jpg", "b.jpg"], mode="suffix", value="_scan")
    assert r == ["a_scan.jpg", "b_scan.jpg"]


def test_rename_find_replaces():
    r = toolconv.rename_preview(["DSC0012 copia.jpg"], mode="find", value=" copia")
    assert r == ["DSC0012.jpg"]


def test_rename_number_pad():
    r = toolconv.rename_preview(["a.jpg", "b.jpg", "c.jpg"], mode="number", value="foto", start=1, step=1)
    assert r == ["foto-1.jpg", "foto-2.jpg", "foto-3.jpg"]
    r2 = toolconv.rename_preview(["a.jpg", "b.jpg"], mode="number", value="foto", start=10, step=2)
    assert r2 == ["foto-10.jpg", "foto-12.jpg"]


def test_rename_number_pad_wide():
    # 12 file -> padding 2
    r = toolconv.rename_preview([f"x{i}.jpg" for i in range(12)], mode="number", value="img", start=1, step=1)
    assert r[0] == "img-01.jpg"
    assert r[11] == "img-12.jpg"


def test_rename_cleans_invalid_chars():
    r = toolconv.rename_preview(["a.jpg"], mode="prefix", value='a\\b/c:d')
    assert len(r) == 1
    assert "\\" not in r[0] and "/" not in r[0] and ":" not in r[0]


def test_rename_rejects_bad_mode():
    with pytest.raises(ValueError):
        toolconv.rename_preview(["a.jpg"], mode="nonsense")


def test_rename_files_applies_preview():
    files = [("a.jpg", b"x"), ("b.jpg", b"y")]
    out = toolconv.rename_files(files, mode="number", value="f", start=1, step=1)
    assert [n for n, _ in out] == ["f-1.jpg", "f-2.jpg"]
    assert [d for _, d in out] == [b"x", b"y"]


def test_rename_preserves_extension():
    out = toolconv.rename_preview(["x.png", "y.heic"], mode="prefix", value="p")
    assert out[0].endswith(".png")
    assert out[1].endswith(".heic")
