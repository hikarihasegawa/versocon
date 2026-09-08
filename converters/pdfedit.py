"""Editor PDF: azioni su file PDF tramite pymupdf (già dipendenza).

Tutte le funzioni prendono `bytes` del PDF in ingresso e ritornano `bytes`
del PDF modificato. Le pagine sono INDICIZZATE A PARTIRE DA 1 (come l'utente
le vede in un PDF reader).

Azioni:
- reorder_pages(data, order)          → riordina/sposta pagine
- delete_pages(data, pages)           → elimina pagine
- rotate_pages(data, pages, angle)    → ruota pagine (0/90/180/270, cumulativo)
- watermark_text(data, text, ...)      → watermark di testo su tutte le pagine
- add_signature(data, img, page, ...) → firma in immagine su una pagina

Zero dipendenze nuove (solo pymupdf). Erri in modo esplicito con ValueError
su input non validi (PDF vuoto/invalido, pagina fuori range, angolo non valido).
"""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image

MAX_PAGES = 500
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB per immagine (firma)
_ROT_VALUES = {0, 90, 180, 270}
_WATERMARK_CORNERS = {"tl", "tr", "bl", "br", "center"}


def _open(data: bytes) -> "pymupdf.Document":
    if not data:
        raise ValueError("PDF vuoto")
    try:
        doc = pymupdf.Document(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"PDF non valido: {e}")
    if doc.page_count > MAX_PAGES:
        raise ValueError(f"PDF con {doc.page_count} pagine (max {MAX_PAGES} supportate)")
    return doc


def _save(doc: "pymupdf.Document") -> bytes:
    doc.save(buf := io.BytesIO(), garbage=3, deflate=True)
    return buf.getvalue()


def page_count(data: bytes) -> int:
    """Numero di pagine di `data` (validazione inclusa)."""
    doc = _open(data)
    n = doc.page_count
    doc.close()
    return n


def _norm_page(page: int, n: int, field: str = "page") -> int:
    try:
        p = int(page)
    except (TypeError, ValueError):
        raise ValueError(f"{field} non valido: {page!r} (attesi interi 1..{n})")
    if p < 1 or p > n:
        raise ValueError(f"{field} fuori range: {p} (attesi 1..{n})")
    return p


def _norm_list(pages, n: int, field: str = "pages") -> list[int]:
    """Normalizza una lista di numeri pagina 1-based in una lista 0-based."""
    if isinstance(pages, int):
        pages = [pages]
    out: list[int] = []
    for p in pages:
        try:
            ip = int(p)
        except (TypeError, ValueError):
            raise ValueError(f"{field} contiene un valore non valido: {p!r}")
        if ip < 1 or ip > n:
            raise ValueError(f"{field} contiene {ip} fuori range (attesi 1..{n})")
        out.append(ip - 1)
    return out


def reorder_pages(data: bytes, order: list[int]) -> bytes:
    """Riordina le pagine. `order` = permutazione 1-based delle N pagine,
    nella NUOVA sequenza. Esempio per 3 pagine: [3,1,2] → pagina3, pagina1, pagina2."""
    doc = _open(data)
    n = doc.page_count
    if not isinstance(order, (list, tuple)):
        raise ValueError("order deve essere una lista di numeri pagina 1..N")
    try:
        norm_order = [int(p) for p in order]
    except (TypeError, ValueError):
        raise ValueError(f"order contiene un valore non valido: {order!r}")
    if sorted(norm_order) != list(range(1, n + 1)):
        raise ValueError(f"order deve essere una permutazione di 1..{n} (ricevuto {order})")
    ordered = pymupdf.Document()
    for idx in order:
        ordered.insert_pdf(doc, from_page=int(idx) - 1, to_page=int(idx) - 1)
    doc.close()
    return _save(ordered)


def delete_pages(data: bytes, pages) -> bytes:
    """Elimina le pagine indicate (1-based). `pages` int o lista di int."""
    doc = _open(data)
    n = doc.page_count
    to_delete = set(_norm_list(pages, n))
    if not to_delete:
        return data
    if len(to_delete) >= n:
        raise ValueError("Non puoi eliminare tutte le pagine del PDF")
    remaining = [i for i in range(n) if i not in to_delete]
    ordered = pymupdf.Document()
    for idx in remaining:
        ordered.insert_pdf(doc, from_page=idx, to_page=idx)
    result = _save(ordered)
    doc.close()
    return result


def rotate_pages(data: bytes, pages, angle: int = 90) -> bytes:
    """Ruota le pagine indicate (1-based) di `angle` gradi (0/90/180/270, CW).
    `pages` int o lista di int; angle è cumulativo rispetto alla rotazione attuale."""
    doc = _open(data)
    try:
        a = int(angle)
    except (TypeError, ValueError):
        raise ValueError(f"Rotazione non valida: {angle!r} (attesi 0/90/180/270)")
    if a not in _ROT_VALUES:
        raise ValueError(f"Rotazione non valida: {angle} (permesse 0/90/180/270)")
    if a == 0:
        return data
    n = doc.page_count
    targets = set(_norm_list(pages, n))
    for i in range(n):
        if i in targets:
            page = doc[i]
            page.set_rotation((page.rotation + a) % 360)
    out = _save(doc)
    return out


def watermark_text(
    data: bytes,
    text: str,
    corner: str = "br",
    font_size: int = 48,
    opacity: float = 0.2,
    color=(0.4, 0.4, 0.4),
    rotate: int = 0,
) -> bytes:
    """Applica un watermark di testo su OGNI pagina.
    corner ∈ {tl,tr,bl,br,center}; font_size pt; opacity 0..1; rotate ∈ {0,90,180,−90}."""
    if not (text or "").strip():
        raise ValueError("Testo watermark vuoto")
    if corner not in _WATERMARK_CORNERS:
        raise ValueError(f"Angolo watermark non valido: {corner!r}")
    if int(rotate) not in {0, 90, 180, -90}:
        raise ValueError(f"Rotation watermark: {rotate!r} non supportata (attesi 0/90/180/−90)")
    op = max(0.0, min(1.0, float(opacity)))
    fs = max(8, min(240, int(font_size)))
    doc = _open(data)
    for i in range(doc.page_count):
        page = doc[i]
        r = page.rect
        fs2 = fs * (r.width / 595.0) if r.width else fs  # scala con larghezza
        fs2 = max(10, min(300, fs2))
        line = text
        # posiziona il testo
        w = page.rect.width
        h = page.rect.height
        margin = fs2 * 0.6
        est = len(line) * fs2 * 0.5  # stima larghezza testo
        if corner == "tl":
            pos = (margin, h - margin)
        elif corner == "tr":
            pos = (max(margin, w - est - margin), h - margin)
        elif corner == "bl":
            pos = (margin, margin)
        elif corner == "br":
            pos = (max(margin, w - est - margin), margin)
        else:  # center
            pos = (max(margin, (w - est) / 2), (h - fs2) / 2)
        page.insert_text(
            pymupdf.Point(*pos),
            line,
            fontsize=fs2,
            color=color,
            fill_opacity=op,
            rotate=int(rotate),
            overlay=True,
        )
    return _save(doc)


def add_signature(
    data: bytes,
    signature_image: bytes,
    page: int = 1,
    corner: str = "bl",
    width: float = 2.0,
) -> bytes:
    """Aggiunge una firma in immagine su una pagina (1-based).
    `width` = larghezza in POLLCI della firma (default 2in); corner ∈ angoli."""
    if not signature_image:
        raise ValueError("Immagine firma vuota")
    if len(signature_image) > MAX_IMAGE_BYTES:
        raise ValueError("Immagine firma supera i 20 MB")
    # normalizza in PNG se serve (PIL)
    try:
        im = Image.open(io.BytesIO(signature_image))
        im.load()
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Immagine firma non valida: {e}")
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    png = buf.getvalue()
    if corner not in _WATERMARK_CORNERS:
        raise ValueError(f"Posizione firma non valida: {corner!r}")
    doc = _open(data)
    n = doc.page_count
    p = _norm_page(page, n, "page")
    pg = doc[p - 1]
    r = pg.rect
    w_in = max(0.3, min(20.0, float(width)))
    w_pt = w_in * 72
    aspect = im.height / im.width if im.width else 1
    h_pt = w_pt * aspect
    margin = 24
    if corner == "tl":
        rect = pymupdf.Rect(margin, r.height - h_pt - margin, margin + w_pt, r.height - margin)
    elif corner == "tr":
        rect = pymupdf.Rect(r.width - w_pt - margin, r.height - h_pt - margin, r.width - margin, r.height - margin)
    elif corner == "bl":
        rect = pymupdf.Rect(margin, margin, margin + w_pt, margin + h_pt)
    elif corner == "br":
        rect = pymupdf.Rect(r.width - w_pt - margin, margin, r.width - margin, margin + h_pt)
    else:  # center
        cx, cy = (r.width - w_pt) / 2, (r.height - h_pt) / 2
        rect = pymupdf.Rect(cx, cy, cx + w_pt, cy + h_pt)
    pg.insert_image(rect, stream=png, keep_proportion=True)
    return _save(doc)


def _clamp(v: float, lo: float, hi: float) -> float:
    v = float(v)
    return max(lo, min(hi, v))


def _to_rgba(image: bytes) -> Image.Image:
    """Normalizza `image` in RGBA validato (solleva ValueError se non è immagine)."""
    if not image:
        raise ValueError("Immagine firma vuota")
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("Immagine firma supera i 20 MB")
    try:
        im = Image.open(io.BytesIO(image))
        im.load()
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Immagine firma non valida: {e}")
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    return im


def place_signature(
    data: bytes,
    image: bytes,
    page: int = 1,
    x_pct: float = 50.0,
    y_pct: float = 85.0,
    width_pct: float = 30.0,
    rotation: float = 0.0,
    opacity: float = 100.0,
) -> bytes:
    """Posiziona liberamente la `image` (PNG) su una pagina del PDF.

    - `x_pct` / `y_pct`: centro della firma in % (50,50 = centro pagina; y cresce verso il basso).
    - `width_pct`: larghezza in % della larghezza pagina (la altezza segue l'aspetto).
    - `rotation`: grado (0-359), applicata alla firma.
    - `opacity`: 0-100 (burrata nell'alpha del PNG → trasparenza uniforme).
    """
    im = _to_rgba(image)
    opacity = _clamp(opacity, 0, 100)
    rotation = float(int(rotation)) % 360.0
    x_pct = _clamp(x_pct, 0, 100)
    y_pct = _clamp(y_pct, 0, 100)
    width_pct = _clamp(width_pct, 1, 100)

    if opacity < 100:
        a = im.getchannel("A").point(lambda p: int(p * opacity / 100))
        im.putalpha(a)
    if rotation:
        # rotazione anti-oraria con canvas espansa; mantengo trasparenza del bordo
        im = im.rotate(rotation, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0, 0))

    buf = io.BytesIO()
    im.save(buf, format="PNG")
    png = buf.getvalue()

    doc = _open(data)
    n = doc.page_count
    p = _norm_page(page, n, "page")
    pg = doc[p - 1]
    r = pg.rect
    w_pt = r.width * width_pct / 100.0
    aspect = im.height / im.width if im.width else 1
    h_pt = w_pt * aspect
    cx = r.width * x_pct / 100.0
    cy = r.height * y_pct / 100.0
    rect = pymupdf.Rect(cx - w_pt / 2, cy - h_pt / 2, cx + w_pt / 2, cy + h_pt / 2)
    pg.insert_image(rect, stream=png, keep_proportion=True)
    return _save(doc)
