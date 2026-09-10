"""L'avviso "file eliminati alla chiusura" deve esistere in UI e in ogni lingua shipped."""
import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_session_note_present_in_all_download_surfaces():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    notes = re.findall(r'<p class="hint session-note"[^>]*data-i18n="res.session_note"', html)
    assert len(notes) == 3  # risultati, PDF->testo, editor PDF
    assert 'id="edSessionNote" hidden' in html


def test_session_note_translated():
    for lang in ("it", "en"):
        data = json.loads((STATIC / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        assert data.get("res.session_note", "").startswith("🔒")


def test_results_download_link_is_translated():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "download>Scarica</a>" not in js
    assert 'IC.t("dyn.download")' in js
    assert "try { renderResults(); } catch (e) {}" in js  # si aggiorna al cambio lingua
