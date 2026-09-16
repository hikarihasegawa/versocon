"""Guardia di packaging: ogni dipendenza importata dall'app deve stare nel lock.

Bundle PyInstaller e pacchetto MSIX si costruiscono da `requirements-lock.txt`.
Se una dipendenza runtime entra nel codice ma non nel lock (o lo spec smette di
includerla), l'artefatto esce mutilato: qui il controllo statico, nel turno di
rilascio, mentre l'esecuzione reale del bundle è verificata prima del tag.
"""
import ast
import re
import sys
from pathlib import Path

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
