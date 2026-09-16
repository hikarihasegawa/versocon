"""Controllo aggiornamenti — opt-in, consapevole dell'edizione (Store o portable).

Nessuna connessione parte da qui: `check_for_update()` viene chiamata solo su
richiesta esplicita dell'utente (pulsante) o all'avvio se l'utente ha attivato
l'opzione (default OFF, salvata nel browser).

L'edizione Microsoft Store non può auto-aggiornarsi (policy Store 10.2.5):
per quella si apre la pagina dello Store; per portable/installer la pagina
Releases di GitHub.
"""
from __future__ import annotations

import ctypes
import json
import re
import sys
import urllib.request
from urllib.error import URLError

from app.version import __version__

RELEASES_API = "https://api.github.com/repos/hikarihasegawa/versocon/releases/latest"
RELEASES_PAGE = "https://github.com/hikarihasegawa/versocon/releases"
STORE_URL = "https://apps.microsoft.com/detail/9ngcr80nk3kc"
_TIMEOUT_S = 6.0
# GetCurrentPackageFullName: ERROR_INSUFFICIENT_BUFFER = processo con identità
# di pacchetto MSIX; APPMODEL_ERROR_NO_PACKAGE = processo normale.
_ERROR_INSUFFICIENT_BUFFER = 122
_APPMODEL_ERROR_NO_PACKAGE = 15700


class UpdateCheckError(RuntimeError):
    """Controllo aggiornamenti non riuscito: rete assente, HTTP o risposta non valida."""


def is_store_edition() -> bool:
    """True se il processo gira dentro un pacchetto MSIX (edizione Store).

    Usa `GetCurrentPackageFullName` di kernel32: su un processo senza identità
    di pacchetto restituisce `APPMODEL_ERROR_NO_PACKAGE` (15700), mentre un
    pacchetto MSIX risponde `ERROR_INSUFFICIENT_BUFFER` (122) con la lunghezza
    richiesta. Su piattaforme non Windows è sempre False."""
    if not sys.platform.startswith("win"):
        return False
    try:
        fn = ctypes.WinDLL("kernel32", use_last_error=True).GetCurrentPackageFullName
        fn.argtypes = [ctypes.POINTER(ctypes.c_uint32), ctypes.c_wchar_p]
        fn.restype = ctypes.c_long
        length = ctypes.c_uint32(0)
        return fn(ctypes.byref(length), None) == _ERROR_INSUFFICIENT_BUFFER
    except (AttributeError, OSError):
        return False


def page_url() -> str:
    """Pagina da aprire per aggiornare la copia in uso, in base all'edizione."""
    return STORE_URL if is_store_edition() else RELEASES_PAGE


def _version_tuple(text: str) -> tuple[int, ...]:
    """Converte «v0.3.0» in (0, 3, 0); testo non numerico → tupla vuota."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", str(text))
    if not m:
        return ()
    return tuple(int(p) for p in m.group(1).split("."))


def _fetch_latest(timeout: float) -> dict:
    """Ultima release pubblica da GitHub (l'API richiede uno User-Agent)."""
    req = urllib.request.Request(
        RELEASES_API,
        headers={
            "User-Agent": f"VersoCon/{__version__}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def check_for_update(timeout: float = _TIMEOUT_S) -> dict:
    """Confronta la versione installata con l'ultima release pubblica.

    Solleva `UpdateCheckError` se la rete o la risposta non sono utilizzabili.
    """
    try:
        data = _fetch_latest(timeout)
    except (URLError, OSError, ValueError) as e:
        raise UpdateCheckError(str(e)) from e
    latest = str(data.get("tag_name") or "").lstrip("v")
    if not _version_tuple(latest):
        raise UpdateCheckError("tag di release non valido")
    return {
        "current": __version__,
        "latest": latest,
        "update_available": _version_tuple(latest) > _version_tuple(__version__),
        "edition": "store" if is_store_edition() else "portable",
    }
