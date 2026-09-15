"""Una sola versione: backend (/api/config), footer della UI e installer devono coincidere."""
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from app import version as app_version  # noqa: E402


def test_version_py_is_single_source():
    """app/version.py è la fonte: valore valido e identico a /api/config."""
    src = (ROOT / "app" / "version.py").read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', src, re.M)
    assert m, "app/version.py deve definire __version__"
    assert re.fullmatch(r"\d+\.\d+\.\d+", m.group(1))
    assert app_version.__version__ == app.version


def test_main_does_not_hardcode_version():
    main_src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert not re.search(r'version\s*=\s*"0\.\d', main_src)


def test_config_exposes_version():
    assert TestClient(app).get("/api/config").json()["version"] == app.version


def test_footer_fallback_matches_backend_version():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    m = re.search(r'id="appVersion">v([^<]+)<', html)
    assert m and m.group(1) == app.version


def test_installer_version_matches_backend():
    iss = (ROOT / "packaging" / "inno" / "versocon.iss").read_text(encoding="utf-8")
    m = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', iss)
    assert m and m.group(1) == app.version
