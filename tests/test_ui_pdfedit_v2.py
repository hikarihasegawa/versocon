"""Editor PDF v2: pannello UI (17 azioni) presente e cablato a /api/pdf-edit.

Controlli statici su index.html / app.js / style.css + chiavi i18n tradotte.
La parità completa chiave/placeholder tra lingue è in test_i18n_keys.py.
"""
import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
I18N = STATIC / "i18n"

NEW_ACTIONS = [
    "annotate", "note", "ink", "stamp", "text", "redact", "replace",
    "number", "headerfooter", "insertpage", "extract", "form",
]
SECURE_ACTIONS = ["protect", "unprotect", "searchable"]
ALL_ACTIONS = ["rotate", "delete", "reorder", "watermark", "signature"] + NEW_ACTIONS + SECURE_ACTIONS


def test_all_actions_in_select():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<select id="edAction".*?</select>', html, re.S)
    assert m, "select #edAction non trovato"
    values = re.findall(r'<option value="([a-z]+)"', m.group(0))
    assert sorted(values) == sorted(ALL_ACTIONS)


def test_all_action_blocks_present():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    missing = [a for a in ALL_ACTIONS if f'id="edBlock-{a}"' not in html]
    assert missing == []


def test_draw_layers_present():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="edInkLayer"' in html
    assert 'id="edRectLayer"' in html
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".ed-draw" in css


def test_apply_dispatches_new_actions():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    missing = [a for a in NEW_ACTIONS if f'act === "{a}"' not in js]
    assert missing == []


def test_form_fields_endpoint_and_handler():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '"/api/pdf-form-fields"' in js
    assert 'id="btnFormLoad"' in (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'data-field' in js


def test_tool_grid_and_sticky_panel_layout():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="edTools"' in html
    assert "ed-action-sel" in html and 'tabindex="-1"' in html
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "ED_TOOLS" in js and "renderEdTools" in js and "aria-pressed" in js
    assert 'classList.toggle("wide"' in js
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".ed-tools {" in css and ".ed-head {" in css and ".ed-tool {" in css
    assert "grid-template-columns: minmax(320px, 360px)" in css
    assert ".ed-left .ed-foot {" in css and "position: sticky" in css
    assert 'class="ed-foot"' in html
    assert ".shell.wide" in css


def test_apply_reloads_live_preview_and_chains_edits():
    """Dopo «Applica» il risultato diventa il documento di lavoro e l'anteprima si aggiorna."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "edPdfFile = new File([blob], res.name" in js
    assert "loadEdPreview(edPdfFile, true)" in js
    assert "async function loadEdPreview(file, keepView = false)" in js


def test_i18n_dispatches_lang_event_on_init():
    js = (STATIC / "i18n.js").read_text(encoding="utf-8")
    assert 'new CustomEvent("vscon:lang"' in js
    assert js.count('new CustomEvent("vscon:lang"') == 2


def test_action_keys_translated_all_languages():
    js = (STATIC / "i18n.js").read_text(encoding="utf-8")
    langs = re.findall(r'"([a-z]{2})"', re.search(r"SUPPORTED\s*=\s*\[([^\]]+)\]", js).group(1))
    keys = [
        "pdf.edit.annotate", "pdf.edit.note", "pdf.edit.ink", "pdf.edit.stamp",
        "pdf.edit.text", "pdf.edit.redact", "pdf.edit.replace", "pdf.edit.number",
        "pdf.edit.hf", "pdf.edit.insertpage", "pdf.edit.extract", "pdf.edit.form",
        "pdf.edit.group_pages", "pdf.edit.group_mark", "pdf.edit.group_text",
        "pdf.edit.group_doc", "pdf.edit.group_form",
        "pdf.edit.click_pos", "pdf.edit.ink_hint", "pdf.edit.redact_hint",
        "pdf.edit.form_load", "pdf.edit.form_hint", "pdf.edit.hf_ph",
        "dyn.needle_required", "dyn.ink_empty", "dyn.redact_rects_empty",
        "dyn.form_no_fields",
    ]
    for lang in langs:
        data = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))
        missing = [k for k in keys if not data.get(k)]
        assert missing == [], f"{lang}.json: mancano {missing}"


def test_barre_sticky_col_sfondo_della_card():
    """Regressione: ed-head/ed-foot sticky con sfondo --paper creavano bande nere
    che tagliavano il pannello (visibile soprattutto in Manga) mentre si scorre."""
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    head = re.search(r"\.ed-head \{(.*?)\}", css, re.S)
    foot = re.search(r"\.ed-left \.ed-foot \{(.*?)\}", css, re.S)
    assert head, ".ed-head non trovato"
    assert foot, ".ed-left .ed-foot non trovato"
    assert "background: var(--paper-2)" in head.group(1), "ed-head non usa la superficie della card"
    assert "background: var(--paper-2)" in foot.group(1), "ed-foot non usa la superficie della card"
    assert "background: var(--paper);" not in head.group(1)
    assert "background: var(--paper);" not in foot.group(1)


def test_shell_wide_ricalcolata_al_cambio_sezione():
    """Regressione: dopo l'editor PDF la shell restava larga (rail a icone) anche
    cambiando sezione principale, perché `wide` era tolto solo dal click subtab."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "function syncShellWide()" in js
    assert js.count("syncShellWide();") >= 2, "attesa la chiamata in selectTab e nel subtab PDF"
    assert '#tabPdf .subtab.active[data-sub="pdf-edit"]' in js
    assert 'classList.toggle("wide"' in js
