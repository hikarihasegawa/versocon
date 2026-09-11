"""Programmi esterni (tesseract, ffmpeg) avviati senza finestra di console.

L'exe di VersoCon non ha console: su Windows ogni programma a riga di comando
lanciato da lì apre per un attimo una finestra cmd/Terminale. Il flag
CREATE_NO_WINDOW la evita; sugli altri sistemi non serve nulla.
"""
from __future__ import annotations

import subprocess
import sys

NO_WINDOW: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
