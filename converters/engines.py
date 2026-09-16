"""Ricerca dei motori esterni (ffmpeg, Tesseract).

I motori **inclusi nel pacchetto** hanno la precedenza: la ricerca guarda per
prima `_internal/tesseract`, `_internal/ffmpeg` e `bin/` accanto all'eseguibile
(bundle PyInstaller onedir e bundle portable), così l'app funziona out-of-the-box
senza installazioni separate. Solo se il bundle non c'è si cerca sul sistema.

`shutil.which` da solo non basta su Windows: l'installer winget in modalità
utente mette nel PATH la cartella *radice* del pacchetto e non `...\\bin`,
quindi il binario non viene mai trovato (bug noto winget-cli#2909). La ricerca
qui guarda anche le cartelle di shim dei gestori di pacchetti (WinGet Links,
Chocolatey, Scoop), i pacchetti WinGet installati per l'utente e le cartelle di
installazione comuni: l'app trova i motori anche se il PATH del processo è
vecchio o incompleto.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

# Pacchetti winget installati per-utente che contengono i motori.
_PACKAGE_GLOBS = (
    "Gyan.FFmpeg_*",
    "UB-Mannheim.TesseractOCR_*",
    "tesseract-ocr.tesseract_*",
)


def bundled_dirs() -> list[Path]:
    """Cartelle dei motori inclusi nel pacchetto, in ordine di priorità.

    PyInstaller onedir mette gli asset in `_internal` (`sys._MEIPASS`), quindi
    i motori vivono in `_internal/tesseract`, `_internal/ffmpeg` e
    `_internal/bin`; le stesse sottocartelle accanto all'exe coprono i bundle
    portable. La ricerca dei motori usa prima queste, poi il sistema.
    """
    dirs: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        dirs += [base / "tesseract", base / "ffmpeg", base / "bin"]
    exe_dir = Path(sys.executable).parent
    dirs += [exe_dir / "tesseract", exe_dir / "ffmpeg", exe_dir / "bin"]
    return dirs


def app_dirs() -> list[Path]:
    """Cartelle di fallback accanto all'app: radice, `bin/` e `tools/`."""
    dirs: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(Path(meipass))
    exe_dir = Path(sys.executable).parent
    dirs += [exe_dir, exe_dir / "bin", exe_dir / "tools"]
    return dirs


def _package_bins(packages: Path) -> list[Path]:
    """`.../WinGet/Packages/<Id>_*/.../bin` dei motori noti (vuoto se assente)."""
    out: list[Path] = []
    if not packages.is_dir():
        return out
    for pattern in _PACKAGE_GLOBS:
        for pkg in sorted(packages.glob(pattern)):
            out += sorted(pkg.glob("**/bin"))
    return out


def search_dirs(
    env: Mapping[str, str] | None = None, home: Path | None = None
) -> list[Path]:
    """Cartelle in cui cercare i binari, in ordine di priorità."""
    e: Mapping[str, str] = os.environ if env is None else env
    if home is None:
        home = Path(e["USERPROFILE"]) if e.get("USERPROFILE") else Path.home()
    dirs = app_dirs()
    local = e.get("LOCALAPPDATA")
    if local:
        base = Path(local)
        dirs.append(base / "Microsoft" / "WinGet" / "Links")
        dirs += _package_bins(base / "Microsoft" / "WinGet" / "Packages")
        dirs.append(base / "Programs" / "Tesseract-OCR")
    progdata = e.get("ProgramData")
    if progdata:
        dirs.append(Path(progdata) / "chocolatey" / "bin")
    dirs.append(home / "scoop" / "shims")
    progfiles = e.get("ProgramFiles")
    if progfiles:
        pf = Path(progfiles)
        dirs += [pf / "Tesseract-OCR", pf / "ffmpeg" / "bin"]
    progfiles86 = e.get("ProgramFiles(x86)")
    if progfiles86:
        dirs.append(Path(progfiles86) / "Tesseract-OCR")
    dirs += [
        Path("C:/ffmpeg/bin"),
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/opt/tesseract"),
    ]
    return dirs


def _iter_in_dirs(
    dirs: Iterable[Path], names: Sequence[str], seen: set[str]
) -> Iterator[str]:
    """Percorsi esistenti `dir/name` non ancora visti, aggiornando `seen`."""
    for d in dirs:
        for name in names:
            p = d / name
            try:
                ok = p.is_file()
            except OSError:
                ok = False
            if ok and str(p) not in seen:
                seen.add(str(p))
                yield str(p)


def iter_candidates(
    names: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    extra_dirs: Sequence[str | Path] | None = None,
) -> Iterator[str]:
    """Percorsi candidati per i nomi dati, in ordine di priorità.

    Ordine: cartelle bundle (`_internal/tesseract`, `_internal/ffmpeg`,
    `bin/`), PATH, `extra_dirs`, cartelle dei gestori pacchetti e cartelle
    comuni. I motori inclusi nel pacchetto vincono su quelli di sistema. Un
    percorso rotto (esiste ma non parte) resta compito del chiamante: qui si
    verifica solo l'esistenza.
    """
    seen: set[str] = set()
    yield from _iter_in_dirs(bundled_dirs(), names, seen)
    for name in names:
        if env is None:
            found = shutil.which(name)
        else:
            found = shutil.which(name, path=env.get("PATH", ""))
        if found and found not in seen:
            seen.add(found)
            yield found
    dirs = [Path(d) for d in (extra_dirs or [])]
    dirs += search_dirs(env=env)
    yield from _iter_in_dirs(dirs, names, seen)


def find_binary(
    names: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    extra_dirs: Sequence[str | Path] | None = None,
) -> str | None:
    """Percorso del primo binario esistente tra `names`, oppure None."""
    return next(iter_candidates(names, env=env, extra_dirs=extra_dirs), None)
