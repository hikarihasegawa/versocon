"""Tema UI: variante "Pro" (dashboard sobria) + selettore e persistenza.

Controlli statici su index.html / style.css / theme.js e calcolo reale del
contrasto WCAG 2.0 dei colori di testo del tema Pro (soglia 4.5:1).
"""
import json
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
I18N = STATIC / "i18n"
LANGS = ("it", "en", "es", "fr", "de", "pt", "zh", "ja")
MIN_RATIO = 4.5


def _css() -> str:
    return (STATIC / "style.css").read_text(encoding="utf-8")


def _theme_block() -> dict:
    """Variabili del blocco `html.theme-pro { ... }` di style.css."""
    css = _css()
    m = re.search(r"html\.theme-pro\s*\{(.*?)\}", css, re.S)
    assert m, "blocco html.theme-pro non trovato in style.css"
    body = m.group(1)
    return {k: v.strip() for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", body, re.I)}


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


def test_tema_pro_ha_le_variabili_chiave():
    v = _theme_block()
    for key in ("--paper", "--paper-2", "--ink", "--ink-soft", "--red", "--red-deep",
                "--border", "--radius", "--shadow", "--font-title"):
        assert key in v, f"manca {key} nel tema Pro"
    assert v["--shadow"] == "none", "il tema Pro deve essere piatto (shadow: none)"


def test_contrasto_testo_tema_pro():
    """Testo e testo secondario devono superare 4.5:1 su entrambe le superfici."""
    v = _theme_block()
    pairs = [
        ("--ink", "--paper"), ("--ink", "--paper-2"),
        ("--ink-soft", "--paper"), ("--ink-soft", "--paper-2"),
        ("--red-deep", "--paper"), ("--red-deep", "--paper-2"),
    ]
    failures = []
    for fg, bg in pairs:
        ratio = _contrast(v[fg], v[bg])
        if ratio < MIN_RATIO:
            failures.append(f"{fg} su {bg}: {ratio:.2f}:1")
    assert failures == [], f"contrasto insufficiente: {failures}"


def test_tema_pro_spegne_le_decorazioni():
    css = _css()
    m = re.search(r"html\.theme-pro body::before,(.*?)\{([^}]*)\}", css, re.S)
    assert m, "regola di spegnimento decorazioni non trovata"
    selectors, body = m.group(1), m.group(2)
    for sel in ("#petals", ".dropzone-card::after"):
        assert sel in selectors, f"{sel} non spento nel tema Pro"
    assert "display: none" in body


def test_selettore_tema_in_header():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for el in ('id="themeToggle"', 'id="themeLabel"', 'src="theme.js"'):
        assert el in html, f"{el} mancante in index.html"
    assert 'aria-pressed="true"' in html


def test_theme_js_persistenza_e_default_pro():
    js = (STATIC / "theme.js").read_text(encoding="utf-8")
    assert "versocon.theme" in js
    assert 'classList.toggle("theme-pro"' in js
    assert 'return t === "manga" ? "manga" : "pro"' in js  # default: Pro
    assert 'localStorage.setItem' in js and 'localStorage.getItem' in js
    assert '"vscon:lang"' in js  # etichetta tradotta al cambio lingua


def test_chiavi_tema_in_tutte_le_lingue():
    for lang in LANGS:
        data = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))
        for key in ("theme.title", "theme.pro", "theme.manga"):
            assert data.get(key), f"{lang}: manca {key}"
        assert data["theme.pro"] == "Pro" and data["theme.manga"] == "Manga"
