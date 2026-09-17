"""PDF → testo: estrazione nativa (pymupdf) + OCR opzionale (Tesseract).

Tesseract è **incluso nel pacchetto** (nella build PyInstaller/MSIX): l'app lo
cerca prima nel bundle (`engines.bundled_dirs()`), poi sul sistema. Se il
componente incluso manca o è danneggiato l'app funziona comunque (solo testo
nativo) e lo segnala: non serve — e non viene chiesto — installare nulla a
parte. Zero dipendenze online, tutto locale e offline.

La cartella `tessdata` accanto al binario viene passata a Tesseract via
`TESSDATA_PREFIX` (Tesseract 5 vuole la cartella `tessdata` stessa), così le
lingue incluse (ita/eng) si trovano anche quando il binario non è nel PATH.
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import threading
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from . import engines
from .proc import NO_WINDOW

MAX_PAGES = 500
OCR_MIN_SIDE = 300
OCR_MAX_SIDE = 6000
OCR_DPI = 200
OCR_MIN_CONF = 30  # confidenza minima Tesseract (0-100) per il layer invisibile
DEFAULT_OCR_LANG = "ita"
FALLBACK_LANGS = ["eng", "ita"]


def _resolve_tesseract_cmd() -> str | None:
    """Restituisce il percorso assoluto del binary Tesseract, se esiste.

    Ordine: (1) $TESSERACT_CMD; (2) ricerca condivisa `engines` (PATH, WinGet
    Links/Packages, Chocolatey, Scoop, cartelle comuni).
    """
    if os.environ.get("TESSERACT_CMD"):
        v = os.environ["TESSERACT_CMD"]
        if os.path.exists(v):
            return v
    return engines.find_binary(("tesseract", "tesseract.exe"))


class OcrEngineMissingError(Exception):
    """L'utente ha richiesto OCR ma il componente OCR incluso non è utilizzabile."""

    def __init__(self, lang: str = "eng"):
        super().__init__(
            "Motore OCR non disponibile: il componente OCR incluso risulta "
            f"mancante o danneggiato (lingue richieste: ['{lang}']). "
            "Reinstalla l'app per ripristinarlo."
        )


def _tessdata_dir(tess_cmd: str) -> str | None:
    """Cartella `tessdata` accanto al binario Tesseract, se esiste.

    Tesseract 5 vuole `TESSDATA_PREFIX` = la cartella `tessdata` stessa (non la
    sua cartella padre): verificato con `tesseract --list-langs` (v5.5.3).
    """
    d = Path(tess_cmd).parent / "tessdata"
    return str(d) if d.is_dir() else None


_TESS_CACHE: str | None = None
_TESS_RESOLVED = False
# Valori originali delle variabili d'ambiente dei motori, salvati prima della
# prima risoluzione: `reset_ocr_cache` li ripristina, così il «Ricontrolla» non
# riparte con i valori scritti dalla risoluzione precedente.
_TESS_ENV_SAVED: dict[str, str | None] | None = None
_TESS_ENV_VARS = ("TESSERACT_CMD", "TESSDATA_PREFIX")


def _save_engine_env() -> None:
    """Memorizza (una sola volta) i valori originali delle variabili dei motori."""
    global _TESS_ENV_SAVED
    if _TESS_ENV_SAVED is None:
        _TESS_ENV_SAVED = {k: os.environ.get(k) for k in _TESS_ENV_VARS}


def _get_tesseract_cmd() -> str | None:
    """Cache del percorso tesseract (una sola risoluzione per processo)."""
    global _TESS_CACHE, _TESS_RESOLVED
    if _TESS_RESOLVED:
        return _TESS_CACHE
    _TESS_CACHE = _resolve_tesseract_cmd()
    _TESS_RESOLVED = True
    # Se abbiamo trovato un binario ma non è nel PATH, glielo diciamo a pytesseract.
    if _TESS_CACHE:
        _save_engine_env()
        os.environ["TESSERACT_CMD"] = _TESS_CACHE
        data = _tessdata_dir(_TESS_CACHE)
        if data:
            # Lingue accanto al binario (bundle o installazione): Tesseract 5 le
            # cerca in TESSDATA_PREFIX, che deve puntare alla cartella `tessdata`.
            os.environ["TESSDATA_PREFIX"] = data
    return _TESS_CACHE


def _try_import_pytesseract():
    """Importa pytesseract; gli passa il percorso del binary risolto.

    pytesseract usa la variabile module-level `tesseract_cmd` (default
    "tesseract"), NON l'env `TESSERACT_CMD`; qui la impostiamo esplicitamente
    al path risolto così da non dipendere dal PATH di sistema.
    """
    tess = _get_tesseract_cmd()
    if not tess:
        return None
    try:
        import pytesseract  # type: ignore
        import pytesseract.pytesseract as _pte  # type: ignore  # il binario vive qui

        _pte.tesseract_cmd = tess
        pytesseract.tesseract_cmd = tess
        return pytesseract
    except Exception:  # noqa: BLE001
        return None


_PROBE: dict | None = None
_PROBE_LOCK = threading.Lock()


def _run_quiet(cmd: list[str]) -> str:
    """Esegue un comando senza finestra console; restituisce stdout + stderr."""
    r = subprocess.run(cmd, capture_output=True, timeout=20, **NO_WINDOW)
    return (r.stdout + r.stderr).decode("utf-8", "replace")


def _tesseract_probe() -> dict:
    """Versione e lingue di Tesseract, lette una volta sola per processo.

    Sostituisce get_tesseract_version()/get_languages() di pytesseract: lanciano
    tesseract senza nascondere la console e senza memorizzare il risultato, così
    nell'exe comparivano finestre cmd all'avvio e a ogni estrazione.
    """
    global _PROBE
    with _PROBE_LOCK:
        if _PROBE is None:
            version, langs = None, []
            tess = _get_tesseract_cmd()
            if tess:
                try:
                    m = re.search(r"tesseract\s+v?(\d+(?:\.\d+)*)", _run_quiet([tess, "--version"]), re.I)
                    version = m.group(1) if m else None
                    if version:
                        for ln in _run_quiet([tess, "--list-langs"]).splitlines():
                            ln = ln.strip()
                            if ln and " " not in ln and not ln.endswith(":") and ln not in langs:
                                langs.append(ln)
                except (OSError, subprocess.SubprocessError):
                    version, langs = None, []
            _PROBE = {"version": version, "languages": langs}
        return _PROBE


def ocr_enabled() -> bool:
    """True se Tesseract risponde e ha almeno una delle lingue usate (eng/ita)."""
    if _try_import_pytesseract() is None:
        return False
    info = _tesseract_probe()
    return bool(info["version"]) and bool(set(info["languages"]) & set(FALLBACK_LANGS))


def ocr_info() -> dict:
    """Stato OCR per /api/config e CLI: { available, version, languages }."""
    if _try_import_pytesseract() is None:
        return {"available": False, "version": None, "languages": []}
    info = _tesseract_probe()
    if not info["version"]:
        return {"available": False, "version": None, "languages": []}
    return {"available": True, "version": info["version"], "languages": list(info["languages"])}


def reset_ocr_cache() -> None:
    """Dimentica percorso, versione e lingue di Tesseract (bottone «Ricontrolla»).

    Ripristina anche le variabili d'ambiente scritte dalla risoluzione
    precedente, così la ricerca successiva parte dall'ambiente reale.
    """
    global _TESS_CACHE, _TESS_RESOLVED, _PROBE, _TESS_ENV_SAVED
    _TESS_CACHE = None
    _TESS_RESOLVED = False
    _PROBE = None
    if _TESS_ENV_SAVED is not None:
        for k, v in _TESS_ENV_SAVED.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _TESS_ENV_SAVED = None


def _render_pixmap(doc: "pymupdf.Document", page_no: int, dpi: int) -> bytes:
    """Renderizza una pagina in PNG (RGB, senza alpha). Ritorna i bytes PNG."""
    page = doc[page_no]
    zoom = dpi / 72.0
    mat = pymupdf.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False, colorspace=pymupdf.csRGB)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _clamp_dpi(dpi: int | None) -> int:
    if dpi is None:
        return 150
    try:
        v = int(dpi)
    except (TypeError, ValueError):
        return 150
    return max(50, min(600, v))


def _same_row(a: dict, b: dict) -> bool:
    """La riga `b` prosegue la riga `a`: testo orizzontale, stessa linea, subito a destra."""
    (ax0, ay0, ax1, ay1), (bx0, by0, bx1, by1) = a["bbox"], b["bbox"]
    horizontal = all(abs(ln["dir"][0] - 1) < 1e-3 and abs(ln["dir"][1]) < 1e-3 for ln in (a, b))
    overlap = min(ay1, by1) - max(ay0, by0)
    return horizontal and overlap > 0.5 * min(ay1 - ay0, by1 - by0) and bx0 >= ax1 - 1


def _native_text(page: "pymupdf.Page") -> str:
    """Testo nativo di una pagina, con le righe spezzate ricomposte.

    Nei PDF con testo giustificato ogni parola può essere scritta da sola e
    get_text("text") la mette su una riga a sé ("ricerca,\\nla\\nmetrica…").
    Qui le righe dello stesso blocco che stanno sulla stessa linea, una dopo
    l'altra da sinistra a destra, vengono riunite; ordine e caratteri restano
    quelli di get_text("text").
    """
    rows: list[str] = []
    for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
        if block.get("type") != 0:
            continue
        prev, row = None, ""
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"])
            if prev is not None and _same_row(prev, line):
                gap = line["bbox"][0] - prev["bbox"][2]
                height = line["bbox"][3] - line["bbox"][1]
                if gap > 0.15 * height and not row.endswith((" ", "\t")) and not text.startswith((" ", "\t")):
                    row += " "
                row += text
            else:
                if prev is not None:
                    rows.append(row)
                row = text
            prev = line
        if prev is not None:
            rows.append(row)
    return "".join(r + "\n" for r in rows)


def page_texts(data: bytes, max_pages: int | None = None) -> list[str]:
    """Estrae il testo nativo da ogni pagina del PDF.
    Ritorna una lista di stringhe (una per pagina).
    Lancio ValueError se il PDF non è valido o vuoto.
    """
    if not data:
        raise ValueError("PDF vuoto")
    try:
        doc = pymupdf.Document(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"PDF non valido: {e}")
    try:
        n = doc.page_count
        if max_pages and n > max_pages:
            raise ValueError(f"PDF con {n} pagine (max {max_pages} supportate)")
        return [_native_text(page) for page in doc]
    finally:
        doc.close()


def _page_png(doc: "pymupdf.Document", page_no: int, dpi: int) -> bytes:
    """Renderizza una pagina di un doc già aperto in PNG (RGB), scalata per OCR."""
    raw = _render_pixmap(doc, page_no, dpi)
    img = Image.open(io.BytesIO(raw))
    if min(img.size) < OCR_MIN_SIDE:
        s = OCR_MIN_SIDE / min(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    elif max(img.size) > OCR_MAX_SIDE:
        s = OCR_MAX_SIDE / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def page_image_png(data: bytes, page_no: int, dpi: int | None = None) -> bytes:
    """Renderizza la pagina indicata in PNG per OCR. Ritorna i bytes PNG."""
    dpi = _clamp_dpi(dpi)
    try:
        doc = pymupdf.Document(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"PDF non valido: {e}")
    try:
        if page_no < 0 or page_no >= doc.page_count:
            raise ValueError(f"Pagina {page_no} fuori range")
        return _page_png(doc, page_no, dpi)
    finally:
        doc.close()


def ocr_image_bytes(img: bytes, lang: str = "eng") -> str:
    """Esegue Tesseract su un PNG e restituisce il testo.
    Lancia OcrEngineMissingError se il motore non è disponibile.

    `lang` può essere una stringa singola ("it") o "it+eng".
    """
    pyt = _try_import_pytesseract()
    if pyt is None:
        raise OcrEngineMissingError(lang)
    img_obj = Image.open(io.BytesIO(img))
    try:
        return pyt.image_to_string(img_obj, lang=lang)
    except pyt.TesseractError as e:
        raise OcrEngineMissingError(lang) from e
    except Exception as e:  # noqa: BLE001 - tesseract non raggiungibile
        raise OcrEngineMissingError(lang) from e


def extract_text(
    data: bytes,
    mode: str = "auto",
    lang: str = "it",
    ocr_dpi: int = 200,
) -> list[str]:
    """Orchestrazione: ritorna una lista di `str` una per pagina.
    mode ∈ {"auto", "on", "off"} (default "auto").
    - auto: testo nativo per ogni pagina; se una pagina è vuota → OCR.
    - on:   OCR su OGNI pagina (sovrascrive il testo nativo, se c'è).
    - off:  solo testo nativo (mai OCR).
    Lancia OcrEngineMissingError se si tenta OCR senza motore.
    Lancia ValueError su PDF vuoto/invalido.
    """
    if mode not in ("auto", "on", "off"):
        raise ValueError(f"Modalità OCR non valida: {mode!r}")
    if not data:
        raise ValueError("PDF vuoto")
    try:
        doc = pymupdf.Document(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"PDF non valido: {e}")
    dpi = _clamp_dpi(ocr_dpi)
    try:
        n = doc.page_count
        if n > MAX_PAGES:
            raise ValueError(f"PDF con {n} pagine (max {MAX_PAGES} supportate)")
        out: list[str] = []
        for i in range(n):
            txt = _native_text(doc[i])
            use_ocr = mode == "on" or (mode == "auto" and not txt.strip())
            if use_ocr:
                txt = ocr_image_bytes(_page_png(doc, i, dpi), lang=lang)
            out.append(txt)
        return out
    finally:
        doc.close()


# --------------------------------------------------------------------------
# OCR su immagini e PDF ricercabile (layer di testo invisibile)
# --------------------------------------------------------------------------
def _open_image(img: bytes) -> Image.Image:
    """Apre un file immagine (bytes) applicando l'orientamento EXIF."""
    try:
        return ImageOps.exif_transpose(Image.open(io.BytesIO(img)))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Immagine non valida: {e}") from e


def _ocr_error(e: Exception, lang: str) -> Exception:
    """Distingue lingua Tesseract mancante (ValueError) da motore assente."""
    import pytesseract  # type: ignore

    if isinstance(e, pytesseract.TesseractError) and (
        "traineddata" in str(e) or "Failed loading language" in str(e)
    ):
        return ValueError(f"Lingua OCR non disponibile: {lang}")
    return OcrEngineMissingError(lang)


def ocr_image_file(img: bytes, lang: str = "it") -> str:
    """OCR di un file immagine (foto/scansione) → testo; rispetta l'EXIF."""
    pyt = _try_import_pytesseract()
    if pyt is None:
        raise OcrEngineMissingError(lang)
    im = _open_image(img)
    try:
        return pyt.image_to_string(im, lang=lang)
    except Exception as e:  # noqa: BLE001
        raise _ocr_error(e, lang) from e


def image_to_searchable_pdf(img: bytes, lang: str = "it") -> bytes:
    """OCR di un'immagine → PDF con l'immagine + layer di testo invisibile
    (generato da Tesseract). Richiede il motore OCR."""
    pyt = _try_import_pytesseract()
    if pyt is None:
        raise OcrEngineMissingError(lang)
    im = _open_image(img)
    try:
        return bytes(pyt.image_to_pdf_or_hocr(im, lang=lang, extension="pdf"))
    except Exception as e:  # noqa: BLE001
        raise _ocr_error(e, lang) from e


def _page_ocr_layer(page: "pymupdf.Page", pyt, lang: str, dpi: int) -> int:
    """OCR della pagina renderizzata e inserimento del testo INVISIBILE
    (render_mode=3) raggruppato per riga. Ritorna il numero di parole inserite."""
    raw = _render_pixmap(doc=page.parent, page_no=page.number, dpi=dpi)
    img = Image.open(io.BytesIO(raw))
    try:
        d = pyt.image_to_data(img, lang=lang, output_type=pyt.Output.DICT)
    except Exception as e:  # noqa: BLE001
        raise _ocr_error(e, lang) from e
    sx = page.rect.width / img.width
    sy = page.rect.height / img.height
    lines: dict[tuple[int, int, int], list[tuple[int, int, int, int, str]]] = {}
    for j, txt in enumerate(d["text"]):
        word = (txt or "").strip()
        if d["level"][j] != 5 or not word or int(d["conf"][j]) < OCR_MIN_CONF:
            continue
        key = (d["block_num"][j], d["par_num"][j], d["line_num"][j])
        lines.setdefault(key, []).append(
            (d["left"][j], d["top"][j], d["width"][j], d["height"][j], word)
        )
    count = 0
    for words in lines.values():
        words.sort(key=lambda w: w[0])
        left = min(w[0] for w in words)
        top = min(w[1] for w in words)
        height = max(w[3] for w in words)
        size = max(4.0, min(200.0, height * sy * 0.85))
        baseline = top * sy + height * sy * 0.8
        page.insert_text((left * sx, baseline), " ".join(w[4] for w in words),
                         fontsize=size, fontname="helv", render_mode=3)
        count += len(words)
    return count


def searchable_pdf(
    data: bytes,
    lang: str = "it",
    dpi: int | None = None,
    pages=None,
) -> bytes:
    """Rende ricercabile un PDF scansionato: sovrappone un layer di testo
    INVISIBILE al contenuto originale (che non viene modificato).

    - `pages=None` → solo le pagine senza testo nativo (auto).
    - `pages=[...]` (1-based) → esattamente quelle pagine.
    Richiede Tesseract (OcrEngineMissingError se assente)."""
    pyt = _try_import_pytesseract()
    if pyt is None:
        raise OcrEngineMissingError(lang)
    if not data:
        raise ValueError("PDF vuoto")
    try:
        doc = pymupdf.Document(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"PDF non valido: {e}")
    try:
        n = doc.page_count
        if n > MAX_PAGES:
            raise ValueError(f"PDF con {n} pagine (max {MAX_PAGES} supportate)")
        dpi_c = _clamp_dpi(dpi)
        target = set(int(p) for p in pages) if pages else None
        if target:
            bad = sorted(p for p in target if p < 1 or p > n)
            if bad:
                raise ValueError(f"Pagine fuori range: {bad} (attese 1..{n})")
        for i in range(n):
            if target is not None:
                if (i + 1) not in target:
                    continue
            elif _native_text(doc[i]).strip():
                continue
            _page_ocr_layer(doc[i], pyt, lang, dpi_c)
        buf = io.BytesIO()
        doc.save(buf, garbage=3, deflate=True)
        return buf.getvalue()
    finally:
        doc.close()
