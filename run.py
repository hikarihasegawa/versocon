"""VersoCon — lanciatore.

Preferisce una finestra desktop (pywebview); se non disponibile apre il
browser predefinito. Uso:
    python run.py                # finestra desktop o browser, porta scelta dal SO
    python run.py --browser      # forza browser
    python run.py --port 9000    # forza una porta esplicita
"""
from __future__ import annotations

import os
import sys
import socket
import threading
import time
import traceback
import urllib.request
import webbrowser

# --- FIX radice (v0.2.3) ----------------------------------------------------
# In una build PyInstaller "windowed" (senza console) sys.stdout/stderr sono
# None. uvicorn istanzia un formatter (ColourizedFormatter) che chiama
# sys.stdout.isatty() INDIPENDENTEMENTE da log_level -> AttributeError('NoneType'
# has no attribute 'isatty') avvolto da logging in
#   ValueError: Unable to configure formatter 'default'
# -> crash al primo avvio dell'EXE (v0.2.2). Mettiamo stdout/stderr a devnull
# PRIMA che uvicorn configuri il logging. In dev (console) i stream esistono e
# questo blocco è un no-op.
_devnull = open(os.devnull, "w")
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, _devnull)
# -----------------------------------------------------------------------------

import uvicorn  # noqa: E402  (dopo la guardia su sys.stdout/stderr)

_APP_IMPORT_ERROR: Exception | None = None
try:
    from app.main import app  # noqa: E402,F401
except Exception as _e:  # noqa: BLE001
    # Non deve uscire un traceback grezzo di PyInstaller: senza questa guardia
    # una DLL bloccata (es. criterio di controllo applicazioni di Windows)
    # faceva fallire l'avvio con «Failed to execute script 'run'».
    _APP_IMPORT_ERROR = _e
    app = None

HOST = "127.0.0.1"

_CRASH_LOG = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                          "Temp", "VersoCon", "crash.log")


def _crash(msg: str) -> None:
    """Logga su file %LOCALAPPDATA%\\Temp\\VersoCon\\crash.log (e console se esiste)."""
    try:
        print(msg, file=sys.stderr)
    except Exception:  # noqa: BLE001
        pass
    try:
        os.makedirs(os.path.dirname(_CRASH_LOG), exist_ok=True)
        with open(_CRASH_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n{msg}\n")
    except OSError:
        pass


def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
    _crash("Uncaught exception in thread %s:\n%s" % (
        args.thread,
        "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)),
    ))


def _main_excepthook(exc_type, exc, tb) -> None:
    _crash("Uncaught exception:\n" + "".join(traceback.format_exception(exc_type, exc, tb)))


def _show_error_dialog(title: str, text: str) -> None:
    """Avviso di avvio impossibile: MessageBox nativo (nessuna dipendenza GUI)."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR
    except Exception:  # noqa: BLE001
        pass


def _startup_failure_text(err: Exception) -> str:
    return (
        "VersoCon non pu\u00f2 avviarsi su questo PC.\n\n"
        f"Errore: {err}\n\n"
        "Se il messaggio parla di \u00abcriterio di controllo dell'applicazione\u00bb, "
        "Windows (Smart App Control o AppLocker) ha bloccato un file dell'app "
        "perch\u00e9 non \u00e8 firmato: consentilo dal pannello Sicurezza di Windows "
        "oppure installa VersoCon su un PC senza questa restrizione.\n\n"
        "Dettagli salvati in: " + _CRASH_LOG
    )


def _pick_free_port() -> int:
    """Chiede al SO una porta libera garantita (bind su porta 0)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _serve(host: str, port: int) -> None:
    # Pattern 0.2.1, provato e stabile. log_level=warning silenzia i log access.
    uvicorn.run(app, host=host, port=port, log_level="warning")


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
            # Finestra desktop: parte massimizzata (il layout a due pannelli
            # dell'editor non entra in 860x860); 1280x860 come base se l'utente
            # la ripristina.
            webview.create_window("VersoCon", url, width=1280, height=860,
                                  maximized=True, background_color="#f7f2e9")
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
    sys.excepthook = _main_excepthook
    threading.excepthook = _thread_excepthook
    if _APP_IMPORT_ERROR is not None:
        _crash("AVVIO IMPOSSIBILE (import app.main): " + repr(_APP_IMPORT_ERROR))
        _show_error_dialog("VersoCon", _startup_failure_text(_APP_IMPORT_ERROR))
        return 1
    args = sys.argv[1:]
    force_browser = "--browser" in args or os.environ.get("VERSOCON_BROWSER") == "1"

    # 0 = il SO sceglie una porta libera garantita: l'app funziona anche se 8321
    # (o qualsiasi altra) è già occupata su quella macchina.
    port = _pick_free_port()
    if "--port" in args:
        port = int(args[args.index("--port") + 1])

    # Avvia il server in un daemon thread e attendi finché risponde davvero.
    threading.Thread(target=_serve, args=(HOST, port), daemon=True).start()
    try:
        _wait_until_ready(HOST, port)
    except TimeoutError as e:
        _crash(f"AVVIO FALLITO: {e}")
        return 1

    url = f"http://{HOST}:{port}/"
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
