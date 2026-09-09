"""Backend i18n — trasla le stringhe degli errori HTTP in base alla lingua del client.

Rispetta due header, in ordine di priorità:
  1. ``X-VersoCon-Lang``  — lingua scelta dall'utente nell'UI (spedita da app.js)
  2. ``Accept-Language``  — lingua di sistema del browser / client HTTP

Se nessuno dei due header è valido, si cade su ``it`` (lingua fonte di verità).
Fallback a catena: ``lang → en → it → chiave``.

I JSON viveno in ``static/i18n/*.json`` (stesse fonti del frontend); per i
test, ``VERSOCON_I18N_DIR`` punta a una directory alternativa.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import Request

from app import constants

SUPPORTED: list[str] = ["it", "en", "es", "fr", "de", "pt", "zh", "ja"]

_I18N_DIR: Path = (
    Path(os.environ["VERSOCON_I18N_DIR"])
    if os.environ.get("VERSOCON_I18N_DIR")
    else constants.STATIC_DIR / "i18n"
)

_LANGS: dict[str, dict[str, str]] = {}


def _parse_accept_language(h: str) -> list[tuple[str, float]]:
    """``"it, en;q=0.9, zh;q=0.8"`` → ``[(it,1.0), (en,0.9), (zh,0.8)]``."""
    out: list[tuple[str, float]] = []
    for part in h.split(","):
        part = part.strip()
        if not part:
            continue
        if ";" in part:
            code, q = part.split(";", 1)
            try:
                qv = float(q.strip().lstrip("q=") or "1")
            except ValueError:
                qv = 1.0
        else:
            code, qv = part, 1.0
        code = code.strip()
        if code:
            out.append((code.lower(), qv))
    out.sort(key=lambda p: p[1], reverse=True)
    return out


def _pick_lang(request: Request) -> str:
    """Scelge la lingua migliore tra ``X-VersoCon-Lang`` e ``Accept-Language``."""
    explicit = (request.headers.get("x-versocon-lang") or "").strip().lower()
    if explicit:
        return explicit if explicit in SUPPORTED else (
            explicit.split("-")[0] if explicit.split("-")[0] in SUPPORTED else "it"
        )
    h = request.headers.get("accept-language")
    if h:
        for code, _q in _parse_accept_language(h):
            if code in SUPPORTED:
                return code
            root = code.split("-")[0]
            if root in SUPPORTED:
                return root
    return "it"


def _load(lang: str) -> dict[str, str] | None:
    if lang in _LANGS:
        return _LANGS[lang]
    p = _I18N_DIR / f"{lang}.json"
    if not p.exists():
        _LANGS[lang] = {}
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _LANGS[lang] = {}
        return None
    _LANGS[lang] = data
    return data


def t(
    request: Request,
    key: str,
    params: dict[str, object] | None = None,
    **kw: object,
) -> str:
    """Traduce ``key`` con fallback ``lang → en → it → key`` e applica ``{param}``.

    I parametri possono essere passati come dict posizionale o come keyword
    (``t(request, "api.x", name="a.png")``).
    """
    all_params: dict[str, object] = dict(params or {})
    all_params.update(kw)
    best = _pick_lang(request)
    chain = list(dict.fromkeys([best, "en", "it"])) if best in SUPPORTED else ["it"]
    for lang in chain:
        d = _load(lang)
        if d and key in d and isinstance(d[key], str) and d[key]:
            s = d[key]
            break
    else:
        s = key
    if all_params:
        try:
            return s.format(**all_params)
        except (KeyError, IndexError, ValueError):
            return s
    return s


def reset_cache() -> None:
    """Vota il cache in-memoria; utile nei test dopo aver puntato ``VERSOCON_I18N_DIR``."""
    _LANGS.clear()
