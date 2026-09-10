"""Config pytest condivisa.

Il TestClient di Starlette invia `Host: testserver`: lo ammettiamo SOLO nei
test, prima che `app.main` venga importato dai moduli di test.
"""
import os

os.environ.setdefault("VERSOCON_EXTRA_HOSTS", "testserver")
