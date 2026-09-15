"""Font Inter del tema Pro: bundle locale offline, licenza OFL e stack.

Il riferimento DeepSeek carica Inter (400/500/600) da CDN; qui il file è
bundled in `static/fonts/` così l'app resta offline e senza terze parti.
"""
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


def _css() -> str:
    return (STATIC / "style.css").read_text(encoding="utf-8")


def test_font_file_bundled():
    f = STATIC / "fonts" / "InterVariable.woff2"
    assert f.is_file(), "manca static/fonts/InterVariable.woff2"
    data = f.read_bytes()
    assert data[:4] == b"wOF2", "il file non è un WOFF2 valido"
    assert len(data) > 200_000, "font sospettosamente piccolo (file troncato?)"


def test_font_license_present():
    lic = (STATIC / "fonts" / "LICENSE-Inter.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in lic
    assert "Inter Project Authors" in lic


def test_font_face_local_only():
    css = _css()
    m = re.search(r"@font-face\s*\{(.*?)\}", css, re.S)
    assert m, "@font-face per Inter mancante in style.css"
    block = m.group(1)
    assert '"Inter"' in block
    assert 'url("fonts/InterVariable.woff2")' in block
    assert "http" not in block, "il font non deve puntare a risorse remote"
    rest = css.replace(block, "")
    assert "url(" not in rest, "nessun'altra risorsa remota attesa in style.css"


def test_theme_pro_usa_inter_per_primo():
    m = re.search(r"html\.theme-pro\s*\{(.*?)\}", _css(), re.S)
    assert m, "blocco html.theme-pro non trovato"
    for var in ("--font", "--font-title"):
        v = re.search(rf"{var}\s*:\s*([^;]+);", m.group(1))
        assert v, f"{var} mancante nel tema Pro"
        assert v.group(1).strip().startswith('"Inter"'), f"{var} non parte da Inter"
