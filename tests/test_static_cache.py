"""Asset statici: il browser deve sempre rivalidarli (ETag → 304 se invariati).

Senza `Cache-Control` i browser usano la cache euristica e possono continuare a
mostrare style.css/app.js vecchi dopo un aggiornamento (bug visto dall'utente).
"""
from fastapi.testclient import TestClient

from app.main import app

PATHS = ("/", "/style.css", "/app.js", "/theme.js", "/i18n/it.json", "/fonts/InterVariable.woff2")


def test_asset_statici_sempre_rivalidati():
    client = TestClient(app)
    for path in PATHS:
        res = client.get(path)
        assert res.status_code == 200, path
        assert res.headers.get("cache-control") == "no-cache", f"{path}: manca Cache-Control no-cache"
        assert res.headers.get("etag"), f"{path}: manca ETag per la rivalidazione"


def test_rivalidazione_risponde_304():
    client = TestClient(app)
    res = client.get("/style.css")
    res2 = client.get("/style.css", headers={"If-None-Match": res.headers["etag"]})
    assert res2.status_code == 304
