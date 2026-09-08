"""Firma calligrafica da testo: genera un PNG a fondo trasparente
a partire da nome + stile font.

Font disponibili (bundle in `assets/fonts/`, tutti OFL — open licence):
- "caveat"      → Caveat (casual, leggermente inclinata)
- "dancing"     → DancingScript (decorativa, elegante)
- "greatvibes"  → GreatVibes (scritta fine, "autograppata")
- "pacifico"    → Pacifico (large, moderna)

Zero dipendenze nuove: solo Pillow (già dipendenza del progetto).
Entry-point: `generate()` + `list_styles()` per la GUI.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"

# key → (file, label umano)
_STYLES: "dict[str, tuple[str, str]]" = {
    "caveat":     ("Caveat.ttf",              "Caveat (casual)"),
    "dancing":    ("DancingScript.ttf",       "Dancing (elegante)"),
    "greatvibes": ("GreatVibes-Regular.ttf",  "Great Vibes (fine)"),
    "pacifico":   ("Pacifico-Regular.ttf",    "Pacifico (moderna)"),
}

_ORDER = ("caveat", "dancing", "greatvibes", "pacifico")

_HEIGHT_PX = 120
_PAD_PX = 24


def _hex_to_rgba(hexcolor: str) -> tuple[int, int, int, int]:
    h = (hexcolor or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Colore inchiostro non valido: {hexcolor!r} (usa es. #1a1a2e)")
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 236)
    except ValueError:
        raise ValueError(f"Colore inchiostro non valido: {hexcolor!r} (usa es. #1a1a2e)") from None


@dataclass(frozen=True)
class Style:
    key: str
    file: str
    label: str


def _styles_map() -> "dict[str, Style]":
    return {k: Style(k, f, lab) for k, (f, lab) in _STYLES.items()}


def list_styles() -> "list[Style]":
    """Stili disponibili (ordine stabile)."""
    return [_styles_map()[k] for k in _ORDER]


def _font_path(key: str) -> Path:
    st = _styles_map().get(key)
    if not st:
        raise ValueError(f"Stile firma non valido: {key!r} (valori: {', '.join(_styles_map())})")
    p = FONTS_DIR / st.file
    if not p.exists():
        raise ValueError(f"Font non trovato in bundle: {p.name} (assets/fonts/)")
    return p


def _measure(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    """Dimensioni in pixel del `text` disegnato con `font` (getbbox, agganciato
    a ogni versione di Pillow — in 10.x `getsize` è stato rimosso)."""
    l, t, r, b = font.getbbox(text)
    return (r - l), (b - t)


def _fit_font(path: Path, text: str, target_h: int) -> ImageFont.FreeTypeFont:
    """Scelte la size del font così che l'altezza del testo ~= target_h."""
    lo, hi = 200, 3200
    best: ImageFont.FreeTypeFont | None = None
    for _ in range(8):
        mid = (lo + hi) // 2
        f = ImageFont.truetype(str(path), mid)
        _w, h = _measure(f, text)
        if h <= target_h:
            lo = mid + 1
            best = f
        else:
            hi = mid - 1
        if hi - lo <= 4:
            break
    if best is None:
        best = ImageFont.truetype(str(path), max(lo, 200))
    return best


def generate(
    name: str,
    style: str = "caveat",
    height: int = _HEIGHT_PX,
    color: str = "#000000",
) -> bytes:
    """Genera un PNG (trasparente) con `name` firmato in stile `style`.

    `color` è l'inchiostro hex (#rrggbb; default nero `#000000`).
    Ritorna i `bytes` del PNG. Altezza approssimativa = `height` (px).
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Nome firmato vuoto")
    if len(name) > 240:
        raise ValueError("Nome troppo lungo (max 240 char)")
    height = int(max(20, min(2048, height or _HEIGHT_PX)))
    ink = _hex_to_rgba(color)

    path = _font_path(style)
    font = _fit_font(path, name, height)
    w, h = _measure(font, name)

    canvas_w = min(w + 2 * _PAD_PX + 24, 8000)
    canvas_h = min(h + 2 * _PAD_PX + 24, 8000)
    img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    x = (canvas_w - w) // 2
    y = (canvas_h - h) // 2
    draw.text((x, y), name, font=font, fill=ink)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
