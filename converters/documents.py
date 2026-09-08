"""Conversione documenti: PDF -> immagini, immagini -> PDF."""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image

PDF_TO_IMAGE_OUT = ("jpeg", "png", "webp")
IMAGES_TO_PDF_IN = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
MAX_DOC_BYTES = 100 * 1024 * 1024
MAX_DOC_PAGES = 60
MAX_IMAGES_PER_PDF = 50
DEFAULT_DPI = 150
JPEG_Q = 92


def pdf_to_image_ext(out_format: str) -> str:
    o = (out_format or "jpeg").lower().lstrip(".")
    if o == "jpg":
        o = "jpeg"
    if o not in PDF_TO_IMAGE_OUT:
        raise ValueError(f"Formato di uscita non supportato: {out_format}")
    return o


def image_is_supported(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGES_TO_PDF_IN


def sanitize_dpi(dpi) -> int:
    try:
        v = int(dpi)
    except (TypeError, ValueError):
        return DEFAULT_DPI
    return max(72, min(600, v))


def _pil_to_bytes(img: Image.Image, out: str, quality: int | None) -> bytes:
    if out not in ("png",) and img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        fg = img.convert("RGBA")
        bg.paste(fg, mask=fg.split()[-1])
        img = bg
    buf = io.BytesIO()
    if out == "jpeg":
        img.save(buf, format="JPEG", quality=quality or JPEG_Q, optimize=True)
    elif out == "png":
        img.save(buf, format="PNG")
    else:
        img.save(buf, format="WEBP", quality=quality or JPEG_Q)
    return buf.getvalue()


def pdf_to_images(
    data: bytes,
    out_format: str = "jpeg",
    dpi: int | None = None,
    quality: int | None = None,
) -> list[bytes]:
    """Ogni pagina del PDF diventa un'immagine (max MAX_DOC_PAGES pagine)."""
    out = pdf_to_image_ext(out_format)
    if not data:
        raise ValueError("PDF vuoto")
    doc = pymupdf.Document(stream=data, filetype="pdf")
    try:
        n = min(doc.page_count, MAX_DOC_PAGES)
        zoom = sanitize_dpi(dpi) / 72.0
        mat = pymupdf.Matrix(zoom, zoom)
        out_bytes = []
        for i in range(n):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            out_bytes.append(_pil_to_bytes(img, out, quality))
        return out_bytes
    finally:
        doc.close()


def images_to_pdf(files: list[tuple[str, bytes]], max_side: int | None = None) -> bytes:
    """Immagini -> un unico PDF, un'immagine per pagina."""
    if not isinstance(files, (list, tuple)) or not files:
        raise ValueError("Nessuna immagine da convertire")
    if len(files) > MAX_IMAGES_PER_PDF:
        raise ValueError(f"Massimo {MAX_IMAGES_PER_PDF} immagini per PDF (ne sono {len(files)})")

    pages: list[bytes] = []
    for _name, raw in files:
        if not raw:
            raise ValueError("File vuoto")
        img = Image.open(io.BytesIO(raw))
        if img.format not in ("JPEG", "JPG", "PNG", "WEBP", "BMP", "TIFF"):
            raise ValueError("Formato immagine non supportato")
        if max_side:
            try:
                ms = int(max_side)
            except (TypeError, ValueError):
                ms = 0
            if ms > 0:
                w, h = img.size
                m = max(w, h)
                if m > ms:
                    s = ms / m
                    img = img.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        pages.append(_pil_to_bytes(img, "jpeg", JPEG_Q))

    doc = pymupdf.Document()
    for raw in pages:
        img = Image.open(io.BytesIO(raw))
        page = doc.new_page(width=img.width, height=img.height)
        page.insert_image(pymupdf.Rect(0, 0, img.width, img.height), stream=raw, keep_proportion=False)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out
