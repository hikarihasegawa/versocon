"""Crea il pacchetto MSIX di VersoCon per Microsoft Store partendo dalla build PyInstaller.

Uso (dalla root del repo):
    python packaging/msix/build_msix.py --dist dist/Versocon --version 0.2.5 \
        --name "<Package/Identity/Name>" --publisher "<Package/Identity/Publisher>" \
        --publisher-display "<Package/Properties/PublisherDisplayName>" \
        --display-name "<nome riservato in Partner Center>" --out dist/VersoCon-0.2.5.msix

I valori di identita' si leggono in Partner Center > Product identity.
Richiede makeappx.exe (Windows SDK). Il pacchetto per lo Store non va firmato: lo firma Microsoft.
"""
from __future__ import annotations

import argparse
import glob
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
# Nome file -> dimensione (larghezza, altezza) richiesta dal manifest.
ASSETS = {
    "StoreLogo.png": (50, 50),
    "Square44x44Logo.png": (44, 44),
    "Square150x150Logo.png": (150, 150),
    "Wide310x150Logo.png": (310, 150),
}


def make_assets(dst: Path) -> None:
    ico = Image.open(ROOT / "packaging" / "versocon.ico")
    ico.size = max(ico.info["sizes"])  # frame piu' grande (256x256)
    src = ico.convert("RGBA")
    for name, (w, h) in ASSETS.items():
        side = min(w, h)
        icon = src.resize((side, side), Image.LANCZOS)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.paste(icon, ((w - side) // 2, (h - side) // 2), icon)
        canvas.save(dst / name)


def makeappx() -> str:
    found = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\makeappx.exe"))
    if not found:
        raise SystemExit("makeappx.exe non trovato: serve il Windows SDK")
    return found[-1]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dist", required=True, type=Path, help="cartella PyInstaller (contiene Versocon.exe)")
    ap.add_argument("--version", required=True, help="versione app, es. 0.2.5 (diventa 0.2.5.0)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--publisher", required=True)
    ap.add_argument("--publisher-display", required=True)
    ap.add_argument("--display-name", default="VersoCon", help="deve coincidere con un nome riservato nello Store")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    if not (args.dist / "Versocon.exe").is_file():
        raise SystemExit(f"Versocon.exe non trovato in {args.dist}")
    layout = args.out.parent / "msix-layout"
    shutil.rmtree(layout, ignore_errors=True)
    shutil.copytree(args.dist, layout)
    (layout / "Assets").mkdir()
    make_assets(layout / "Assets")

    manifest = (HERE / "AppxManifest.xml").read_text(encoding="utf-8")
    values = {
        "{NAME}": args.name,
        "{PUBLISHER}": args.publisher,
        "{PUBLISHER_DISPLAY}": args.publisher_display,
        "{DISPLAY_NAME}": args.display_name,
        "{VERSION}": f"{args.version}.0",  # lo Store richiede l'ultima cifra a 0
    }
    for key, val in values.items():
        manifest = manifest.replace(key, escape(val, {'"': "&quot;"}))
    (layout / "AppxManifest.xml").write_text(manifest, encoding="utf-8")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([makeappx(), "pack", "/d", str(layout), "/p", str(args.out), "/o"], check=True)
    print(f"MSIX creato: {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
