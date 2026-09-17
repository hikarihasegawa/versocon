"""Config pytest condivisa.

Il TestClient di Starlette invia `Host: testserver`: lo ammettiamo SOLO nei
test, prima che `app.main` venga importato dai moduli di test.
"""
import os

import pytest

os.environ.setdefault("VERSOCON_EXTRA_HOSTS", "testserver")

_ENGINE_ENV_VARS = ("TESSERACT_CMD", "TESSDATA_PREFIX")


@pytest.fixture(autouse=True)
def _isolate_engine_env():
    """Nessun test può lasciare TESSERACT_CMD/TESSDATA_PREFIX sporchi.

    La risoluzione dei motori scrive queste variabili nel processo: senza
    isolamento un bundle finto risolto in un test faceva fallire l'OCR dei test
    successivi (CI Ubuntu, 2026-09-17). `reset_ocr_cache` ripristina i valori
    salvati dal prodotto; qui li ripristiniamo comunque, per ogni test.
    """
    from converters import extract as _extract

    saved = {k: os.environ.get(k) for k in _ENGINE_ENV_VARS}
    _extract.reset_ocr_cache()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _extract.reset_ocr_cache()
