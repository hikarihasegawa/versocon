"""VersoCon — lanciatore.

Preferisce una finestra desktop (pywebview); se non disponibile apre il
browser predefinito. Uso:
    python run.py                # finestra desktop o browser, porta scelta dal SO
    python run.py --browser      # forza browser
    python run.py --port 9000    # forza una porta esplicita
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser

import uvicorn

from app.main import app  # noqa: F401  (verifica import)

HOST = "127.0.0.1"
# 0 = il SO sceglie una porta libera garantita: l'app funziona anche se 8321
# (o qualsiasi altra) è già occupata su quella macchina.
PORT = 0

_CRASH_LOG = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                          "Temp", "VersoCon", "crash.log")


def _crash(msg: str) -> None:
    """Logga su console E %LOCALAPPDATA%\\Temp\\VersoCon\\crash.log."""
    print(msg)
    try:
        os.makedirs(os.path.dirname(_CRASH_LOG), exist_ok=True)
        with open(_CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n{msg}\n")
    except OSError:
        pass


def _sys_excepthook(exc_type, exc, tb) -> None:
    _crash("Uncaught exception:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))


def _start_server(port: int):
    """Avvia uvicorn in un daemon-thread su 127.0.0.1.

    `port==0` → il SO sceglie una porta libera garantita (nessuna collisione
    possibile, nessun ri-bind esterno = nessun race). Ritorna l'istanza Server.
    """
    config = uvicorn.Config(app, host=HOST, port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    server.handle_signals = lambda: None  # serve() in un thread non-main deve ignorare i segnali
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_until_complete, args=(server.serve(),), daemon=True).start()
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        if server.should_exit:
            raise RuntimeError("uvicorn si è chiuso in fase di avvio")
        if server.started:
            return server
        time.sleep(0.1)
    raise TimeoutError("uvicorn non è entrato in stato 'started' in 60 s")


def _actual_port(server: "uvicorn.Server") -> int:
    return int(server.servers[0].sockets[0].getsockname()[1])


def _wait_until_ready(host: str, port: int, timeout: float = 60.0) -> None:
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
    raise TimeoutError(f"server non pronto in {timeout:.0f}s su {host}:{port}; ultimo errore: {last_err}")


def _open_ui(url: str, force_browser: bool) -> int:
    if not force_browser:
        try:
            import webview

            webview.settings["ALLOW_DOWNLOADS"] = True
            webview.create_window("VersoCon", url, width=860, height=860,
                                  background_color="#f7f2e9")
            webview.start()
            return 0
        except Exception as e:  # noqa: BLE001
            _crash(f"webview non disponibile, uso browser: {e}")
    webbrowser.open(url)
    print(f"VersoCon in ascolto su {url}  (chiudi per uscire)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    return 0


def main() -> int:
    sys.excepthook = _sys_excepthook
    args = sys.argv[1:]
    force_browser = "--browser" in args or os.environ.get("VERSOCON_BROWSER") == "1"
    port = PORT
    if "--port" in args:
        port = int(args[args.index("--port") + 1])

    try:
        server = _start_server(port)
        real = _actual_port(server)
    except Exception as e:  # noqa: BLE001
        _crash(f"AVVIO FALLITO: {e!r}")
        return 1

    try:
        _wait_until_ready(HOST, real)
    except TimeoutError as e:
        _crash(str(e))
        return 1

    url = f"http://{HOST}:{real}/"
    # Memo persistente dell'istanza attiva (utile per riaprirne l'URL, e per
    # tool di verifica). Non critico se la scrittura fallisce.
    try:
        _mem = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                            "Temp", "VersoCon")
        os.makedirs(_mem, exist_ok=True)
        with open(os.path.join(_mem, "current_url.txt"), "w", encoding="utf-8") as f:
            f.write(url + "\n")
    except OSError:
        pass

    return _open_ui(url, force_browser)


if __name__ == "__main__":
    raise SystemExit(main())
