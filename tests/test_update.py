"""Aggiornamenti opt-in: backend, edizione e contratto HTTP.

Il controllo contatta GitHub SOLO su richiesta dell'utente (pulsante o opzione
attivata, default OFF): questi test usano `_fetch_latest` monkeypatched e non
aprono connessioni. La UI è coperta da `tests/test_ui_welcome.py` e dallo smoke.
"""
import sys
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.main as m  # noqa: E402
from app import update as upd  # noqa: E402
from app import version as app_version  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def _fake_release(monkeypatch, tag):
    monkeypatch.setattr(
        upd, "_fetch_latest",
        lambda timeout: {"tag_name": tag, "html_url": "https://github.com/hikarihasegawa/versocon/releases/tag/x"},
    )


# ── Edizione in uso ────────────────────────────────────────────────────────
def test_edition_portable_su_processo_non_pacchettizzato():
    """Chiamata reale a GetCurrentPackageFullName: da sorgente non c'è pacchetto."""
    assert upd.is_store_edition() is False
    assert upd.page_url() == upd.RELEASES_PAGE


def test_page_url_store(monkeypatch):
    monkeypatch.setattr(upd, "is_store_edition", lambda: True)
    assert upd.page_url() == upd.STORE_URL
    assert upd.STORE_URL.startswith("https://apps.microsoft.com/detail/")


# ── Confronto versioni ─────────────────────────────────────────────────────
@pytest.mark.parametrize("a,b", [("v0.10.0", "v0.9.9"), ("1.0.0", "0.99.9"), ("v0.3.0", "v0.2.99")])
def test_version_tuple_confronta_numericamente(a, b):
    assert upd._version_tuple(a) > upd._version_tuple(b)


@pytest.mark.parametrize("text", ["ultima", "", "v"])
def test_version_tuple_non_numerica(text):
    assert upd._version_tuple(text) == ()


# ── check_for_update ───────────────────────────────────────────────────────
def test_aggiornamento_disponibile(monkeypatch):
    _fake_release(monkeypatch, "v99.0.0")
    r = upd.check_for_update()
    assert r == {
        "current": app_version.__version__,
        "latest": "99.0.0",
        "update_available": True,
        "edition": "portable",
    }


def test_versione_aggiornata(monkeypatch):
    _fake_release(monkeypatch, "v" + app_version.__version__)
    assert upd.check_for_update()["update_available"] is False


@pytest.mark.parametrize("exc", [urllib.error.URLError("offline"), OSError("offline"), ValueError("json rotto")])
def test_errori_rete_o_risposta_diventano_updatecheckerror(monkeypatch, exc):
    def boom(timeout):
        raise exc

    monkeypatch.setattr(upd, "_fetch_latest", boom)
    with pytest.raises(upd.UpdateCheckError):
        upd.check_for_update()


def test_tag_non_valido_rifiutato(monkeypatch):
    _fake_release(monkeypatch, "nightly")
    with pytest.raises(upd.UpdateCheckError):
        upd.check_for_update()


# ── Contratto HTTP ────────────────────────────────────────────────────────
def test_api_update_check_contratto(monkeypatch):
    _fake_release(monkeypatch, "v99.0.0")
    r = client.post("/api/update-check")
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"current", "latest", "update_available", "edition"}
    assert data["latest"] == "99.0.0" and data["update_available"] is True
    assert data["edition"] == "portable"


def test_api_update_check_errore_tradotto_nella_lingua(monkeypatch):
    def boom(timeout):
        raise OSError("offline")

    monkeypatch.setattr(upd, "_fetch_latest", boom)
    r = client.post("/api/update-check", headers={"X-VersoCon-Lang": "en"})
    assert r.status_code == 502
    assert r.json()["detail"] == "Update check failed: check your connection and try again."


def test_api_update_open_portable_apre_releases(monkeypatch):
    opened = []
    monkeypatch.setattr(m, "_open_url_in_browser", opened.append)
    r = client.post("/api/update-open")
    assert r.status_code == 200
    assert r.json() == {"opened": True, "url": upd.RELEASES_PAGE}
    assert opened == [upd.RELEASES_PAGE]


def test_api_update_open_store_apre_store(monkeypatch):
    monkeypatch.setattr(upd, "is_store_edition", lambda: True)
    monkeypatch.setattr(m, "_open_url_in_browser", lambda url: None)
    r = client.post("/api/update-open")
    assert r.status_code == 200
    assert r.json()["url"] == upd.STORE_URL
