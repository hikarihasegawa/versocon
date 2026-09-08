"""Genera pack/versocon.ico + static/logo.png dallo stile in-app (hanko)."""
import math
from PIL import Image, ImageDraw, ImageFont

OUT_ICO = "packaging/versocon.ico"
OUT_PNG = "static/logo.png"

RED = (239, 74, 60)
RED_DARK = (188, 40, 32)
WHITE = (255, 255, 255)
FONT_PATH = "C:/Windows/Fonts/yugothb.ttc"


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size - 1), radius, fill=255)
    return m


def render(sz):
    S = sz * 4  # supersampling antialiased
    pad = S // 8
    r = S // 6
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle((pad, pad, S - 1 - pad, S - 1 - pad), r, fill=RED)
    # frame interno bianco 60%
    inset = max(S // 12, 2)
    fr = max(S // 60, 1)
    d.rounded_rectangle(
        (pad + S // 10, pad + S // 10, S - 1 - (pad + S // 10), S - 1 - (pad + S // 10)),
        max(r - S // 18, 2),
        outline=(255, 255, 255, 153),
        width=fr,
    )
    fs = int(S * 0.42)
    font = ImageFont.truetype(FONT_PATH, fs)
    text = "変"
    bb = font.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    cx = (S - tw) // 2 + -bb[0]
    cy = (S - th) // 2 + -bb[1] + S // 250
    d.text((cx, cy), text, font=font, fill=WHITE)
    # composita su rosso ALTA risoluzione: niente fringing scuro al downscale
    plate = Image.new("RGBA", (S, S), RED + (255,))
    plate.paste(bg, (0, 0), bg)
    plate = plate.resize((sz, sz), Image.LANCZOS)
    # maschera rounded alla dimensione finale: angoli puliti e trasparenti
    plate.putalpha(rounded_mask(sz, max(int(sz / 6), 2)))
    return plate


def main():
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    img = render(256)
    img.save(OUT_ICO, sizes=[(s, s) for s in sizes])
    render(512).save(OUT_PNG)
    im2 = Image.open(OUT_ICO)
    print("OK", OUT_ICO, im2.ico.sizes(), OUT_PNG)


if __name__ == "__main__":
    main()
