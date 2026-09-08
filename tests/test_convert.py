"""Test di conversione immagini (con HEIC sintetico via pillow-heif)."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from converters import images as imgconv  # noqa: E402
from PIL import Image  # noqa: E402


def _png_bytes(size=(64, 64), color=(255, 106, 133)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _heic_bytes() -> bytes:
    import pillow_heif

    img = Image.new("RGB", (48, 48), (40, 200, 160))
    bio = io.BytesIO()
    pillow_heif.from_pillow(img).save(bio)
    return bio.getvalue()


@pytest.mark.parametrize("out", ["jpeg", "png", "webp", "jpg"])
def test_convert_common_formats(out: str):
    out_bytes = imgconv.convert_bytes(_png_bytes(), out)
    im = Image.open(io.BytesIO(out_bytes))
    im.verify()
    if out in ("jpeg", "jpg"):
        assert Image.open(io.BytesIO(out_bytes)).format == "JPEG"
    elif out == "png":
        assert Image.open(io.BytesIO(out_bytes)).format == "PNG"
    else:
        assert Image.open(io.BytesIO(out_bytes)).format == "WEBP"


def test_convert_heic_to_jpeg():
    out = imgconv.convert_bytes(_heic_bytes(), "jpeg")
    im = Image.open(io.BytesIO(out))
    assert im.format == "JPEG"
    assert im.size == (48, 48)


def test_convert_heic_preserves_alpha_to_png():
    img = Image.new("RGBA", (32, 32), (10, 20, 30, 128))
    import pillow_heif

    bio = io.BytesIO()
    pillow_heif.from_pillow(img).save(bio)
    out = imgconv.convert_bytes(bio.getvalue(), "png")
    im = Image.open(io.BytesIO(out))
    assert im.format == "PNG"
    assert im.mode == "RGBA"


@pytest.mark.parametrize("src", [".heic", ".heif", ".jpg", ".png", ".webp", ".bmp", ".tiff", ".gif"])
def test_is_convertible(src: str):
    assert imgconv.is_convertible(f"foto{src}")


def test_bad_output_format_raises():
    with pytest.raises(ValueError):
        imgconv.convert_bytes(_png_bytes(), "tiff")


def test_output_ext():
    assert imgconv.output_ext("jpeg") == "jpg"
    assert imgconv.output_ext("png") == "png"
    assert imgconv.output_ext("webp") == "webp"


def test_max_side_downscales_longest_only():
    out = imgconv.convert_bytes(_png_bytes(size=(200, 100)), "jpeg", max_side=100)
    im = Image.open(io.BytesIO(out))
    assert im.size == (100, 50)


def test_max_side_noop_when_smaller():
    out = imgconv.convert_bytes(_png_bytes(size=(40, 20)), "jpeg", max_side=100)
    im = Image.open(io.BytesIO(out))
    assert im.size == (40, 20)


def test_quality_lower_than_higher_yields_smaller_jpeg():
    low = imgconv.convert_bytes(_png_bytes(size=(256, 256)), "jpeg", quality=20)
    high = imgconv.convert_bytes(_png_bytes(size=(256, 256)), "jpeg", quality=95)
    assert len(low) < len(high)


def test_quality_clamped_to_1_100():
    assert imgconv._clamp_quality(0) == 1
    assert imgconv._clamp_quality(150) == 100
    assert imgconv._clamp_quality(None) == imgconv.JPEG_QUALITY
    assert imgconv._clamp_quality("xx") == imgconv.JPEG_QUALITY


def test_max_side_also_applies_to_png_output():
    out = imgconv.convert_bytes(_png_bytes(size=(200, 100)), "png", max_side=50)
    im = Image.open(io.BytesIO(out))
    assert im.size == (50, 25)


def test_max_side_zero_or_negative_means_no_resize():
    for bad in (0, -5):
        out = imgconv.convert_bytes(_png_bytes(size=(120, 80)), "jpeg", max_side=bad)
        assert Image.open(io.BytesIO(out)).size == (120, 80)


def _exif_bytes(orientation: int) -> bytes:
    """EXIF minimo con solo il tag orientation."""
    from PIL import Image as _I

    e = _I.Exif()
    e[0x0112] = orientation
    return e.tobytes()


def _png_with_exif(w, h, exif_bytes):
    im = Image.new("RGB", (w, h), (200, 40, 40))
    buf = io.BytesIO()
    im.save(buf, format="PNG", exif=exif_bytes)
    return buf.getvalue()


def test_exif_orientation_applies_rotation_to_jpeg():
    # 100x50 con orientation 6 (ruota 90) -> output 50x100
    src = _png_with_exif(100, 50, _exif_bytes(6))
    out = imgconv.convert_bytes(src, "jpeg")
    r = Image.open(io.BytesIO(out))
    assert r.size == (50, 100)
    # orientation normalizzata a 1
    assert r.getexif().get(0x0112) == 1


def test_exif_orientation_preserved_when_none():
    # orientation 1 (nessuna rotazione) -> dimensioni invariate, tag presente
    src = _png_with_exif(80, 60, _exif_bytes(1))
    out = imgconv.convert_bytes(src, "jpeg")
    r = Image.open(io.BytesIO(out))
    assert r.size == (80, 60)
    assert r.getexif().get(0x0112) == 1


def test_exif_data_carried_to_output():
    # un tag EXIF arbitrario (Artist) deve sopravvivere alla conversione JPEG
    im = Image.new("RGB", (40, 40), (1, 2, 3))
    e = Image.Exif()
    e[0x013B] = "VersoCon"  # Artist
    src = _png_with_exif(40, 40, e.tobytes())
    out_j = imgconv.convert_bytes(src, "jpeg")
    assert Image.open(io.BytesIO(out_j)).getexif().get(0x013B) == "VersoCon"


def test_animated_gif_preserves_frames():
    frames = [
        Image.new("P", (30, 30), (0, 0, 0)).convert("RGB").convert("P"),
        Image.new("P", (30, 30), (255, 0, 0)).convert("RGB").convert("P"),
        Image.new("P", (30, 30), (0, 255, 0)).convert("RGB").convert("P"),
    ]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   duration=100, loop=0)
    src = buf.getvalue()
    out = imgconv.convert_bytes(src, "gif")
    r = Image.open(io.BytesIO(out))
    assert r.format == "GIF"
    assert getattr(r, "n_frames", 1) == 3


def test_static_gif_from_single_frame():
    out = imgconv.convert_bytes(_png_bytes(size=(24, 24)), "gif")
    r = Image.open(io.BytesIO(out))
    assert r.format == "GIF"
    assert r.size == (24, 24)


def test_gif_max_side_scales_frames():
    frames = [
        Image.new("RGB", (200, 100), (10, 20, 30)).convert("P"),
        Image.new("RGB", (200, 100), (60, 60, 60)).convert("P"),
    ]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   duration=80, loop=0)
    out = imgconv.convert_bytes(buf.getvalue(), "gif", max_side=100)
    r = Image.open(io.BytesIO(out))
    assert r.size == (100, 50)
    assert getattr(r, "n_frames", 1) == 2


def test_multipage_tiff_first_frame_to_jpeg():
    # TIFF multi-frame: verso JPEG usa il primo frame (single-frame output)
    p1 = Image.new("RGB", (50, 30), (5, 5, 5))
    p2 = Image.new("RGB", (50, 30), (90, 90, 90))
    buf = io.BytesIO()
    p1.save(buf, format="TIFF", save_all=True, append_images=[p2])
    out = imgconv.convert_bytes(buf.getvalue(), "jpeg")
    r = Image.open(io.BytesIO(out))
    assert r.format == "JPEG"
    assert r.size == (50, 30)


def test_bad_output_format_raises_includes_gif_now_valid():
    # gif è ora formato di uscita valido
    assert imgconv.output_ext("gif") == "gif"
    # tiff resta non supportato come output
    with pytest.raises(ValueError):
        imgconv.convert_bytes(_png_bytes(), "tiff")
