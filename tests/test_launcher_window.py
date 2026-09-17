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
