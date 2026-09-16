"""Benvenuto al primo avvio e banner aggiornamenti: UI statica e chiavi i18n.

Il comportamento live (dialog, opt-in, banner) è coperto dallo smoke Playwright;
qui si verificano struttura, default sicuri e traduzioni presenti ovunque.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
THEME_JS = (ROOT / "static" / "theme.js").read_text(encoding="utf-8")
I18N_JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")

NEW_KEYS = [
    "about.title",
    "welcome.title", "welcome.lead", "welcome.lang", "welcome.theme",
    "welcome.update", "welcome.update_hint", "welcome.check_now", "welcome.checking",
    "welcome.uptodate", "welcome.check_fail", "welcome.cta_start", "welcome.cta_close",
    "welcome.ver", "update.open", "update.dismiss", "update.available", "api.update_fail",
]


def test_ui_dialog_benvenuto_con_checkbox_spenta_di_default():
    assert '<dialog id="welcomeDlg"' in HTML
    tag = re.search(r'<input type="checkbox" id="welcomeUpdate"[^>]*>', HTML)
    assert tag and "checked" not in tag.group(0)
    assert 'id="welcomeOk"' in HTML and 'id="welcomeVer"' in HTML


def test_ui_nessuna_rete_senza_optin():
    assert 'localStorage.getItem(UPDATE_KEY) === "1"' in APP_JS
    assert "if (updateCheckEnabled())" in APP_JS


def test_ui_banner_aggiornamento_e_about_nel_footer():
    assert 'id="updateNote"' in HTML and 'id="updateNoteOpen"' in HTML
    assert 'id="btnAbout"' in HTML and 'aria-haspopup="dialog"' in HTML
    # Accesso esplicito anche dall'header (icona ingranaggio), non solo dal footer.
    assert 'id="btnAboutHead"' in HTML and "about.title" in HTML


def test_ui_dialog_controlla_lingua_e_tema_veri():
    assert "welcomeLang" in I18N_JS and "welcomeTheme" in APP_JS
    assert "window.VTheme" in THEME_JS


def test_i18n_chiavi_nuove_presenti_in_tutte_le_lingue():
    for p in sorted((ROOT / "static" / "i18n").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for k in NEW_KEYS:
            assert isinstance(d.get(k), str) and d[k].strip(), (p.name, k)
