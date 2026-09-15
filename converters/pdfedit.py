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

Editor v2 (annotazioni e operazioni documento):
- annotate_text(...)                  → evidenzia/sottolinea/barrato/ondulato su testo cercato
- add_note(...)                       → nota a fumetto
- add_ink(...)                        → tratti a penna libera (percentuali pagina)
- add_stamp(...)                      → timbro di testo ruotabile
- add_text(...)                       → testo libero
- redact(...)                         → redazione vera (testo cercato o rettangoli)
- find_replace(...)                   → trova&sostituisci con stile originale
- number_pages(...)                   → numerazione/Bates
- header_footer(...)                  → intestazione/piè di pagina ({page}/{pages}/{date})
- insert_blank_page(...)              → inserisci pagine bianche
- extract_pages(...)                  → estrai pagine in un nuovo PDF
- form_fields(...) / fill_form(...)   → elenca e compila campi modulo

Sicurezza:
- is_protected(data)                  → True se il PDF richiede una password
- protect(data, pw, ...)              → cifra in AES-256 (password apertura/modifica)
- unprotect(data, pw)                 → rimuove la password (no-op se non protetto)

Anteprima:
- render_page_png(data, page, dpi)    → PNG di una pagina (anteprima live, nessun file scritto)

Zero dipendenze nuove (solo pymupdf). Erri in modo esplicito con ValueError
su input non validi (PDF vuoto/invalido, pagina fuori range, angolo non valido).
"""
from __future__ import annotations

import io
import math
import secrets
from pathlib import Path

import pymupdf
from PIL import Image

MAX_PAGES = 500
MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB per immagine (firma)
MAX_PREVIEW_PIXELS = 40_000_000  # tetto di sicurezza per il rendering anteprima
_PREVIEW_DPI_MIN, _PREVIEW_DPI_MAX = 30, 300
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


def render_page_png(
    data: bytes, page: int = 1, dpi: int = 110, password: str = ""
) -> tuple[bytes, int, int]:
    """Rende una pagina del PDF come PNG (anteprima live, nessun file scritto).

    Ritorna `(png, pagina_usata, pagine_totali)`. `page` (1-based) è limitata
    all'ultima pagina; `dpi` ∈ [30, 300] e viene ridotto se la pagina supera
    `MAX_PREVIEW_PIXELS`. `password` serve per i PDF cifrati (es. risultato di
    `protect`)."""
    doc = _open(data)
    try:
        p = int(page)
    except (TypeError, ValueError):
        raise ValueError(f"page non valido: {page!r} (attesi interi 1..N)")
    try:
        d = int(dpi)
    except (TypeError, ValueError):
        raise ValueError(f"dpi non valido: {dpi!r} (attesi {_PREVIEW_DPI_MIN}..{_PREVIEW_DPI_MAX})")
    if d < _PREVIEW_DPI_MIN or d > _PREVIEW_DPI_MAX:
        raise ValueError(f"dpi fuori range: {d} (attesi {_PREVIEW_DPI_MIN}..{_PREVIEW_DPI_MAX})")
    try:
        if doc.needs_pass and not doc.authenticate(password or ""):
            raise ValueError("PDF protetto: password mancante o errata")
        n = doc.page_count
        used = max(1, min(p, n))
        pg = doc[used - 1]
        w_pt, h_pt = pg.rect.width, pg.rect.height
        scale = d / 72.0
        if w_pt and h_pt and w_pt * h_pt * scale * scale > MAX_PREVIEW_PIXELS:
            scale = (MAX_PREVIEW_PIXELS / (w_pt * h_pt)) ** 0.5
            # il pixmap arrotonda per eccesso: stringi finché il prodotto
            # delle dimensioni intere rientra nel tetto (garanzia, non stima)
            while math.ceil(w_pt * scale) * math.ceil(h_pt * scale) > MAX_PREVIEW_PIXELS:
                scale *= 0.995
        pix = pg.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png"), used, n
    finally:
        doc.close()


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


# ---------------------------------------------------------------------------
# Editor v2 — annotazioni, testo, redazione, testo cercato, pagine, moduli
# ---------------------------------------------------------------------------
_ANNOT_KINDS = {"highlight", "underline", "strikeout", "squiggly"}
_ANNOT_DEFAULT_COLOR = {
    "highlight": "#ffd400",
    "underline": "#e2382c",
    "strikeout": "#e2382c",
    "squiggly": "#e2382c",
}
_NOTE_ICONS = {"Note", "Comment", "Help", "Insert", "Key", "Star"}
_BASE14 = {
    "helv", "heit", "hebo", "hebi", "cour", "coit", "cobo", "cobi",
    "tiro", "tiit", "tibo", "tibi", "symb", "zadb",
}
_POS_ALIGN = {
    "tl": (0.0, "top"), "tc": (0.5, "top"), "tr": (1.0, "top"),
    "bl": (0.0, "bottom"), "bc": (0.5, "bottom"), "br": (1.0, "bottom"),
}


def _rgb(value, field: str = "colore") -> tuple[float, float, float]:
    """Converte '#rgb'/'#rrggbb' (o triple 0..1) in tupla RGB 0..1 validata."""
    if isinstance(value, (tuple, list)) and len(value) == 3:
        vals = [float(v) for v in value]
        if all(0.0 <= v <= 1.0 for v in vals):
            return vals[0], vals[1], vals[2]
        return tuple(max(0, min(255, int(v))) / 255 for v in vals)  # type: ignore[return-value]
    s = str(value or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"{field} non valido: {value!r} (atteso #rrggbb)")
    try:
        n = int(s, 16)
    except ValueError:
        raise ValueError(f"{field} non valido: {value!r} (atteso #rrggbb)")
    return ((n >> 16) & 255) / 255.0, ((n >> 8) & 255) / 255.0, (n & 255) / 255.0


def _point_pct(page: "pymupdf.Page", x_pct: float, y_pct: float) -> "pymupdf.Point":
    """Punto in % (origine alto-sinistra, come in UI) → coordinate PyMuPDF."""
    r = page.rect
    return pymupdf.Point(
        _clamp(x_pct, 0, 100) / 100.0 * r.width,
        _clamp(y_pct, 0, 100) / 100.0 * r.height,
    )


def _rect_pct(page: "pymupdf.Page", x_pct: float, y_pct: float,
              w_pct: float, h_pct: float) -> "pymupdf.Rect":
    """Rettangolo in % pagina (x,y = alto-sinistra, come in UI) → Rect."""
    r = page.rect
    x = _clamp(x_pct, 0, 100) / 100.0 * r.width
    y = _clamp(y_pct, 0, 100) / 100.0 * r.height
    w = _clamp(w_pct, 0.5, 100) / 100.0 * r.width
    h = _clamp(h_pct, 0.5, 100) / 100.0 * r.height
    return pymupdf.Rect(x, y, min(r.width, x + w), min(r.height, y + h))


def _base14(fontname: str) -> str:
    """Mappa il nome font di uno span (es. Helvetica-Bold) su un base14 pymupdf."""
    f = (fontname or "").lower()
    if f in _BASE14:
        return f
    bold = "bold" in f
    italic = "italic" in f or "oblique" in f
    if "mono" in f or "courier" in f:
        return "cobi" if bold and italic else "cobo" if bold else "coit" if italic else "cour"
    if "times" in f or "serif" in f or "tiro" in f or "georgia" in f:
        return "tibi" if bold and italic else "tibo" if bold else "tiit" if italic else "tiro"
    return "hebi" if bold and italic else "hebo" if bold else "heit" if italic else "helv"


def _style_at(page: "pymupdf.Page", rect: "pymupdf.Rect"):
    """(font base14, size, colore RGB, origine baseline, direzione) dello span che copre `rect`."""
    fallback = ("helv", 11.0, (0.0, 0.0, 0.0), pymupdf.Point(rect.x0, rect.y1), (1.0, 0.0))
    try:
        info = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return fallback
    center = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
    for block in info.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                bbox = pymupdf.Rect(span.get("bbox", (0, 0, 0, 0)))
                if bbox.contains(center) or bbox.intersects(rect):
                    c = int(span.get("color", 0))
                    origin = span.get("origin") or (rect.x0, rect.y1)
                    direction = tuple(line.get("dir") or (1.0, 0.0))
                    return (
                        _base14(span.get("font", "")),
                        max(4.0, min(200.0, float(span.get("size", 11)))),
                        (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0),
                        pymupdf.Point(origin),
                        (float(direction[0]), float(direction[1])),
                    )
    return fallback


def _match_origin(rect: "pymupdf.Rect", span_origin: "pymupdf.Point",
                  direction: tuple[float, float]) -> "pymupdf.Point":
    """Origine del match: coordinata lungo la scrittura dal rettangolo trovato,
    coordinata perpendicolare (baseline) dallo span.

    Serve perché una span può contenere più parole: l'origine della span è
    l'inizio della riga, non della parola cercata.
    """
    dx, dy = (direction or (1.0, 0.0))[:2]
    if abs(dx) >= abs(dy):
        return pymupdf.Point(rect.x0 if dx >= 0 else rect.x1, span_origin.y)
    return pymupdf.Point(span_origin.x, rect.y1 if dy < 0 else rect.y0)


def _rotate_for(direction: tuple[float, float]) -> int:
    """Rotazione CCW (0/90/180/270) da usare in `insert_text` per la direzione data."""
    dx, dy = (direction or (1.0, 0.0))[:2]
    if abs(dx) >= abs(dy):
        return 0 if dx >= 0 else 180
    return 90 if dy < 0 else 270


def _insert_replacement(pg: "pymupdf.Page", rect: "pymupdf.Rect", text: str,
                        font: str, size: float, color, origin: "pymupdf.Point",
                        direction: tuple[float, float]) -> None:
    """Inserisce `text` alla posizione originale mantenendone la direzione.

    Testo orizzontale: inserimento diretto se ci sta, altrimenti textbox che
    rimpicciolisce. Testo ruotato: `insert_text(rotate=...)`, riducendo il
    corpo quanto basta a restare dentro la pagina.
    """
    rot = _rotate_for(direction)
    width = pymupdf.get_text_length(text, fontname=font, fontsize=size)
    if rot == 0:
        if "\n" not in text and width <= pg.rect.width - origin.x - 4:
            pg.insert_text(origin, text, fontsize=size, fontname=font, color=color)
            return
        fs = size
        while fs >= 4.0:
            if pg.insert_textbox(rect, text, fontsize=fs, fontname=font,
                                 color=color, align=0) >= 0:
                return
            fs *= 0.85
        pg.insert_text((rect.x0, rect.y1 - 0.5), text,
                       fontsize=max(4.0, size / 2), fontname=font, color=color)
        return

    if rot == 90:      # dal basso verso l'alto: spazio fino al bordo alto
        avail = origin.y - pg.rect.y0
    elif rot == 270:   # dall'alto verso il basso
        avail = pg.rect.y1 - origin.y
    else:              # 180: verso sinistra
        avail = origin.x - pg.rect.x0
    fs = size
    while "\n" in text or width > avail - 4:
        if fs <= 4.0:
            break
        fs *= 0.85
        width = pymupdf.get_text_length(text, fontname=font, fontsize=fs)
    pg.insert_text(origin, text, fontsize=max(4.0, fs), fontname=font,
                   color=color, rotate=rot)


def annotate_text(data: bytes, page: int, needle: str, kind: str = "highlight",
                  color: str = "", opacity: float = 0.35) -> bytes:
    """Annota TUTTE le occorrenze di `needle` sulla pagina (1-based).

    `kind` ∈ {highlight,underline,strikeout,squiggly}; `color` '#rrggbb'
    (default per tipo); `opacity` 0.05..1.0.
    """
    kind = (kind or "").strip().lower()
    if kind not in _ANNOT_KINDS:
        raise ValueError(f"Tipo annotazione non valido: {kind!r} (attesi {sorted(_ANNOT_KINDS)})")
    if not (needle or "").strip():
        raise ValueError("Testo da annotare vuoto")
    doc = _open(data)
    p = _norm_page(page, doc.page_count)
    pg = doc[p - 1]
    rects = pg.search_for(needle)
    if not rects:
        raise ValueError(f"Testo non trovato: {needle!r}")
    add = {
        "highlight": pg.add_highlight_annot,
        "underline": pg.add_underline_annot,
        "strikeout": pg.add_strikeout_annot,
        "squiggly": pg.add_squiggly_annot,
    }[kind]
    annot = add(quads=rects)
    annot.set_colors(stroke=_rgb(color or _ANNOT_DEFAULT_COLOR[kind]))
    annot.set_opacity(_clamp(opacity, 0.05, 1.0))
    annot.update()
    return _save(doc)


def add_note(data: bytes, page: int, x_pct: float, y_pct: float, text: str,
             icon: str = "Note", color: str = "#e2382c") -> bytes:
    """Aggiunge una nota a fumetto nel punto (x_pct, y_pct) della pagina."""
    if not (text or "").strip():
        raise ValueError("Testo nota vuoto")
    if icon not in _NOTE_ICONS:
        raise ValueError(f"Icona nota non valida: {icon!r} (attese {sorted(_NOTE_ICONS)})")
    doc = _open(data)
    p = _norm_page(page, doc.page_count)
    pg = doc[p - 1]
    annot = pg.add_text_annot(_point_pct(pg, x_pct, y_pct), text, icon=icon)
    annot.set_colors(stroke=_rgb(color))
    annot.set_info(content=text)
    annot.update()
    return _save(doc)


def add_ink(data: bytes, page: int, strokes, color: str = "#e2382c", width: float = 2.0) -> bytes:
    """Disegna tratti a penna. `strokes` = lista di tratti, ognuno lista di [x_pct,y_pct]."""
    if not isinstance(strokes, (list, tuple)) or not strokes:
        raise ValueError("Nessun tratto penna da disegnare")
    doc = _open(data)
    p = _norm_page(page, doc.page_count)
    pg = doc[p - 1]
    handwriting = []
    for stroke in strokes:
        if not isinstance(stroke, (list, tuple)) or len(stroke) < 2:
            raise ValueError("Ogni tratto penna richiede almeno 2 punti [x,y]")
        pts = []
        for pt in stroke:
            if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                raise ValueError("Punto penna non valido: atteso [x,y]")
            point = _point_pct(pg, pt[0], pt[1])
            pts.append((point.x, point.y))
        handwriting.append(pts)
    annot = pg.add_ink_annot(handwriting)
    annot.set_colors(stroke=_rgb(color))
    annot.set_border(width=_clamp(width, 0.3, 20.0))
    annot.update()
    return _save(doc)


def add_stamp(data: bytes, page: int, text: str, x_pct: float, y_pct: float,
              w_pct: float = 35.0, h_pct: float = 12.0,
              color: str = "#e2382c", font_size: float = 14.0, rotate: int = 0) -> bytes:
    """Aggiunge un timbro di testo (riquadro bordato) ruotabile di 0/90/180/270."""
    if not (text or "").strip():
        raise ValueError("Testo timbro vuoto")
    try:
        rot = int(rotate)
    except (TypeError, ValueError):
        raise ValueError(f"Rotazione timbro non valida: {rotate!r}")
    if rot not in _ROT_VALUES:
        raise ValueError(f"Rotazione timbro non valida: {rotate} (permesse 0/90/180/270)")
    rgb = _rgb(color)
    doc = _open(data)
    p = _norm_page(page, doc.page_count)
    pg = doc[p - 1]
    rect = _rect_pct(pg, x_pct, y_pct, w_pct, h_pct)
    pg.draw_rect(rect, color=rgb, width=1.2, dashes="[4 2] 0", stroke_opacity=0.75)
    fs = _clamp(font_size, 6, 72)
    while fs >= 4.0:
        if pg.insert_textbox(rect, text, fontsize=fs, fontname="hebo",
                             color=rgb, align=1, rotate=rot) >= 0:
            break
        fs *= 0.85
    return _save(doc)


def add_text(data: bytes, page: int, text: str, x_pct: float, y_pct: float,
             font_size: float = 12.0, color: str = "#141210", font: str = "helv") -> bytes:
    """Inserisce testo libero con angolo alto-sinistra in (x_pct, y_pct).

    Il testo va a capo nella larghezza residua della pagina; se non entra
    nemmeno ridotto, viene inserito su una sola riga.
    """
    if not (text or "").strip():
        raise ValueError("Testo vuoto")
    f = (font or "helv").strip().lower()
    if f not in _BASE14:
        raise ValueError(f"Font non valido: {font!r} (attesi {sorted(_BASE14)})")
    fs = _clamp(font_size, 6, 96)
    rgb = _rgb(color)
    doc = _open(data)
    p = _norm_page(page, doc.page_count)
    pg = doc[p - 1]
    start = _point_pct(pg, x_pct, y_pct)
    rect = pymupdf.Rect(start.x, start.y, pg.rect.width - 12, pg.rect.height - 12)
    if rect.width > 20 and rect.height > 10:
        left = pg.insert_textbox(rect, text, fontsize=fs, fontname=f, color=rgb, align=0)
        if left >= 0:
            return _save(doc)
    pg.insert_text(start, text, fontsize=fs, fontname=f, color=rgb)
    return _save(doc)


def redact(data: bytes, needle: str = "", rects=None, page=None,
           fill: str = "#000000") -> bytes:
    """Redazione VERA (il testo/immagine sotto viene rimosso, non solo coperto).

    Redige tutte le occorrenze di `needle` su tutte le pagine (o su `page`),
    e/o i rettangoli `[x_pct,y_pct,w_pct,h_pct]` indicati (richiedono `page`).
    """
    needle = (needle or "").strip()
    rects = list(rects or [])
    if not needle and not rects:
        raise ValueError("Specifica un testo da redigere o dei rettangoli")
    doc = _open(data)
    n = doc.page_count
    targets = [_norm_page(page, n) - 1] if page is not None else list(range(n))
    if rects and page is None:
        raise ValueError("I rettangoli di redazione richiedono una pagina")
    rgb = _rgb(fill, "colore copertura")
    hits = 0
    for i in targets:
        pg = doc[i]
        if needle:
            for r in pg.search_for(needle):
                pg.add_redact_annot(r, fill=rgb)
                hits += 1
        for rect in rects:
            if not isinstance(rect, (list, tuple)) or len(rect) != 4:
                raise ValueError("Rettangolo di redazione non valido: atteso [x,y,w,h]")
            pg.add_redact_annot(_rect_pct(pg, *rect), fill=rgb)
            hits += 1
    if needle and hits == 0:
        raise ValueError(f"Testo non trovato: {needle!r}")
    for i in targets:
        doc[i].apply_redactions()
    return _save(doc)


def find_replace(data: bytes, needle: str, replacement: str, pages=None,
                 fill: str | None = None) -> bytes:
    """Trova&sostituisci con stile originale; `replacement` vuoto = rimozione.

    Rimuove solo il testo e ne inserisce uno nuovo alla stessa posizione con
    font/size/colore originali: lo sfondo (grafica e immagini della pagina)
    resta intatto. `fill` opzionale dipinge il rettangolo di copertura.
    """
    needle = (needle or "")
    if not needle.strip():
        raise ValueError("Testo da cercare vuoto")
    replacement = replacement or ""
    doc = _open(data)
    n = doc.page_count
    targets = _norm_list(pages, n, "pages") if pages else list(range(n))
    jobs: list[tuple] = []
    for i in targets:
        pg = doc[i]
        for r in pg.search_for(needle):
            rect = pymupdf.Rect(r)
            font, size, color, span_origin, direction = _style_at(pg, rect)
            origin = _match_origin(rect, span_origin, direction)
            jobs.append((i, rect, font, size, color, origin, direction))
    if not jobs:
        raise ValueError(f"Testo non trovato: {needle!r}")
    rgb_fill = _rgb(fill, "colore copertura") if fill else None
    for i, r, _f, _s, _c, _o, _d in jobs:
        doc[i].add_redact_annot(r, fill=rgb_fill)
    for i in targets:
        doc[i].apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        )
    if replacement:
        for i, r, font, size, color, origin, direction in jobs:
            _insert_replacement(doc[i], r, replacement, font, size, color, origin, direction)
    return _save(doc)


def number_pages(data: bytes, start: int = 1, prefix: str = "", suffix: str = "",
                 digits: int = 6, position: str = "br", font_size: float = 10.0,
                 color: str = "#141210", pages=None, margin: int = 24) -> bytes:
    """Numerazione/Bates: `prefix`+numero a `digits` cifre+`suffix` sulle pagine.

    `position` ∈ {tl,tc,tr,bl,bc,br}; il contatore avanza in ordine di pagina
    a partire da `start` (le pagine non selezionate non consumano numeri).
    """
    position = (position or "br").strip().lower()
    if position not in _POS_ALIGN:
        raise ValueError(f"Posizione non valida: {position!r} (attese {sorted(_POS_ALIGN)})")
    try:
        counter = int(start)
        nd = int(digits)
        mg = int(margin)
    except (TypeError, ValueError):
        raise ValueError("start/digits/margin devono essere interi")
    if counter < 0:
        raise ValueError("start non può essere negativo")
    nd = max(1, min(12, nd))
    fs = _clamp(font_size, 6, 72)
    rgb = _rgb(color)
    doc = _open(data)
    n = doc.page_count
    targets = _norm_list(pages, n, "pages") if pages else list(range(n))
    align_x, vertical = _POS_ALIGN[position]
    for i in targets:
        pg = doc[i]
        txt = f"{prefix}{counter:0{nd}d}{suffix}"
        width = pymupdf.get_text_length(txt, fontname="helv", fontsize=fs)
        x = max(2.0, min(align_x * (pg.rect.width - width), pg.rect.width - width - 2.0))
        y = mg + fs if vertical == "top" else pg.rect.height - mg
        pg.insert_text((x, y), txt, fontsize=fs, fontname="helv", color=rgb)
        counter += 1
    return _save(doc)


def header_footer(data: bytes, header: str = "", footer: str = "",
                  position: str = "center", font_size: float = 10.0,
                  color: str = "#141210", pages=None, margin: int = 24,
                  date: str = "") -> bytes:
    """Intestazione/piè di pagina. Placeholder: {page}, {pages}, {date}."""
    if not (header or "").strip() and not (footer or "").strip():
        raise ValueError("Specifica almeno l'intestazione o il piè di pagina")
    position = (position or "center").strip().lower()
    if position not in ("left", "center", "right"):
        raise ValueError(f"Posizione non valida: {position!r} (attese left/center/right)")
    try:
        mg = int(margin)
    except (TypeError, ValueError):
        raise ValueError(f"Margine non valido: {margin!r}")
    fs = _clamp(font_size, 6, 72)
    rgb = _rgb(color)
    doc = _open(data)
    n = doc.page_count
    targets = _norm_list(pages, n, "pages") if pages else list(range(n))
    align_x = {"left": 0.0, "center": 0.5, "right": 1.0}[position]
    for i in targets:
        pg = doc[i]
        subs = {"{page}": str(i + 1), "{pages}": str(n), "{date}": date}
        for text, y in ((header, mg + fs), (footer, pg.rect.height - mg)):
            if not (text or "").strip():
                continue
            txt = text
            for k, v in subs.items():
                txt = txt.replace(k, v)
            width = pymupdf.get_text_length(txt, fontname="helv", fontsize=fs)
            x = max(2.0, min(align_x * (pg.rect.width - width), pg.rect.width - width - 2.0))
            pg.insert_text((x, y), txt, fontsize=fs, fontname="helv", color=rgb)
    return _save(doc)


def insert_blank_page(data: bytes, at: int = 1, count: int = 1) -> bytes:
    """Inserisce `count` pagine bianche PRIMA della pagina `at` (1-based; n+1 = in coda)."""
    doc = _open(data)
    n = doc.page_count
    try:
        at_i = int(at)
        cnt = int(count)
    except (TypeError, ValueError):
        raise ValueError("at/count devono essere interi")
    if at_i < 1 or at_i > n + 1:
        raise ValueError(f"at fuori range: {at_i} (attesi 1..{n + 1})")
    if cnt < 1 or cnt > 50:
        raise ValueError(f"count fuori range: {cnt} (attesi 1..50)")
    w, h = (doc[0].rect.width, doc[0].rect.height) if n else (595.0, 842.0)
    for k in range(cnt):
        doc.new_page(pno=at_i - 1 + k, width=w, height=h)
    return _save(doc)


def extract_pages(data: bytes, pages) -> bytes:
    """Estrae le pagine indicate (1-based, nell'ordine dato) in un nuovo PDF."""
    doc = _open(data)
    idxs = _norm_list(pages, doc.page_count, "pages")
    if not idxs:
        raise ValueError("Nessuna pagina da estrarre")
    out = pymupdf.Document()
    for i in idxs:
        out.insert_pdf(doc, from_page=i, to_page=i)
    result = _save(out)
    out.close()
    doc.close()
    return result


def form_fields(data: bytes) -> list[dict]:
    """Elenca i campi modulo: [{page, name, type, value}]."""
    doc = _open(data)
    out: list[dict] = []
    for i in range(doc.page_count):
        for w in (doc[i].widgets() or []):
            out.append({
                "page": i + 1,
                "name": w.field_name or "",
                "type": (w.field_type_string or "").lower().replace(" ", "_"),
                "value": "" if w.field_value is None else str(w.field_value),
            })
    return out


def fill_form(data: bytes, fields: dict) -> bytes:
    """Compila i campi modulo indicati. Erra se nessun campo combacia;
    i nomi non trovati vengono elencati nel messaggio."""
    if not isinstance(fields, dict) or not fields:
        raise ValueError("Nessun campo modulo da compilare")
    wanted = {str(k): ("" if v is None else str(v)) for k, v in fields.items()}
    doc = _open(data)
    left = set(wanted)
    for i in range(doc.page_count):
        for w in (doc[i].widgets() or []):
            if w.field_name in left:
                w.field_value = wanted[w.field_name]
                w.update()
                left.discard(w.field_name)
    if len(left) == len(wanted):
        raise ValueError("Il PDF non contiene campi modulo compilabili")
    if left:
        raise ValueError(f"Campi non trovati: {', '.join(sorted(left))}")
    doc.need_appearances(True)
    return _save(doc)


# --------------------------------------------------------------------------
# Sicurezza: protezione con password (AES-256) e rimozione
# --------------------------------------------------------------------------
class PasswordError(ValueError):
    """Password mancante/errata o PDF non apribile con la password data."""


_PERM_PRINT = pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_PRINT_HQ
_PERM_COPY = pymupdf.PDF_PERM_COPY | pymupdf.PDF_PERM_ACCESSIBILITY
_PERM_MODIFY = (pymupdf.PDF_PERM_MODIFY | pymupdf.PDF_PERM_ANNOTATE
                | pymupdf.PDF_PERM_FORM | pymupdf.PDF_PERM_ASSEMBLE)


def _permissions(allow_print: bool, allow_copy: bool, allow_modify: bool) -> int:
    """Bitmask permessi PDF: stampa, copia/testo accessibile, modifica completa."""
    perms = 0
    if allow_print:
        perms |= _PERM_PRINT
    if allow_copy:
        perms |= _PERM_COPY
    if allow_modify:
        perms |= _PERM_MODIFY
    return perms


def is_protected(data: bytes) -> bool:
    """True se il PDF richiede una password per l'apertura."""
    doc = _open(data)
    try:
        return bool(doc.needs_pass)
    finally:
        doc.close()


def protect(
    data: bytes,
    user_pw: str,
    owner_pw: str = "",
    allow_print: bool = True,
    allow_copy: bool = True,
    allow_modify: bool = False,
) -> bytes:
    """Cifra il PDF in AES-256. `user_pw` serve per aprirlo. Se `owner_pw` è
    vuoto ne viene generato uno casuale, così i permessi valgono davvero anche
    per chi conosce la password di apertura. Ritorna i bytes cifrati."""
    if not user_pw:
        raise PasswordError("password mancante")
    doc = _open(data)
    try:
        doc.save(
            buf := io.BytesIO(),
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=user_pw, owner_pw=(owner_pw or secrets.token_urlsafe(16)),
            permissions=_permissions(allow_print, allow_copy, allow_modify),
            garbage=3, deflate=True,
        )
        return buf.getvalue()
    finally:
        doc.close()


def unprotect(data: bytes, password: str = "") -> bytes:
    """Rimuove la password di apertura. Se il PDF non è protetto ritorna
    l'input invariato; password errata → PasswordError."""
    if not data:
        raise ValueError("PDF vuoto")
    try:
        doc = pymupdf.Document(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"PDF non valido: {e}")
    try:
        if not doc.needs_pass:
            return bytes(data)
        if not doc.authenticate(password or ""):
            raise PasswordError("password errata")
        if doc.page_count > MAX_PAGES:
            raise ValueError(f"PDF con {doc.page_count} pagine (max {MAX_PAGES} supportate)")
        doc.save(buf := io.BytesIO(), encryption=pymupdf.PDF_ENCRYPT_NONE,
                 garbage=3, deflate=True)
        return buf.getvalue()
    finally:
        doc.close()
