"""Conversione immagini: HEIC/HEIF e formati comuni -> JPEG/PNG/WebP/GIF."""
from __future__ import annotations

import io
from pathlib import Path

import pillow_heif
from PIL import Image, ImageOps

pillow_heif.register_heif_opener()

SUPPORTED_OUT = {"jpeg", "jpg", "png", "webp", "gif"}
ACCEPTED_EXT = {
    ".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp",
    ".bmp", ".tif", ".tiff", ".gif",
}

JPEG_QUALITY = 92
MAX_FRAMES = 500
ORIENTATION_TAG = 0x0112


def is_convertible(filename: str) -> bool:
    return Path(filename).suffix.lower() in ACCEPTED_EXT


def _clamp_quality(quality) -> int:
    try:
        q = int(quality)
    except (TypeError, ValueError):
        return JPEG_QUALITY
    return max(1, min(100, q))


def _maybe_resize(img: Image.Image, max_side) -> Image.Image:
    try:
        ms = int(max_side)
    except (TypeError, ValueError):
        return img
    if ms <= 0:
        return img
    w, h = img.size
    longest = max(w, h)
    if longest <= ms:
        return img
    scale = ms / longest
    return img.resize(
        (max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS
    )


def _flatten(img: Image.Image) -> Image.Image:
    """Immagine RGB con trasparenza composita su bianco."""
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        fg = img.convert("RGBA")
        bg.paste(fg, mask=fg.split()[-1])
        return bg
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def _raw_exif(img: Image.Image) -> bytes:
    exif = img.info.get("exif")
    if exif:
        return bytes(exif)
    try:
        e = img.getexif()
        if e:
            return e.tobytes()
    except Exception:  # noqa: BLE001 - exif is best-effort
        pass
    return b""


def _apply_orientation(img: Image.Image, raw: bytes) -> tuple[Image.Image, bool]:
    """Ruota fisicamente l'immagine se EXIF orientation lo richiede."""
    if not raw:
        return img, False
    try:
        exif = Image.Exif()
        exif.load(bytes(raw))
        op = exif.get(ORIENTATION_TAG)
    except Exception:  # noqa: BLE001
        return img, False
    if not op or op == 1:
        return img, False
    try:
        return ImageOps.exif_transpose(img), True
    except Exception:  # noqa: BLE001
        return img, False


def _exif_payload(raw: bytes, applied: bool) -> bytes:
    """Payload EXIF da riannoiare: orientation normalizzata a 1 se già ruotata."""
    if not raw:
        return b""
    if applied:
        try:
            exif = Image.Exif()
            exif.load(bytes(raw))
            exif[ORIENTATION_TAG] = 1
            raw = exif.tobytes()
        except Exception:  # noqa: BLE001
            return b""
    return bytes(raw)


def _convert_gif(img: Image.Image, max_side) -> bytes:
    """GIF: preserva animazione (con cap di frame), altrimenti GIF statica."""
    n = max(1, min(img.n_frames or 1, MAX_FRAMES))
    try:
        loop = int(img.info.get("loop", 0) or 0)
    except (TypeError, ValueError):
        loop = 0
    frames, durations = [], []
    for i in range(n):
        img.seek(i)
        fr = _flatten(img)
        fr = _maybe_resize(fr, max_side)
        fr = fr.convert("P", palette=Image.ADAPTIVE, colors=256)
        frames.append(fr)
        try:
            durations.append(int(img.info.get("duration", 100) or 100))
        except (TypeError, ValueError):
            durations.append(100)
    buf = io.BytesIO()
    if len(frames) == 1:
        frames[0].save(buf, format="GIF")
    else:
        frames[0].save(
            buf, format="GIF", save_all=True,
            append_images=frames[1:], duration=durations, loop=loop,
        )
    return buf.getvalue()


def convert_bytes(
    data: bytes,
    out_format: str,
    quality: int | None = None,
    max_side: int | None = None,
) -> bytes:
    """Converti i byte di un'immagine in 'jpeg'|'png'|'webp'|'gif'.

    quality: 1-100 (solo JPEG/WebP, default 92). max_side: lato massimo in px
    (0/None = nessuna). EXIF preservata (orientation applicata e normalizzata).
    GIF: se sorgente animata, output GIF animato (max MAX_FRAMES frame);
    altrimenti GIF statica. Sorgenti multi-frame verso formati single-frame
    usano il primo frame.
    """
    out = out_format.lower().lstrip(".")
    if out in ("jpg",):
        out = "jpeg"
    if out not in SUPPORTED_OUT:
        raise ValueError(f"Formato di uscita non supportato: {out_format}")

    q = _clamp_quality(quality)
    img = Image.open(io.BytesIO(data))
    n_frames = getattr(img, "n_frames", 1) or 1

    if out == "gif":
        return _convert_gif(img, max_side)

    raw = _raw_exif(img)
    if n_frames == 1:
        img, applied = _apply_orientation(img, raw)
    else:
        applied = False
        img = img.copy()
    img = _maybe_resize(img, max_side)
    exif = _exif_payload(raw, applied) if n_frames == 1 else b""

    if out == "png":
        if img.mode not in ("RGB", "RGBA", "L", "LA", "P"):
            img = img.convert("RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    img = _flatten(img)

    buf = io.BytesIO()
    if out == "jpeg":
        img.save(buf, format="JPEG", quality=q, optimize=True, exif=exif)
    else:
        img.save(buf, format="WEBP", quality=q, exif=exif)
    return buf.getvalue()


def output_ext(out_format: str) -> str:
    return "jpg" if out_format.lower() in ("jpeg", "jpg") else out_format.lower().lstrip(".")


def convert_file(
    src: Path,
    dst_dir: Path,
    out_format: str,
    quality: int | None = None,
    max_side: int | None = None,
) -> Path:
    data = convert_bytes(src.read_bytes(), out_format, quality=quality, max_side=max_side)
    dst = dst_dir / (src.stem + "." + output_ext(out_format))
    dst.write_bytes(data)
    return dst
