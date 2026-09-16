"""Cartelle dei motori esterni (Tesseract, ffmpeg) da includere nel bundle.

Il workflow di release scarica i motori pinnati e passa le cartelle via
`VERSOCON_TESSERACT_DIR` / `VERSOCON_FFMPEG_DIR`; lo spec PyInstaller le copia
in `_internal/tesseract` e `_internal/ffmpeg`, dove `converters.engines` le
cerca per prime (bundle → PATH → sistema).

Senza variabili (build di sviluppo) il bundle non include motori. Con
`VERSOCON_REQUIRE_ENGINES=1` (release) l'assenza è un errore: un artefatto
senza motori deve fallire in build, non arrivare all'utente.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

# (variabile d'ambiente, sottocartella in `_internal`)
ENGINE_ENVS = (
    ("VERSOCON_TESSERACT_DIR", "tesseract"),
    ("VERSOCON_FFMPEG_DIR", "ffmpeg"),
)
REQUIRE_ENV = "VERSOCON_REQUIRE_ENGINES"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() not in ("", "0", "false", "no")


def engine_datas(env: Mapping[str, str] | None = None) -> list[tuple[str, str]]:
    """Coppie `(cartella sorgente, destinazione _internal)` dei motori da impacchettare.

    Lancia `ValueError` se una variabile è impostata ma non è una cartella, o se
    `VERSOCON_REQUIRE_ENGINES` è attivo e nessun motore è disponibile.
    """
    e: Mapping[str, str] = os.environ if env is None else env
    out: list[tuple[str, str]] = []
    for var, dest in ENGINE_ENVS:
        raw = (e.get(var) or "").strip()
        if not raw:
            continue
        p = Path(raw)
        if not p.is_dir():
            raise ValueError(f"{var}={raw} non è una cartella")
        out.append((str(p), dest))
    if not out and _truthy(e.get(REQUIRE_ENV)):
        raise ValueError(
            f"{REQUIRE_ENV} attivo ma nessun motore: impostare "
            + " e ".join(var for var, _ in ENGINE_ENVS)
        )
    return out
