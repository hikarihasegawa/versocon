"""Guardia di packaging: ogni dipendenza importata dall'app deve stare nel lock.

Bundle PyInstaller e pacchetto MSIX si costruiscono da `requirements-lock.txt`.
Se una dipendenza runtime entra nel codice ma non nel lock (o lo spec smette di
includerla), l'artefatto esce mutilato: qui il controllo statico, nel turno di
rilascio, mentre l'esecuzione reale del bundle è verificata prima del tag.
"""
import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "run.py", *sorted((ROOT / "app").glob("*.py")), *sorted((ROOT / "converters").glob("*.py"))]
LOCAL = {"app", "converters"}
IMPORT_TO_DIST = {
    "PIL": "pillow",
    "cv2": "opencv-python-headless",
    "pillow_heif": "pillow-heif",
    "webview": "pywebview",
}


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _lock_distributions() -> set[str]:
    out = set()
    for line in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(_canon(line.split("==", 1)[0]))
    return out


def _runtime_imports() -> set[str]:
    names: set[str] = set()
    for f in SOURCES:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return {n for n in names if n not in sys.stdlib_module_names and n not in LOCAL}


def test_import_runtime_tutti_nel_lockfile():
    lock = _lock_distributions()
    missing = {}
    for mod in sorted(_runtime_imports()):
        dist = _canon(IMPORT_TO_DIST.get(mod, mod))
        if dist not in lock:
            missing[mod] = dist
    assert not missing, f"import fuori da requirements-lock.txt: {missing}"


def test_spec_include_esplicitamente_cv2_e_numpy():
    spec = (ROOT / "packaging" / "versacon.spec").read_text(encoding="utf-8")
    assert '"cv2"' in spec and '"numpy"' in spec


def test_msix_copia_lintero_dist_senza_filtrare_file():
    """Se un giorno il builder filtrasse i file, le dipendenze sparirebbero dal pacchetto."""
    src = (ROOT / "packaging" / "msix" / "build_msix.py").read_text(encoding="utf-8")
    assert "shutil.copytree(args.dist, layout)" in src


def _bundle_engines():
    """Carica packaging/bundle_engines.py senza dipendere dal sys.path dei test."""
    path = ROOT / "packaging" / "bundle_engines.py"
    spec = importlib.util.spec_from_file_location("bundle_engines", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_engine_datas_vuoto_senza_variabili():
    be = _bundle_engines()
    assert be.engine_datas({}) == []
    assert be.engine_datas({"VERSOCON_TESSERACT_DIR": "", "VERSOCON_FFMPEG_DIR": "  "}) == []


def test_engine_datas_mappa_le_cartelle(tmp_path):
    be = _bundle_engines()
    tess, ff = tmp_path / "tess", tmp_path / "ff"
    tess.mkdir(), ff.mkdir()
    assert be.engine_datas(
        {"VERSOCON_TESSERACT_DIR": str(tess), "VERSOCON_FFMPEG_DIR": str(ff)}
    ) == [(str(tess), "tesseract"), (str(ff), "ffmpeg")]


def test_engine_datas_cartella_invalida_fallisce():
    be = _bundle_engines()
    with pytest.raises(ValueError):
        be.engine_datas({"VERSOCON_TESSERACT_DIR": r"C:\cartella\che\non\esiste"})


def test_engine_datas_release_senza_motori_fallisce():
    """Un rilascio non deve poter uscire senza i motori."""
    be = _bundle_engines()
    with pytest.raises(ValueError):
        be.engine_datas({"VERSOCON_REQUIRE_ENGINES": "1"})
    assert be.engine_datas({"VERSOCON_REQUIRE_ENGINES": "0"}) == []


def test_spec_impacchetta_motori_da_env():
    spec = (ROOT / "packaging" / "versacon.spec").read_text(encoding="utf-8")
    assert "from bundle_engines import engine_datas" in spec
    assert "+ engine_datas()" in spec


def test_fetch_engines_pinna_versioni_e_sha256():
    """I motori di release sono pinnati: niente URL mobili, hash verificati."""
    script = (ROOT / "packaging" / "fetch_engines.ps1").read_text(encoding="utf-8")
    assert "5.5.3.20260724" in script
    assert "8.1.2-essentials_build.zip" in script
    assert len(re.findall(r"[0-9A-F]{64}", script)) >= 2  # ita + ffmpeg
    for line in script.splitlines():
        if "http" in line:
            assert "latest" not in line.lower(), line
    assert "VERSOCON_REQUIRE_ENGINES=1" in script


def test_release_e_msix_scaricano_i_motori():
    for wf in ("release.yml", "msix.yml"):
        text = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
        assert "packaging/fetch_engines.ps1" in text, wf


def test_licenze_terze_parti_nel_bundle():
    """I motori inclusi sono distribuiti: licenze e nota di terze parti devono esserci."""
    spec = (ROOT / "packaging" / "versacon.spec").read_text(encoding="utf-8")
    assert '(str(LICENSES), "licenses")' in spec

    lic = ROOT / "packaging" / "licenses"
    for name, min_size in (
        ("Apache-2.0.txt", 10000),
        ("BSD-2-Clause-Leptonica.txt", 1000),
        ("GPL-3.0.txt", 30000),
        ("THIRD-PARTY-NOTICES.txt", 500),
    ):
        f = lic / name
        assert f.is_file(), name
        assert f.stat().st_size >= min_size, name

    notices = (lic / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    for needle in ("Tesseract", "Apache", "Leptonica", "BSD", "FFmpeg", "GPL"):
        assert needle in notices, needle
    assert "ffmpeg.org" in notices

    iss = (ROOT / "packaging" / "inno" / "versocon.iss").read_text(encoding="utf-8")
    assert "THIRD-PARTY-NOTICES.txt" in iss
