"""UI-G: layout a rail laterale (dashboard) — struttura, icone, drawer, pillole.

Controlli statici su index.html / style.css / app.js / theme.js + contrasto
WCAG calcolato per le superfici nuove del tema Pro e chiavi i18n del menu.
"""
import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
I18N = STATIC / "i18n"
LANGS = ("it", "en", "es", "fr", "de", "pt", "zh", "ja")
MIN_RATIO = 4.5


def _html() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def _css() -> str:
    return (STATIC / "style.css").read_text(encoding="utf-8")


def _js() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8")


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    s = value.strip().lstrip("#")
    assert re.fullmatch(r"[0-9a-fA-F]{6}", s), f"colore non #rrggbb: {value!r}"
    n = int(s, 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


def _luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    l1, l2 = _luminance(_hex_to_rgb(fg)), _luminance(_hex_to_rgb(bg))
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _theme_block() -> dict:
    m = re.search(r"html\.theme-pro\s*\{(.*?)\}", _css(), re.S)
    assert m, "blocco html.theme-pro non trovato in style.css"
    return {k: v.strip() for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", m.group(1), re.I)}


def test_rail_structure_and_wrappers():
    html = _html()
    for el in ('<div class="app-body">', '<div class="app-main">', 'id="mainTabs"',
               'id="navToggle"', 'id="navScrim"', 'aria-controls="mainTabs"'):
        assert el in html, f"{el} mancante in index.html"
    # la shell chiude: main > app-body > app-main > footer
    assert html.index('class="app-body"') < html.index('id="mainTabs"') < html.index('class="app-main"')
    assert html.index('class="app-main"') < html.index('<footer class="foot">')
    # nav tradotta e drawer accessibile
    assert 'data-i18n-attr="aria-label:nav.aria"' in html
    assert 'aria-expanded="false"' in html
    # tab = icone + etichetta separata (la traduzione non cancella l'icona)
    assert html.count('<span class="nav-label" data-i18n="nav.') == 4
    assert html.count('<svg class="nav-ic"') == 4
    assert html.count('role="tab"') == 4


def test_css_rail_drawer_and_pills():
    css = _css()
    assert "grid-template-columns: 232px minmax(0, 1fr)" in css
    assert ".shell.wide .app-body" in css  # editor: rail a icone
    assert ".nav-scrim" in css and "body.nav-open .nav-scrim" in css
    assert "@media (max-width: 900px)" in css
    assert "transform: translateX(-104%)" in css
    # pillole e superfici piatte nel tema Pro
    assert "html.theme-pro .card { border: 0;" in css
    assert "border-radius: 999px" in css


def test_appjs_drawer_and_theme_aware_labels():
    js = _js()
    for s in ("setNavOpen(false)", "navScrim.addEventListener", 'e.key === "Escape"',
              "syncNavLabels", "stripEmoji", "isProTheme", "ED_TOOL_ICONS", "tool-ic"):
        assert s in js, f"{s} mancante in app.js"
    theme = (STATIC / "theme.js").read_text(encoding="utf-8")
    assert '"vscon:theme"' in theme


def test_contrasto_superfici_rail():
    """Testo su rail (--paper-2), voce attiva (--paper-3) e pillola primaria."""
    v = _theme_block()
    pairs = [
        (v["--ink"], v["--paper-3"]),
        ("#ffffff", v["--paper-3"]),
        (v["--ink-soft"], v["--paper-2"]),
    ]
    failures = [f"{fg} su {bg}: {_contrast(fg, bg):.2f}:1" for fg, bg in pairs if _contrast(fg, bg) < MIN_RATIO]
    assert failures == [], f"contrasto insufficiente: {failures}"


def test_chiave_menu_tradotta_ovunque():
    for lang in LANGS:
        data = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))
        assert data.get("nav.menu"), f"{lang}: manca nav.menu"


def test_tablist_aria_contratto():
    """Contratto tablist verticale: ruoli, orientamento, roving tabindex."""
    html = _html()
    assert 'role="tablist" aria-orientation="vertical"' in html
    for i, (tid, tab) in enumerate([("photos", "photos"), ("pdf", "pdf"),
                                    ("compress", "compress"), ("video", "video")]):
        assert f'id="tabBtn-{tid}"' in html, f"manca id tabBtn-{tid}"
        assert f'aria-labelledby="tabBtn-{tid}"' in html, f"manca aria-labelledby per {tid}"
    assert html.count('role="tabpanel"') == 4
    assert 'id="tabBtn-photos" role="tab" aria-selected="true" tabindex="0"' in html
    assert html.count('aria-selected="false" tabindex="-1"') == 3


def test_navigazione_da_tastiera():
    js = _js()
    for s in ("selectTab", "tabButtons", "ArrowDown", "ArrowUp", "ArrowLeft",
              "ArrowRight", "Home", "End", "tabIndex = on ? 0 : -1"):
        assert s in js, f"{s} mancante in app.js"


def test_rail_con_veste_anche_in_manga():
    """Il rail non è più una fila di barre sciolte: pannello + voci + stato attivo."""
    css = _css()
    m = re.search(r"\.app-body \.tabs \{(.*?)\}", css, re.S)
    assert m, "regola base .app-body .tabs mancante"
    panel = m.group(1)
    for s in ("background: var(--paper-2)", "border: var(--border)",
              "box-shadow: var(--shadow-sm)", "padding: 8px"):
        assert s in panel, f"rail senza {s!r} (veste Manga incompleta)"
    assert ".app-body .tabs .tab {" in css
    assert ".app-body .tabs .tab.active {" in css
    assert "border-color: var(--ink)" in css


def test_rail_collassato_mostra_le_icone_in_entrambi_i_temi():
    """Regressione: in Manga le barre collassate restavano vuote (no label, no icona)."""
    css = _css()
    assert ".shell.wide .app-body .nav-label { display: none; }" in css
    assert ".shell.wide .app-body .nav-ic { display: block;" in css


def test_regressioni_layout_e_tema():
    css = _css()
    assert "html.theme-pro .nav-toggle { display: none; }" in css, "toggle visibile a desktop (regressione)"
    assert "inset: 0 0 0 min(300px, 86vw)" in css, "lo scrim deve coprire solo l'area fuori dal drawer"
    assert "body.nav-open .nav-scrim { display: block; }" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".app-body .tabs { transition: none; }" in css
    js = _js()
    assert "isProTheme() ? stripEmoji(raw) : raw" in js, "le emoji si tolgono solo nel tema Pro"


def test_masthead_si_impila_sotto_900():
    """Regressione overflow Manga a 768px: badge+selettori non stanno accanto al logo."""
    blocks = _css().split("@media (max-width: 900px)")
    assert len(blocks) >= 3, "attese due media query a 900px (editor + drawer)"
    last = blocks[-1]
    assert ".masthead { flex-direction: column; align-items: flex-start; gap: 14px; }" in last
    assert ".masthead-right { align-items: flex-start; }" in last


def test_drawer_definito_prima_del_tablist():
    """Regressione TDZ: `navToggle` (const) va inizializzata prima di selectTab()."""
    js = _js()
    assert js.index("const navToggle") < js.index("function selectTab")
