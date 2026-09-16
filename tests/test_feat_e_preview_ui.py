"""FEAT-E (E2): anteprima live nell'editor PDF — debounce e annullo lato UI.

Controlli statici su index.html / app.js / style.css: overlay PNG, badge di
stato, fetch verso `/api/pdf-edit-preview` con AbortController, debounce,
stessi parametri Form di «Applica» (buildEdForm) più page/dpi, azioni
geometriche escluse dal dry-run. La parità delle chiavi i18n è in
test_i18n_keys.py; il contratto HTTP del backend in test_feat_e_preview.py.
"""
import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
I18N = STATIC / "i18n"

OVERLAY_ACTIONS = ["stamp", "note", "text", "ink", "signature"]
NEW_KEYS = ["pdf.edit.prev_live", "pdf.edit.prev_fail", "dyn.pdf_locked", "dyn.pages_required"]


def _html() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def _js() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8")


def _css() -> str:
    return (STATIC / "style.css").read_text(encoding="utf-8")


def test_overlay_e_badge_presenti():
    html = _html()
    assert 'id="edPrevImg"' in html and 'class="ed-prev-img"' in html
    m = re.search(r'<span id="edPrevBadge"[^>]*>', html)
    assert m, "badge #edPrevBadge non trovato"
    assert 'role="status"' in m.group(0) and 'aria-live="polite"' in m.group(0)
    assert 'data-i18n="pdf.edit.prev_live"' in html


def test_fetch_preview_con_abort_e_debounce():
    js = _js()
    assert '"/api/pdf-edit-preview"' in js
    assert "new AbortController()" in js
    assert "signal: ctl.signal" in js
    assert "clearTimeout(edPrevTimer)" in js
    assert re.search(r"scheduleEdPreview\(delay = 400", js), "debounce 400ms mancante"
    assert re.search(r"setTimeout\(\(\) => \{ edPrevTimer = null; refreshEdPreview\(\); \}, delay\)", js)


def test_stessi_form_di_applica_piu_page_dpi():
    js = _js()
    assert "function buildEdForm()" in js
    assert js.count("fd = buildEdForm()") >= 2, "Applica e anteprima devono condividere buildEdForm"
    assert 'fd.append("page", String(edCurPage))' in js
    assert 'fd.append("dpi", String(edPreviewDpi()))' in js
    assert 'fetch("/api/pdf-edit"' in js, "l'endpoint sincrono di Applica deve restare"


def test_azioni_geometriche_restano_overlay_client():
    js = _js()
    m = re.search(r"const ED_OVERLAY_ACTIONS = \[([^\]]+)\]", js)
    assert m, "ED_OVERLAY_ACTIONS non trovata"
    listed = re.findall(r'"([a-z]+)"', m.group(1))
    assert listed == OVERLAY_ACTIONS
    assert "edPreviewIsOverlay()" in js
    assert 'mode.value === "rect"' in js


def test_stato_badge_e_blocco_durante_applica():
    js = _js()
    assert "edSetPreviewState(\"busy\")" in js
    assert "edSetPreviewState(\"ok\")" in js
    assert "edSetPreviewState(\"fail\")" in js
    assert "edApplyBusy = true;" in js and "edApplyBusy = false;" in js
    assert "edRenderPreviewBadgeText" in js
    assert "try { edRenderPreviewBadgeText(); } catch (e) {}" in js, "il badge va ritradotto al cambio lingua"


def test_css_overlay_badge_e_reduced_motion():
    css = _css()
    assert ".ed-prev-img {" in css and ".ed-prev-badge {" in css
    assert '.ed-prev-badge[data-state="fail"]' in css
    assert "@keyframes edspin" in css
    m = re.search(r"@media \(prefers-reduced-motion: reduce\) \{\s*\.ed-prev-spin \{ animation: none", css)
    assert m, "lo spinner deve rispettare reduced-motion"


def test_chiavi_i18n_presenti_in_tutte_le_lingue():
    for lang in [p.stem for p in I18N.glob("*.json")]:
        data = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))
        missing = [k for k in NEW_KEYS if k not in data]
        assert missing == [], f"{lang}: chiavi mancanti {missing}"


def test_pdf_protetto_sblocca_anteprima_con_password():
    """Regressione E3: un PDF protetto non blocca l'editor; la password di
    «Rimuovi password» apre pdf.js e la preview live riparte."""
    js = _js()
    assert "let edPdfPw" in js
    assert "password: edPdfPw || undefined" in js, "pdf.js deve ricevere la password"
    assert '"PasswordException"' in js, "il caso locked va distinto dagli altri errori"
    assert 'IC.t("dyn.pdf_locked")' in js
    assert 'edPdfPw = "";' in js, "un nuovo file non deve riusare la password precedente"
    m = re.search(r'edPwUnlockEl\.addEventListener\("input", \(\) => \{(.*?)\n  \}\);', js, re.S)
    assert m, "listener di sblocco sulla password mancante"
    assert 'edAction.value !== "unprotect"' in m.group(1)
    assert "loadEdPreview(edPdfFile)" in m.group(1)


def test_delete_campo_vuoto_non_chiama_il_server():
    """Regressione E3: «Elimina pagine» senza pagine è un errore tradotto lato
    client, non un 400 dell'anteprima (prima: badge rosso appena si sceglieva
    l'azione)."""
    js = _js()
    m = re.search(r'act === "delete"\) \{(.*?)\n    \} else if', js, re.S)
    assert m, "blocco delete non trovato"
    assert 'if (!payload) throw new Error(IC.t("dyn.pages_required"))' in m.group(1)


def test_campi_modulo_refresh_anteprima():
    """Regressione E3: dopo «Carica campi» l'anteprima si rigenera da sola."""
    js = _js()
    m = re.search(r'btnFormLoad\.addEventListener\("click", async \(\) => \{(.*?)\n  \}\);', js, re.S)
    assert m, "handler btnFormLoad non trovato"
    assert "scheduleEdPreview(0);" in m.group(1)
