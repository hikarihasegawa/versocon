"""VersoCon — lanciatore.

Preferisce una finestra desktop (pywebview); se non disponibile apre il
browser predefinito. Uso:
    python run.py                # finestra desktop o browser
    python run.py --browser      # forza browser
    python run.py --port 9000    # porta esplicita
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

import uvicorn

from app.main import app  # noqa: F401  (verifica import)

PORT = 8321
HOST = "127.0.0.1"


def _serve(host: str, port: int) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> int:
    args = sys.argv[1:]
    force_browser = "--browser" in args or os.environ.get("VERSOCON_BROWSER") == "1"

    if "--port" in args:
        global PORT
        PORT = int(args[args.index("--port") + 1])

    thread = threading.Thread(target=_serve, args=(HOST, PORT), daemon=True)
    thread.start()
    time.sleep(1.0)
    url = f"http://{HOST}:{PORT}/"

    if not force_browser:
        try:
            import webview

            # Abilita i download nativi: senza questo pywebview (WebView2)
            # *cancella* ogni download e l'app non salva mai i file.
            webview.settings["ALLOW_DOWNLOADS"] = True

            webview.create_window("VersoCon", url, width=860, height=860,
                                  background_color="#0b0b1e")
            webview.start()
            return 0
        except Exception:  # noqa: BLE001
            pass

    webbrowser.open(url)
    print(f"VersoCon in ascolto su {url}  (Ctrl+C per uscire)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
