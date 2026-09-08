"""VersoCon — costanti globali dell'app."""
from __future__ import annotations

import os
import sys
from pathlib import Path

KOFI_URL = "https://ko-fi.com/hikari22"


def _bundled_root() -> Path:
    """Radice dei file statici/asset.

    In dev:  il progetto (genitore di questo file).
    frozen:  `Path(sys._MEIPASS)` (PyInstaller onedir).
    Per override esplicito: `VERSOCON_HOME`.
    """
    if os.environ.get("VERSOCON_HOME"):
        return Path(os.environ["VERSOCON_HOME"]).resolve()
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass).resolve()
    return Path(__file__).resolve().parent.parent


ROOT = _bundled_root()
STATIC_DIR = ROOT / "static"
ASSETS_DIR = ROOT / "assets"
