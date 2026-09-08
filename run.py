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
import urllib.request
import webbrowser

import uvicorn

from app.main import app  # noqa: F401  (verifica import)

PORT = 8321
HOST = "127.0.0.1"


def _serve(host: str, port: int) -> None:
    uvicorn.run(app, host=host, port=port, log_level="info")


def _wait_until_ready(host: str, port: int, timeout: float = 30.0) -> None:
    """Blocks until the local server answers a HTTP 200 on / — or times out."""
    url = f"http://{host}:{port}/"
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.4) as r:
                if 200 <= r.status < 300:
                    return
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(0.15)
    raise TimeoutError(
        f"VersoCon: server locale non pronto in {timeout:.0f}s su {HOST}:{PORT}. "
        f"Ultimo errore: {last_err}"
    )


def main() -> int:
    args = sys.argv[1:]
    force_browser = "--browser" in args or os.environ.get("VERSOCON_BROWSER") == "1"

    if "--port" in args:
        global PORT
        PORT = int(args[args.index("--port") + 1])

    thread = threading.Thread(target=_serve, args=(HOST, PORT), daemon=True)
    thread.start()

    # Attendiamo che il server risponda davvero (non "dopo 1 secondo").
    # In una macchina con disco/antivirus lento questo può richiedere qualche
    # secondo: il loop sotto è la soluzione.
    try:
        _wait_until_ready(HOST, PORT)
    except TimeoutError as e:
        print(str(e))
        print("Riprova chiudendo e riaprendo VersoCon. Se torna, verifica che"
              " il firewall non blocchi la porta 127.0.0.1:", str(PORT))
        input("Premi INVIO per uscire (il server continua a girare per qualche secondo)...")
        return 1

    url = f"http://{HOST}:{PORT}/"

    if not force_browser:
        try:
            import webview

            webview.settings["ALLOW_DOWNLOADS"] = True
            webview.create_window("VersoCon", url, width=860, height=860,
                                  background_color="#f7f2e9")
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
