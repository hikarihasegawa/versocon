"""ARCH-1 UI: barra job globale (progresso + annulla) e chiavi i18n.

Controlli statici su index.html / app.js e presenza delle traduzioni `job.*`
in tutte le lingue della UI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STATIC = ROOT / "static"
I18N = STATIC / "i18n"
LANGS = ("it", "en", "es", "fr", "de", "pt", "zh", "ja")


def test_index_ha_barra_job():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for el in ['id="jobBar"', 'id="jobLabel"', 'id="jobProg"', 'id="jobCount"',
               'id="jobCancel"', 'data-i18n="job.cancel"']:
        assert el in html, f"{el} mancante"


def test_css_barra_job_nei_due_temi():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    for rule in [".jobbar", ".jobbar-prog", ".jobbar-count", ".jobbar-cancel"]:
        assert rule in css, f"{rule} mancante"


def test_app_js_usa_job_per_video_e_scan():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for s in ["function runJob", "function pollJob", "function jobTicker",
              '"/api/jobs/scan-clean"', '"/api/jobs/video-convert"',
              '"/api/jobs/video-audio"', '"/api/jobs/video-gif"',
              "`/api/jobs/${activeJob}/cancel`"]:
        assert s in js, f"{s} mancante in app.js"


def test_i18n_job_keys_tutte_le_lingue():
    keys = ["job.cancel", "job.cancelling", "job.cancelled", "job.running",
            "job.video", "job.audio", "job.gif", "job.scan", "job.scan_page",
            "job.busy", "api.job_not_found"]
    for lang in LANGS:
        data = json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))
        missing = [k for k in keys if not data.get(k)]
        assert missing == [], f"{lang}.json: mancano {missing}"
