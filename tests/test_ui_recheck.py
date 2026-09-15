"""Bottone «Ricontrolla» (motori) e «Rimuovi firma» presenti in UI e tradotti."""
import json
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_recheck_buttons_and_handler():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.count("data-recheck") == 2
    assert 'id="btnOcrRecheck"' in html and 'id="btnVideoRecheck"' in html
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '"/api/engines/recheck"' in js
    assert 'querySelectorAll("[data-recheck]")' in js


def test_signature_clear_button_and_handler():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="btnSigClear"' in html
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    i = js.find('getElementById("btnSigClear")')
    assert i != -1 and "edSigFile = null" in js[i:i + 600]


def test_new_keys_translated():
    for lang in ("it", "en"):
        data = json.loads((STATIC / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for key in ("btn.recheck", "dyn.recheck_ok", "dyn.recheck_err", "pdf.edit.sig_clear"):
            assert data.get(key), f"{lang}.json: manca {key}"
