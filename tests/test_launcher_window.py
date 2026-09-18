"""Launcher desktop (`run.py`): contratto della finestra pywebview.

La finestra deve aprirsi massimizzata e con una base >= 1200px: il layout a due
pannelli dell'editor PDF non entrava in una finestra 860x860 (segnalato
2026-09-17). Il test usa uno stub di `webview`: nessuna GUI viene aperta.
"""
from __future__ import annotations

import sys
import types

import run


class _FakeWebview(types.ModuleType):
    def __init__(self) -> None:
        super().__init__("webview")
        self.settings: dict[str, object] = {}
        self.calls: list[dict[str, object]] = []
        self.started = False

    def create_window(self, *args, **kwargs):
        self.calls.append({"args": args, **kwargs})
        return object()

    def start(self, *args, **kwargs) -> None:
        self.started = True


def test_finestra_desktop_massimizzata_e_larga(monkeypatch):
    fake = _FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)

    rc = run._open_ui("http://127.0.0.1:1/", force_browser=False)

    assert rc == 0 and fake.started
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call.get("maximized") is True, "la finestra deve aprirsi massimizzata"
    assert int(call.get("width", 0)) >= 1200, "base finestra troppo stretta per l'editor"
    assert fake.settings.get("ALLOW_DOWNLOADS") is True


def test_avvio_impossibile_messaggio_chiaro(monkeypatch):
    """Regressione (2026-09-17): DLL bloccata da policy (Smart App Control) →
    niente traceback PyInstaller, ma avviso comprensibile e exit code 1."""
    err = ImportError(
        "DLL load failed while importing _pillow_heif: "
        "Un criterio di controllo dell'applicazione ha bloccato il file.")
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(run, "_APP_IMPORT_ERROR", err)
    monkeypatch.setattr(run, "_show_error_dialog", lambda t, x: shown.append((t, x)))
    monkeypatch.setattr(run, "_crash", lambda _msg: None)

    rc = run.main()

    assert rc == 1
    assert shown, "deve comparire un avviso all'utente"
    text = shown[0][1]
    assert "_pillow_heif" in text and "criterio di controllo" in text
    assert "firmato" in text and run._CRASH_LOG in text
