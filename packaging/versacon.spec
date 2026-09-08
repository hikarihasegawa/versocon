# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller — VersoCon (on-dire, Windows).

Esecuzione:
    .venv\\Scripts\\pyinstaller packaging\\versacon.spec --noconfirm --clean

Produce:  dist\\Versocon\\Versocon.exe  +  dist\\Versocon\\_internal\
"""
from pathlib import Path

ROOT = Path(SPECPATH).parent
STATIC = ROOT / "static"
FONTS  = ROOT / "assets" / "fonts"
ICO    = Path(SPECPATH) / "versocon.ico"

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(STATIC), "static"),
        (str(FONTS),  "assets/fonts"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "uvicorn._compat",
        "uvicorn._compat.loop",
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "webview.platforms.winforms.gui",
        "fastapi",
        "multipart",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "PIL.ImageFont",
        "heif",
        "fitz",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "pygments"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Versocon",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,             # nessuna console: app desktop
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICO),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Versocon",
)
