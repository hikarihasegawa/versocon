"""Pulizia scansioni (foto di documenti e PDF scansionati) con OpenCV headless.

Operazioni: raddrizza (deskew), correggi illuminazione/ombre (antishadow),
bianco/nero adattivo, ritaglio prospettico da 4 punti. Il motore è opzionale:
se OpenCV non è importabile ``available()`` è False e le funzioni sollevano
``ScanEngineMissingError`` (l'app parte comunque).
"""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from .report import check_cancelled, report

try:  # motore opzionale: senza OpenCV la funzione «Scansione» resta spenta
    import cv2
    import numpy as np

    _CV_AVAILABLE = True
except Exception:  # noqa: BLE001 - qualunque errore di import = motore assente
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    _CV_AVAILABLE = False

try:  # HEIC/HEIF: stesso opener di images.py (best-effort)
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # noqa: BLE001 - senza pillow-heif gli HEIC non si aprono, il resto sì
    pass

# ── limiti ──
SCAN_IN_EXT = {
    ".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp",
    ".bmp", ".tif", ".tiff", ".gif", ".pdf",
}
MAX_PAGES = 300
MAX_ANGLE = 15.0


class ScanEngineMissingError(Exception):
    """Sollevato quando OpenCV non è importabile in questo processo."""


def available() -> bool:
    """True se il motore OpenCV è importabile (funzione «Scansione» attiva)."""
    return _CV_AVAILABLE


def engine_info() -> dict:
    """Stato del motore per la UI: disponibilità e versione OpenCV."""
    return {"available": bool(_CV_AVAILABLE), "version": cv2.__version__ if _CV_AVAILABLE else None}


def is_scan_input(filename: str) -> bool:
    """True se il file è accettato in input (immagine comune/HEIC o PDF)."""
    return Path(filename).suffix.lower() in SCAN_IN_EXT


def output_ext(fmt: str) -> str:
    """Estensione di output per un formato immagine richiesto (png/jpg)."""
    f = (fmt or "png").lower().lstrip(".")
    if f in ("jpg", "jpeg"):
        return ".jpg"
    if f == "png":
        return ".png"
    raise ValueError(f"formato immagine non supportato: {fmt}")


def _require() -> None:
    if not _CV_AVAILABLE:
        raise ScanEngineMissingError("OpenCV (opencv-python-headless) non disponibile")


def _gray(bgr):
    """Canale di luminanza di un'immagine BGR (no-op se già a un canale)."""
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr


def decode_image(data: bytes):
    """Decodifica un'immagine applicando l'EXIF (HEIC incluso) → array BGR."""
    _require()
    with Image.open(io.BytesIO(data)) as im:
        rgb = ImageOps.exif_transpose(im).convert("RGB")
        arr = np.asarray(rgb)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def encode_image(bgr, fmt: str = "png", quality: int = 85) -> bytes:
    """Codifica un'array BGR in PNG (lossless) o JPEG."""
    _require()
    if output_ext(fmt) == ".jpg":
        ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), max(1, min(100, int(quality)))])
    else:
        ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise ValueError("codifica immagine non riuscita")
    return buf.tobytes()


def parse_corners(raw) -> list[list[float]] | None:
    """Valida 4 punti [x,y] in percentuale 0–100 (ordine TL,TR,BR,BL); None se vuoto."""
    if raw in (None, ""):
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise ValueError("servono 4 punti [x,y] in percentuale")
    out: list[list[float]] = []
    for p in raw:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError("ogni punto deve essere [x,y]")
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError) as e:
            raise ValueError("coordinate non numeriche") from e
        if not (0.0 <= x <= 100.0 and 0.0 <= y <= 100.0):
            raise ValueError("coordinate fuori dall'intervallo 0–100")
        out.append([x, y])
    return out


def estimate_skew(bgr, max_angle: float = MAX_ANGLE) -> float:
    """Inclinazione del contenuto in gradi: rotazione di correzione da applicare.

    Valore in ``(-max_angle, max_angle]``; 0.0 se non stimabile (poco inchiostro)
    o se oltre ``max_angle`` (probabile pagina ruotata di 90°).
    """
    _require()
    gray = _gray(bgr)
    _, binv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    pts = cv2.findNonZero(binv)
    if pts is None or len(pts) < 200:
        return 0.0
    ang = cv2.minAreaRect(pts)[2] % 90.0
    if ang > 45.0:
        ang -= 90.0
    return ang if abs(ang) <= max_angle else 0.0


def deskew(bgr, max_angle: float = MAX_ANGLE):
    """Raddrizza l'immagine; ritorna ``(immagine, angolo applicato)``."""
    _require()
    ang = estimate_skew(bgr, max_angle)
    if ang == 0.0:
        return bgr, 0.0
    h, w = bgr.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), ang, 1.0)
    border = (255, 255, 255) if bgr.ndim == 3 else 255
    out = cv2.warpAffine(
        bgr, m, (w, h), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=border,
    )
    return out, ang


def remove_shadow(bgr):
    """Normalizza l'illuminazione: divide per lo sfondo stimato (ombre/alone)."""
    _require()
    h, w = bgr.shape[:2]
    k = max(15, (min(h, w) // 25) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    bg = cv2.morphologyEx(bgr, cv2.MORPH_CLOSE, kernel)
    bg = cv2.max(bg, 1)
    return cv2.divide(bgr, bg, scale=255)


def binarize(bgr, block_size: int = 0, c: int = 10):
    """Bianco/nero adattivo (soglia gaussiana): testo nero su sfondo bianco."""
    _require()
    h, w = bgr.shape[:2]
    gray = cv2.medianBlur(_gray(bgr), 3)
    block = block_size or max(15, (min(h, w) // 40) | 1)
    block = max(15, min(255, block | 1))
    out = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, c
    )
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR) if bgr.ndim == 3 else out


def crop_perspective(bgr, corners):
    """Ritaglio prospettico: ``corners`` = 4 punti % (TL,TR,BR,BL) → rettangolo."""
    _require()
    pts = parse_corners(corners)
    if pts is None:
        return bgr
    h, w = bgr.shape[:2]
    src = np.float32([[x * w / 100.0, y * h / 100.0] for x, y in pts])
    if abs(cv2.contourArea(src)) < 0.005 * w * h:
        raise ValueError("area di ritaglio troppo piccola")
    tw = max(np.linalg.norm(src[1] - src[0]), np.linalg.norm(src[2] - src[3]))
    th = max(np.linalg.norm(src[3] - src[0]), np.linalg.norm(src[2] - src[1]))
    if tw < 50 or th < 50:
        raise ValueError("ritaglio troppo piccolo")
    dst = np.float32([[0, 0], [tw - 1, 0], [tw - 1, th - 1], [0, th - 1]])
    m = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(bgr, m, (int(round(tw)), int(round(th))))


def _pipeline(bgr, *, deskew_enabled, antishadow_enabled, binarize_enabled, corners):
    """Applica in ordine: ritaglio → raddrizza → antishadow → bianco/nero."""
    if corners is not None:
        bgr = crop_perspective(bgr, corners)
    if deskew_enabled:
        bgr, _ = deskew(bgr)
    if antishadow_enabled:
        bgr = remove_shadow(bgr)
    if binarize_enabled:
        bgr = binarize(bgr)
    return bgr


def clean_bytes(
    data: bytes,
    *,
    deskew: bool = True,
    antishadow: bool = False,
    binarize: bool = False,
    corners=None,
    fmt: str = "png",
    quality: int = 85,
    cancel=None,
) -> bytes:
    """Pulisce un'immagine (EXIF/HEIC inclusi) e la ricodifica in PNG o JPEG."""
    _require()
    check_cancelled(cancel)
    img = decode_image(data)
    out = _pipeline(
        img,
        deskew_enabled=deskew,
        antishadow_enabled=antishadow,
        binarize_enabled=binarize,
        corners=corners,
    )
    return encode_image(out, fmt, quality)


def clean_pdf(
    data: bytes,
    *,
    deskew: bool = True,
    antishadow: bool = False,
    binarize: bool = False,
    corners=None,
    dpi: int = 200,
    progress=None,
    cancel=None,
) -> bytes:
    """Pulisce un PDF scansionato: ogni pagina è rasterizzata, pulita e ricomposta.

    Le pagine restano della stessa dimensione; il testo diventa un'immagine.
    ``corners`` (percentuali) si applica a ogni pagina. ``progress``/``cancel``
    opzionali: avanzamento per pagina e annullo tra una pagina e l'altra.
    """
    _require()
    zoom = max(0.5, min(6.0, (dpi or 200) / 72.0))
    mat = pymupdf.Matrix(zoom, zoom)
    src = pymupdf.open(stream=data, filetype="pdf")
    try:
        if src.page_count > MAX_PAGES:
            raise ValueError(f"troppe pagine: {src.page_count} (max {MAX_PAGES})")
        report(progress, 0, src.page_count, "pages")
        out = pymupdf.open()
        try:
            for i, page in enumerate(src):
                check_cancelled(cancel)
                pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=pymupdf.csRGB)
                arr = np.frombuffer(pix.samples, dtype=np.uint8)
                arr = arr.reshape(pix.height, pix.stride)[:, : pix.width * 3]
                bgr = cv2.cvtColor(arr.reshape(pix.height, pix.width, 3), cv2.COLOR_RGB2BGR)
                bgr = _pipeline(
                    bgr,
                    deskew_enabled=deskew,
                    antishadow_enabled=antishadow,
                    binarize_enabled=binarize,
                    corners=corners,
                )
                new = out.new_page(width=page.rect.width, height=page.rect.height)
                new.insert_image(new.rect, stream=encode_image(bgr, "png"))
                report(progress, i + 1, src.page_count, "pages")
            return out.tobytes()
        finally:
            out.close()
    finally:
        src.close()
