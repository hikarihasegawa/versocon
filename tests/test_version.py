"""Una sola versione: backend (/api/config), footer della UI e installer devono coincidere."""
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


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
