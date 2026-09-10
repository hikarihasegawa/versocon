"""VersoCon — difese per un server HTTP locale.

Il server gira su 127.0.0.1, ma "locale" non vuol dire "fidato": qualsiasi
pagina aperta nel browser dell'utente può tentare richieste verso localhost.

- Host allowlist  -> blocca il DNS rebinding (evil.com risolto su 127.0.0.1).
- Origin check    -> blocca il CSRF sulle richieste che modificano stato.
- safe_child      -> impedisce di uscire da OUT_DIR (path traversal, anche con
                     separatori/drive Windows passati come stringa).
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_BASE_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def allowed_hosts() -> frozenset[str]:
    """Host ammessi. `VERSOCON_EXTRA_HOSTS` (separati da virgola) serve ai test."""
    extra = os.environ.get("VERSOCON_EXTRA_HOSTS", "")
    return _BASE_HOSTS | {h.strip().lower() for h in extra.split(",") if h.strip()}


def _strip_port(hostport: str) -> str:
    hp = hostport.strip().lower()
    if hp.startswith("["):  # IPv6: [::1]:8321
        return hp[1:hp.find("]")] if "]" in hp else hp
    return hp.rsplit(":", 1)[0] if hp.count(":") == 1 else hp


class LocalOnlyMiddleware:
    """Rifiuta Host non locali e Origin estranei (metodi non sicuri)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.hosts = allowed_hosts()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}

        host = _strip_port(headers.get("host", ""))
        if host not in self.hosts:
            await PlainTextResponse("Invalid host", status_code=400)(scope, receive, send)
            return

        if scope["method"].upper() not in _SAFE_METHODS:
            origin = headers.get("origin")
            # Nessun Origin = client non-browser (curl, test): un processo locale
            # può comunque leggere i file dell'utente, quindi non è un confine.
            if origin is not None:
                o = urlsplit(origin)
                if o.scheme not in ("http", "https") or (o.hostname or "").lower() not in self.hosts:
                    await PlainTextResponse("Invalid origin", status_code=403)(scope, receive, send)
                    return

        await self.app(scope, receive, send)


def safe_child(base: Path, name: str) -> Path | None:
    """Restituisce `base/name` solo se `name` è un semplice nome di file.

    Rifiuta separatori POSIX e Windows, `:` (unità/ADS), `.`/`..` e qualsiasi
    percorso che, risolto, finisca fuori da `base`. La validazione è fatta con
    la semantica di ENTRAMBI i sistemi, così è identica su Linux e Windows.
    """
    # ":" escluso: su Windows indica unità ("C:") o alternate data stream ("f:s").
    if not name or "\x00" in name or ":" in name:
        return None
    if name in (".", "..") or PurePosixPath(name).name != name or PureWindowsPath(name).name != name:
        return None
    base_r = base.resolve()
    p = (base_r / name).resolve()
    if p.parent != base_r:
        return None
    return p
