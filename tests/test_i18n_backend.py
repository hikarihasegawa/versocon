"""Test i18n backend: scelta lingua, fallback, interpolazione + errori tradotti in API."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.i18n import _parse_accept_language, _pick_lang, t as T  # noqa: E402
from app.main import app  # noqa: E402


def _png() -> bytes:
    from PIL import Image
    import io
    b = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(b, "PNG")
    return b.getvalue()


@pytest.fixture()
def client():
    return TestClient(app)


# ---- _parse_accept_language -----------------------------------------------
def test_parse_accept_language_basic():
    out = _parse_accept_language("it, en;q=0.9, zh;q=0.8")
    assert out == [("it", 1.0), ("en", 0.9), ("zh", 0.8)]


def test_parse_accept_language_sorts_by_q():
    out = _parse_accept_language("en;q=0.5, fr;q=0.9, de")
    # de (1.0), fr (0.9), en (0.5)
    assert [c for c, _ in out] == ["de", "fr", "en"]


def test_parse_accept_language_ignores_blank():
    out = _parse_accept_language("it, , en;q=0.2")
    assert [c for c, _ in out] == ["it", "en"]


# ---- _pick_lang -----------------------------------------------------------
def _mk_request(headers):
    from starlette.requests import Request
    scope = {"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
    return Request(scope)


def test_pick_lang_explicit_header():
    assert _pick_lang(_mk_request({"X-VersoCon-Lang": "en"})) == "en"
    assert _pick_lang(_mk_request({"X-VersoCon-Lang": "fr-CA"})) == "fr"  # root fr supportato
    assert _pick_lang(_mk_request({"X-VersoCon-Lang": "kk-KK"})) == "it"  # non supportato -> it


def test_pick_lang_accept_language_fallback():
    assert _pick_lang(_mk_request({"Accept-Language": "de-DE, de;q=0.9, en;q=0.5"})) == "de"
    assert _pick_lang(_mk_request({"Accept-Language": "ja"})) == "ja"
    assert _pick_lang(_mk_request({})) == "it"


# ---- t(): fallback + interpolazione --------------------------------------
def test_t_fallback_en_and_it():
    assert T(_mk_request({"X-VersoCon-Lang": "en"}), "api.no_files") == "No files provided"
    assert T(_mk_request({"X-VersoCon-Lang": "it"}), "api.no_files") == "Nessun file inviato"
    # es è tradotta (tutte le 8 lingue di SUPPORTED hanno il file)
    assert T(_mk_request({"X-VersoCon-Lang": "es"}), "api.no_files") == "No se envió ningún archivo"
    # chiave inesistente -> restituisce la chiave
    assert T(_mk_request({"X-VersoCon-Lang": "it"}), "api.nota_esistente_xyz") == "api.nota_esistente_xyz"


def test_t_fallback_to_en_when_lang_file_missing(monkeypatch, tmp_path):
    """Lingua supportata ma con file assente: catena lang -> en -> it -> chiave."""
    import app.i18n as i18n

    (tmp_path / "en.json").write_text('{"api.no_files": "No files provided"}', encoding="utf-8")
    (tmp_path / "it.json").write_text('{"api.no_files": "Nessun file inviato"}', encoding="utf-8")
    monkeypatch.setattr(i18n, "_I18N_DIR", tmp_path)
    i18n.reset_cache()
    try:
        assert i18n.t(_mk_request({"X-VersoCon-Lang": "de"}), "api.no_files") == "No files provided"
        assert i18n.t(_mk_request({"X-VersoCon-Lang": "de"}), "api.manca") == "api.manca"
    finally:
        i18n.reset_cache()


def test_t_param_interpolation():
    msg = T(_mk_request({"X-VersoCon-Lang": "en"}), "api.file_200mb_limit", name="a.png")
    assert msg == "a.png exceeds the 200 MB limit"


# ---- endpoint: errori tradotti -------------------------------------------
def test_convert_invalid_format_translated_en(client):
    res = client.post(
        "/api/convert",
        headers={"X-VersoCon-Lang": "en"},
        data={"fmt": "bogus"},
        files=[("files", ("a.png", _png(), "image/png"))],
    )
    assert res.status_code == 400
    assert "Unsupported output format" in res.json()["detail"] or "format" in res.json()["detail"].lower()


def test_convert_invalid_format_translated_it(client):
    res = client.post(
        "/api/convert",
        headers={"X-VersoCon-Lang": "it"},
        data={"fmt": "bogus"},
        files=[("files", ("a.png", _png(), "image/png"))],
    )
    assert res.status_code == 400
    # l'it dovrebbe tradurre 'Unsupported output format'
    assert "Formato" in res.json()["detail"] or "formato" in res.json()["detail"].lower()


def test_download_missing_file_translated(client):
    res_it = client.get("/api/file/non-esiste-xyz.jpg", headers={"X-VersoCon-Lang": "it"})
    res_en = client.get("/api/file/non-esiste-xyz.jpg", headers={"X-VersoCon-Lang": "en"})
    assert res_it.status_code == 404
    assert res_en.status_code == 404
    assert res_it.json()["detail"] != res_en.json()["detail"]
    assert "File" in res_it.json()["detail"]
    assert "not found" in res_en.json()["detail"].lower()


def test_accept_language_header_used(client):
    # senza X-VersoCon-Lang: usa Accept-Language
    res = client.get("/api/file/non-esiste.jpg", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()
