"""Compressione file: immagini (target size o qualità) e PDF (3 livelli)."""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

# ── limiti comuni ──
MAX_BYTES = 100 * 1024 * 1024
IMAGE_IN_EXT = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
IMAGE_OUT = ("jpeg", "webp", "png")
PDF_LEVELS = ("low", "medium", "high")


def image_is_compressible(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_IN_EXT


def _flatten_rgb(img: Image.Image) -> Image.Image:
    """Assicura RGB per jpeg/webp (composita trasparenza su bianco)."""
    if img.mode in ("RGBA", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        fg = img.convert("RGBA")
        bg.paste(fg, mask=fg.split()[-1])
        return bg
    if img.mode not in ("RGB", "L"):
        return img.convert("RGB")
    return img


def _encode(img: Image.Image, fmt: str, quality: int, max_side: int | None) -> bytes:
    work = img
    if max_side and max_side > 0:
        w, h = work.size
        longest = max(w, h)
        if longest > max_side:
            s = max_side / longest
            work = work.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    if fmt != "png":
        work = _flatten_rgb(work)
    q = max(1, min(100, quality))
    buf = io.BytesIO()
    if fmt == "jpeg":
        work.save(buf, format="JPEG", quality=q, optimize=True)
    elif fmt == "webp":
        work.save(buf, format="WEBP", quality=q, optimize=True)
    else:
        work.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def compress_image(
    data: bytes,
    out_format: str = "jpeg",
    quality: int | None = None,
    max_side: int | None = None,
    target_bytes: int | None = None,
) -> tuple[bytes, dict]:
    """Comprime un'immagine; ritorna (byte_output, metadata).

    Se target_bytes > 0: binary search sulla qualità, poi riduzione max_side
    progressiva se necessario. Altrimenti usa quality (default 80) + max_side.
    """
    fmt = (out_format or "jpeg").lower().lstrip(".")
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt not in IMAGE_OUT:
        raise ValueError(f"Formato di uscita non supportato: {out_format}")
    if not data:
        raise ValueError("File immagine vuoto")
    if len(data) > MAX_BYTES:
        raise ValueError("Immagine oltre il limite di 100 MB")

    src = Image.open(io.BytesIO(data))
    src = ImageOps.exif_transpose(src)

    if target_bytes and target_bytes > 0:
        # binary search su quality
        lo, hi, best = 1, 95, 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if len(_encode(src, fmt, mid, max_side)) <= target_bytes:
                best, lo = mid, mid + 1
            else:
                hi = mid - 1
        out = _encode(src, fmt, best, max_side)
        # se ancora sopra, riduci max_side progressivamente
        if len(out) > target_bytes:
            side = min(src.size) // 2
            for _ in range(10):
                if side < 16:
                    break
                out2 = _encode(src, fmt, 1, side)
                if len(out2) <= target_bytes or side < 32:
                    out = out2 if len(out2) < len(out) else out
                    break
                out = out2
                side //= 2
        im2 = Image.open(io.BytesIO(out))
        return out, {
            "width": im2.width, "height": im2.height,
            "format": fmt, "size": len(out),
            "quality": best, "target": target_bytes,
            "reached_target": len(out) <= target_bytes,
        }

    q = max(1, min(100, quality or 80))
    out = _encode(src, fmt, q, max_side)
    im2 = Image.open(io.BytesIO(out))
    return out, {"width": im2.width, "height": im2.height, "format": fmt, "size": len(out), "quality": q}


def _pdf_save_kwargs(level: str) -> dict:
    if level == "low":
        return {"garbage": 1, "deflate_fonts": 1}
    if level == "medium":
        return {"garbage": 2, "deflate": 1, "deflate_images": 1, "deflate_fonts": 1}
    return {"garbage": 3, "deflate": 1, "deflate_images": 1, "deflate_fonts": 1, "compression_effort": 9}


def compress_pdf(data: bytes, level: str = "medium") -> tuple[bytes, dict]:
    """Comprime un PDF; ritorna (byte_output, metadata).

    level:
      low    → garbage=1, deflate_fonts
      medium → garbage=2, deflate+deflate_images+deflate_fonts
      high   → garbage=3, deflate+deflate_images+deflate_fonts, compression_effort=9
    """
    lvl = (level or "medium").lower()
    if lvl not in PDF_LEVELS:
        raise ValueError(f"Livello non valido: {level!r} (attesi: low, medium, high)")
    if not data:
        raise ValueError("PDF vuoto")
    if len(data) > MAX_BYTES:
        raise ValueError("PDF oltre il limite di 100 MB")

    doc = pymupdf.Document(stream=data, filetype="pdf")
    try:
        page_count = doc.page_count
        out = doc.tobytes(**_pdf_save_kwargs(lvl))
        return out, {"pages": page_count, "size": len(out), "level": lvl}
    finally:
        doc.close()
