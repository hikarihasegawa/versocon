"""Test per generatorsign (firma calligrafica da testo)."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converters import sign  # noqa: E402


def _png(data: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(data))
    im.load()
    return im


def test_list_styles_ordinati():
    keys = [s.key for s in sign.list_styles()]
    assert keys == ["caveat", "dancing", "greatvibes", "pacifico",
                    "pinyon", "allura", "parisienne", "sigla"]
    assert all(s.label for s in sign.list_styles())


@pytest.mark.parametrize("key", ["caveat", "dancing", "greatvibes", "pacifico",
                                 "pinyon", "allura", "parisienne", "sigla"])
def test_generate_each_style(key):
    data = sign.generate("Mario Rossi", style=key)
    im = _png(data)
    assert im.mode == "RGBA"
    assert im.width >= 40 and im.height >= 40
    # deve essere effettivamente trasparente almeno in un angolo
    corner = im.getpixel((0, 0))
    assert corner[3] == 0, f"angolo non trasparente in {im}"


def test_sigla_riduce_il_nome_alle_iniziali():
    assert sign._initials("Mario Rossi") == "M.R."
    assert sign._initials("  anna   maria  ") == "A.M."
    assert sign._initials("Cher") == "C."
    assert sign._initials("Èlena D'Angelo") == "È.D."
    assert sign._initials("'Ndrangheta Rossi") == "N.R."


def test_sigla_ignora_parole_senza_lettere():
    assert sign._initials("Mario *** Rossi 42") == "M.R."
    with pytest.raises(ValueError, match="iniziali"):
        sign._initials("*** 123!!!")
    with pytest.raises(ValueError, match="iniziali"):
        sign.generate("***", style="sigla")


def test_sigla_e_piu_corta_del_nome_intero_stesso_font():
    # "sigla" usa Pinyon Script: il PNG delle iniziali deve essere più stretto
    # della firma completa con lo stesso font, a parità di altezza.
    full = _png(sign.generate("Mario Rossi", style="pinyon", height=120))
    sigla = _png(sign.generate("Mario Rossi", style="sigla", height=120))
    assert sigla.width < full.width


def test_height_param_is_respected():
    small = _png(sign.generate("Mario Rossi", height=60))
    big = _png(sign.generate("Mario Rossi", height=240))
    assert small.height < big.height


def test_different_styles_give_different_footprint():
    # gli stili non devono essere tutti identici di dimensione
    sizes = {
        k: _png(sign.generate("Mario Rossi", style=k, height=120)).width
        for k in ["caveat", "dancing", "greatvibes", "pacifico"]
    }
    assert len(set(sizes.values())) >= 3


def test_generate_rejects_empty_name():
    with pytest.raises(ValueError):
        sign.generate("")
    with pytest.raises(ValueError):
        sign.generate("   ")


def test_generate_rejects_unknown_style():
    with pytest.raises(ValueError):
        sign.generate("x", style="nope")


def test_generate_rejects_too_long_name():
    with pytest.raises(ValueError):
        sign.generate("a" * 300)


def _ink_sample(data: bytes) -> tuple[int, int, int]:
    """PRIMO pixel (R,G,B) che NON è background trasparente (alpha=0)."""
    im = _png(data).convert("RGBA")
    for px in im.getdata():
        if px[3] != 0:
            return (px[0], px[1], px[2])
    return (0, 0, 0)


def test_color_default_is_black():
    assert _ink_sample(sign.generate("Mario Rossi")) == (0, 0, 0)


def test_color_parameter_tinted():
    rgb = _ink_sample(sign.generate("Mario Rossi", color="#0000ff"))
    assert rgb[2] > 0 and rgb[0] < 80 and rgb[1] < 80, f"blu atteso, ottenuto {rgb}"


def test_color_rejects_invalid():
    with pytest.raises(ValueError):
        sign.generate("x", color="#zzz")
    with pytest.raises(ValueError):
        sign.generate("x", color="")


def test_fonts_are_bundled():
    # il bundle OTF deve essere presente in assets/fonts/ — se sparisce,
    # la feature è rotta e questo test lo segnala subito.
    for st in sign.list_styles():
        p = sign.FONTS_DIR / st.file
        assert p.exists(), f"font mancante in bundle: {p}"
