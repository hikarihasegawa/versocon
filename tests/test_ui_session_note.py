"""L'avviso "file eliminati alla chiusura" deve esistere in UI (una sola volta, nel footer) e in ogni lingua shipped."""
import json
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_session_note_single_in_global_footer():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert html.count('data-i18n="res.session_note"') == 1
    assert 'class="foot-note" data-i18n="res.session_note"' in html
    # niente più banner ripetuti per funzionalità
    assert 'class="hint session-note"' not in html
    assert "edSessionNote" not in html
    assert "edSessionNote" not in (STATIC / "app.js").read_text(encoding="utf-8")


def test_session_note_translated():
    for lang in ("it", "en"):
        data = json.loads((STATIC / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        assert data.get("res.session_note", "").startswith("🔒")


def test_results_download_link_is_translated():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "download>Scarica</a>" not in js
    assert 'IC.t("dyn.download")' in js
    assert "try { renderResults(); } catch (e) {}" in js  # si aggiorna al cambio lingua
