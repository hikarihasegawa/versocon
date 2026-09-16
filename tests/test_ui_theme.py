"""Tema UI: variante "Pro" (dashboard sobria) + selettore e persistenza.

Controlli statici su index.html / style.css / theme.js e calcolo reale del
contrasto WCAG 2.0 dei colori di testo di entrambi i temi (soglia 4.5:1),
di bottoni/badge accesi e delle regole di accessibilita' (focus, motion).
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


def _vars_block(selector: str) -> dict:
    """Variabili CSS dei blocchi che corrispondono al selettore (anche piu' d'uno)."""
    css = _css()
    out: dict = {}
    for body in re.findall(selector + r"\s*\{([^}]*)\}", css, re.S):
        out.update({k: v.strip() for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", body, re.I)})
    assert out, f"blocco {selector} non trovato in style.css"
    return out


def _theme_block() -> dict:
    """Variabili del blocco `html.theme-pro { ... }` di style.css."""
    return _vars_block(r"html\.theme-pro")


def _manga_block() -> dict:
    """Variabili di `:root` (tema Manga, il predefinito) fuse in un solo dict."""
    return _vars_block(r":root")


def _resolve(value: str, vars_: dict, depth: int = 0) -> tuple[int, int, int, float]:
    """Colore CSS -> (r, g, b, alpha). Supporta #rrggbb, rgb()/rgba() e var()."""
    assert depth < 8, f"catena var troppo profonda: {value!r}"
    v = value.strip()
    if re.fullmatch(r"--[a-z0-9-]+", v, re.I):
        assert v in vars_, f"variabile {v} mancante"
        return _resolve(vars_[v], vars_, depth + 1)
    m = re.fullmatch(r"var\(\s*(--[a-z0-9-]+)\s*\)", v, re.I)
    if m:
        name = m.group(1)
        assert name in vars_, f"variabile {name} mancante"
        return _resolve(vars_[name], vars_, depth + 1)
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([0-9.]+)\s*)?\)", v)
    if m:
        r, g, b = (int(m.group(i)) for i in (1, 2, 3))
        return r, g, b, float(m.group(4)) if m.group(4) else 1.0
    s = v.lstrip("#")
    assert re.fullmatch(r"[0-9a-fA-F]{6}", s), f"colore non gestito: {value!r}"
    n = int(s, 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255, 1.0


def _flatten(color: tuple[int, int, int, float], bg: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b, a = color
    return tuple(round(a * c + (1 - a) * d) for c, d in zip((r, g, b), bg))


def _ratio(fg: str, bg: str, vars_: dict) -> float:
    """Contrasto WCAG del testo `fg` sul fondo `bg`; i colori traslucidi sono
    composti prima sul fondo e, se serve, il fondo sul `--paper`."""
    paper = _resolve(vars_["--paper"], vars_)
    assert paper[3] == 1.0, "--paper deve essere opaco"
    bg_rgb = _flatten(_resolve(bg, vars_), paper[:3])
    fg_rgb = _flatten(_resolve(fg, vars_), bg_rgb)
    return _contrast_rgb(fg_rgb, bg_rgb)


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


def _contrast_rgb(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    l1, l2 = _luminance(fg), _luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _contrast(fg: str, bg: str) -> float:
    return _contrast_rgb(_hex_to_rgb(fg), _hex_to_rgb(bg))


def _media_blocks(name: str) -> list[str]:
    """Contenuto di tutti i blocchi `@media (name) { ... }` con graffe bilanciate."""
    css = _css()
    out, idx = [], 0
    while True:
        start = css.find(f"@media ({name})", idx)
        if start == -1:
            return out
        i = css.find("{", start)
        depth, j = 1, i + 1
        while depth and j < len(css):
            depth += (css[j] == "{") - (css[j] == "}")
            j += 1
        out.append(css[i + 1 : j - 1])
        idx = j


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


# --- contrasto: tema Manga (predefinito) e superfici accese -----------------

def test_contrasto_testo_tema_manga():
    """Testo, testo secondario (rgba), rosso da testo e chip verde >= 4.5:1."""
    v = _manga_block()
    pairs = [
        ("--ink", "--paper"), ("--ink", "--paper-2"),
        ("--ink-soft", "--paper"), ("--ink-soft", "--paper-2"),
        ("--red-text", "--paper"), ("--red-text", "--paper-2"),
        ("--ok", "--ok-soft"),  # etichetta "salvato" su tinta verde tenue
    ]
    failures = [f"{fg} su {bg}: {_ratio(v[fg], v[bg], v):.2f}:1"
                for fg, bg in pairs if _ratio(v[fg], v[bg], v) < MIN_RATIO]
    assert failures == [], f"contrasto insufficiente nel tema Manga: {failures}"


def test_contrasto_bottoni_e_badge_tema_manga():
    """Bianco su rosso pieno, su ogni stop del gradiente del primario e
    inchiostro su oro (badge): tutti i testi >= 4.5:1."""
    v = _manga_block()
    m = re.search(r"\.btn-primary\s*\{([^}]*)\}", _css())
    assert m, "regola .btn-primary non trovata"
    stops = re.findall(r"#[0-9a-fA-F]{6}", m.group(1))
    assert len(stops) >= 2, "gradiente del primario senza stop esadecimali"
    checks = [("#ffffff", stop) for stop in stops]
    checks += [("#ffffff", "--red-deep"), ("--paper", "--gold")]
    failures = [f"{fg} su {bg}: {_ratio(fg, bg, v):.2f}:1"
                for fg, bg in checks if _ratio(fg, bg, v) < MIN_RATIO]
    assert failures == [], f"contrasto insufficiente su superfici accese: {failures}"


def test_contrasto_voci_attive_tema_pro():
    v = _theme_block()
    root = _manga_block()  # :root definisce --accent-on per entrambi i temi
    checks = [
        ("#ffffff", "--paper-3"),  # voce attiva del rail
        (root["--accent-on"], "#ffffff"),  # testo del bottone primario (fondo bianco)
        ("#d4d4d4", "#2b2b2b"),  # badge del masthead
    ]
    failures = [f"{fg} su {bg}: {_ratio(fg, bg, v):.2f}:1"
                for fg, bg in checks if _ratio(fg, bg, v) < MIN_RATIO]
    assert failures == [], f"contrasto insufficiente nel tema Pro: {failures}"


# --- tastiera / focus / reduced motion ---------------------------------------

def test_focus_visible_in_entrambi_i_temi():
    css = _css()
    assert re.search(r"(?m)^:focus-visible\s*\{[^}]*outline:\s*3px solid var\(--red\)", css), \
        "manca la regola base :focus-visible (tema Manga)"
    assert "html.theme-pro :focus-visible" in css, "manca il focus visibile del tema Pro"
    assert "html.theme-pro :focus-visible {\n  outline: 2px solid var(--red);" in css


def test_reduced_motion_spegne_animazioni_e_transizioni():
    blocks = "\n".join(_media_blocks("prefers-reduced-motion: reduce"))
    assert blocks, "nessun blocco prefers-reduced-motion in style.css"
    for sel in (".petal", ".card", ".file", ".btn", ".tab", ".seg-btn", ".toast"):
        assert sel in blocks, f"{sel} non coperto da prefers-reduced-motion"


def test_dialog_benvenuto_focus_iniziale_su_cta():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<button[^>]*id="welcomeOk"[^>]*>', html)
    assert m, "bottone #welcomeOk mancante"
    assert "autofocus" in m.group(0), "il dialog deve aprirsi col focus sulla CTA"
