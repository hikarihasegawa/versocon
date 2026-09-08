"""Strumenti batch: unione (merge) PDF, estrazione pagine (split), rinomina."""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

MAX_DOC_BYTES = 100 * 1024 * 1024
MAX_PDF_FILES = 40
MAX_SPLIT_PAGES = 100

_INVALID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


class SplitRangeError(ValueError):
    """Intervallo di pagine non valido per lo split."""


def _check_pdf(raw: bytes, label: str) -> None:
    if not raw:
        raise ValueError(f"{label}: file vuoto")
    if len(raw) > MAX_DOC_BYTES:
        raise ValueError(f"{label}: oltre il limite di 100 MB")


def pdf_page_count(data: bytes) -> int:
    """Numero di pagine di un PDF in memoria."""
    if not data:
        raise ValueError("PDF vuoto")
    doc = pymupdf.Document(stream=data, filetype="pdf")
    try:
        return int(doc.page_count)
    finally:
        doc.close()


def _is_pdf(filename: str) -> bool:
    return Path(filename).suffix.lower() == ".pdf"


def merge_pdfs(pdfs: list[tuple[str, bytes]]) -> bytes:
    """Unisce N PDF nell'ordine dato in un unico documento."""
    if not isinstance(pdfs, (list, tuple)) or not pdfs:
        raise ValueError("Nessun PDF da unire")
    if len(pdfs) > MAX_PDF_FILES:
        raise ValueError(f"Massimo {MAX_PDF_FILES} PDF per fusione (ne sono {len(pdfs)})")
    out = pymupdf.Document()
    try:
        for i, (name, raw) in enumerate(pdfs, start=1):
            if not _is_pdf(name):
                raise ValueError(f"{name}: atteso un file .pdf")
            _check_pdf(raw, name)
            src = pymupdf.Document(stream=raw, filetype="pdf")
            try:
                if src.page_count == 0:
                    raise ValueError(f"{name}: PDF senza pagine")
                out.insert_pdf(src)
            finally:
                src.close()
        return out.tobytes(garbage=3, deflate=True)
    finally:
        out.close()


def split_pdf(data: bytes, start: int = 1, end: int | None = None) -> tuple[bytes, int, int]:
    """Estrae le pagine [start, end] (1-based, incluse) in un nuovo PDF.

    Ritorna (bytes_pdf, numero_pagine_eseguite, tot_pagine_sorgente).
    """
    if not data:
        raise ValueError("PDF vuoto")
    src = pymupdf.Document(stream=data, filetype="pdf")
    try:
        total = int(src.page_count)
        if total == 0:
            raise SplitRangeError("PDF senza pagine")
        lo = int(start) if start is not None else 1
        try:
            hi = int(end) if end is not None else total
        except (TypeError, ValueError) as e:
            raise SplitRangeError("Intervallo di pagine non valido") from e
        lo = max(1, min(lo, total))
        hi = max(lo, min(hi, total))
        out = pymupdf.Document()
        try:
            out.insert_pdf(src, from_page=lo - 1, to_page=hi - 1)
            if out.page_count == 0:
                raise SplitRangeError("Nessuna pagina estratta")
            payload = out.tobytes(garbage=3, deflate=True)
        finally:
            out.close()
        return payload, hi - lo + 1, total
    finally:
        src.close()


def _clean_name(s: str) -> str:
    s = _INVALID_CHARS.sub(" ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s or "file"


def rename_preview(
    names: list[str],
    mode: str = "prefix",
    value: str = "",
    start: int = 1,
    step: int = 1,
    sep: str = "-",
) -> list[str]:
    """Calcola i nuovi nomi (mantenendo estensione) per un batch di file.

    Modalità:
      - prefix  : valore + nome          -> "foto_01.jpg"
      - suffix  : nome + valore          -> "vacation_01.jpg"
      - find    : rimuove tutte le occorrenze di `value` dal nome
      - number  : base[-]N con N da `start`, passo `step`  -> "base-1.jpg"
    """
    if not isinstance(names, (list, tuple)):
        raise ValueError("Nessun file da rinominare")
    if mode not in ("prefix", "suffix", "find", "number"):
        raise ValueError(f"Modalità di rinomina non valida: {mode}")
    value = (value or "").strip()
    try:
        start = int(start) if start is not None else 1
    except (TypeError, ValueError):
        start = 1
    try:
        step = int(step) if step is not None else 1
    except (TypeError, ValueError):
        step = 1
    if step == 0:
        step = 1
    sep = sep or "-"

    n = len(names)
    last_num = start + (n - 1) * step
    pad = max(1, len(str(abs(last_num)))) if n else 1

    out: list[str] = []
    for i, name in enumerate(names):
        p = Path(name)
        stem = p.stem
        ext = p.suffix
        k = start + i * step
        if mode == "prefix":
            new = f"{value}{stem}"
        elif mode == "suffix":
            new = f"{stem}{value}"
        elif mode == "find":
            new = stem.replace(value, " ") if value else stem
        else:  # number
            base = value if value else "file"
            new = f"{base}{sep}{str(k).zfill(pad)}"
        out.append(_clean_name(new) + ext)
    return out


def rename_files(files: list[tuple[str, bytes]], mode: str, value: str, start: int, step: int) -> list[tuple[str, bytes]]:
    """Applica `rename_preview` a una lista di (nome, byte) e torna la lista rinominata."""
    names = [n for n, _ in files]
    new_names = rename_preview(names, mode=mode, value=value, start=start, step=step)
    return [(new, raw) for (new, (_, raw)) in zip(new_names, files)]
