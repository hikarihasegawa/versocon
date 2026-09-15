"""FEAT-B UI: gruppo «Sicurezza» nell'editor + OCR immagine in «PDF → testo».

Controlli statici su index.html / app.js / style.css e sulle chiavi i18n delle
8 lingue; il comportamento end-to-end è coperto dallo smoke Playwright.
"""
import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
I18N = STATIC / "i18n"

SECURE_ACTIONS = ["protect", "unprotect", "searchable"]
SECURE_KEYS = [
    "pdf.edit.protect", "pdf.edit.unprotect", "pdf.edit.searchable",
    "pdf.edit.group_secure", "pdf.edit.pw", "pdf.edit.pw_repeat",
    "pdf.edit.pw_owner", "pdf.edit.allow_print", "pdf.edit.allow_copy",
    "pdf.edit.allow_modify", "pdf.edit.protect_hint", "pdf.edit.unprotect_hint",
    "pdf.edit.ocr_lang", "pdf.edit.searchable_hint",
    "pdf.img_ocr_hint", "pdf.img_ocr_mode", "pdf.img_ocr_text",
    "pdf.img_ocr_pdf", "btn.image", "btn.img_ocr",
    "dyn.pw_required", "dyn.pw_mismatch", "dyn.img_ocr_ok", "dyn.img_ocr_pdf_ok",
]


def _html() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def _js() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8")


def test_secure_actions_in_select_and_blocks():
    html = _html()
    m = re.search(r'<select id="edAction".*?</select>', html, re.S)
    assert m, "select #edAction non trovato"
    values = re.findall(r'<option value="([a-z]+)"', m.group(0))
    for a in SECURE_ACTIONS:
        assert a in values, f"opzione {a} mancante nella select"
        assert f'id="edBlock-{a}"' in html, f"blocco edBlock-{a} mancante"


def test_protect_fields_and_permissions():
    html = _html()
    for el in ['id="edPwA"', 'id="edPwB"', 'id="edPwOwner"',
               'id="edAllowPrint"', 'id="edAllowCopy"', 'id="edAllowModify"',
               'type="password"']:
        assert el in html, f"{el} mancante"
    assert html.count('type="password"') >= 3
    js = _js()
    for field in ["pdf_pw", "pdf_pw_owner", "allow_print", "allow_copy", "allow_modify"]:
        assert f'fd.append("{field}"' in js, f"FormData: {field} mancante"
    assert 'act === "unprotect"' in js and 'id="edPwUnlock"' in html
    assert 'act === "searchable"' in js and 'id="edOcrLang"' in html


def test_searchable_uses_ocr_lang_and_optional_pages():
    js = _js()
    assert 'fd.append("ocr_lang"' in js
    html = _html()
    assert 'id="edOcrPages"' in html
    assert 'id="edOcrLang"' in html


def test_secure_group_in_tool_grid():
    js = _js()
    assert '["pdf.edit.group_secure", ["protect", "unprotect", "searchable"]]' in js


def test_image_ocr_block_and_fetch():
    html = _html()
    for el in ['id="txtImgIn"', 'id="txtImgMode"', 'id="txtImgLang"', 'id="btnImgOcr"']:
        assert el in html, f"{el} mancante"
    assert 'accept="image/*' in html
    assert '<option value="text"' in html and '<option value="pdf"' in html
    js = _js()
    assert '"/api/image-ocr"' in js
    assert 'fd.append("mode"' in js


def test_image_ocr_result_toggles_preview():
    js = _js()
    assert "txtPreview.hidden" in js and "txtCopy.hidden" in js
    assert 'IC.t("dyn.img_ocr_ok")' in js and 'IC.t("dyn.img_ocr_pdf_ok")' in js


def test_secure_keys_translated_all_languages():
    js = (STATIC / "i18n.js").read_text(encoding="utf-8")
    langs = re.findall(r'"([a-z]{2})"', re.search(r"SUPPORTED\s*=\s*\[([^\]]+)\]", js).group(1))
    for lang in langs:
        data = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))
        missing = [k for k in SECURE_KEYS if not data.get(k)]
        assert missing == [], f"{lang}.json: mancano {missing}"


def test_sep_style_present():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert ".sep {" in css
    assert ".ctlrow label.chk" in css
