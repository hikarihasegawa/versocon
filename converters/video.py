"""Video: transcode verso MP4/WebM, estrazione audio (MP3/M4A) e GIF animata via ffmpeg.

ffmpeg è opzionale: se assente l'app continua a lavorare su tutto il resto e
restituisce un errore 503 chiaro.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

from . import engines
from .proc import NO_WINDOW
from .report import OperationCancelled, report

MAX_VIDEO_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB di input
FFMPEG_TIMEOUT = 300  # secondi

VIDEO_IN_EXT = {
    ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm",
    ".wmv", ".flv", ".mpg", ".mpeg", ".3gp", ".3g2", ".ogg",
}

# formato di uscita -> codec (video/audio) di default.
# mp4: H.264 + AAC (massima compatibilità). webm: VP9 + Vorbis (open).
_OUT = {
    "mp4": ("libx264", "aac"),
    "webm": ("libvpx-vp9", "libvorbis"),
}

# formato audio di uscita -> (codec, argomenti extra)
_AUDIO_OUT = {
    "mp3": ("libmp3lame", ["-q:a", "2"]),
    "m4a": ("aac", ["-b:a", "192k", "-movflags", "+faststart"]),
}

MAX_GIF_FPS = 30
MAX_GIF_WIDTH = 1920
MIN_GIF_WIDTH = 64


class MissingFfmpegError(RuntimeError):
    """Il componente ffmpeg incluso non è disponibile o non è avviabile."""


class VideoTimeoutError(RuntimeError):
    """L'operazione ha superato il timeout."""


class NoAudioTrackError(ValueError):
    """Il video sorgente non contiene una traccia audio."""


def video_is_supported(filename: str) -> bool:
    """True se `filename` ha estensione nota (accetta 'clip.mp4', '.mp4', 'mp4' ecc.)."""
    if not filename:
        return False
    name = filename.strip().lower()
    if name.startswith("."):
        return name in VIDEO_IN_EXT
    return Path(name).suffix in VIDEO_IN_EXT


def _out_container(fmt: str) -> tuple[str, str, str]:
    """Restituisce (estensione, video_codec, audio_codec) per il formato richiesto."""
    o = (fmt or "mp4").lower().lstrip(".")
    if o == "h264":
        o = "mp4"
    if o not in _OUT:
        raise ValueError(f"Formato video di uscita non supportato: {fmt}")
    return (o, *_OUT[o])


_FFMPEG_CACHE: tuple[bool, str | None] | None = None  # (cercata, percorso|None)


def _find_ffmpeg() -> str | None:
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE is not None:
        return _FFMPEG_CACHE[1]
    for p in engines.iter_candidates(("ffmpeg", "ffmpeg.exe")):
        try:
            r = subprocess.run([p, "-version"], capture_output=True, timeout=8, **NO_WINDOW)
        except Exception:  # noqa: BLE001 - stub, timeout, permessi
            continue
        if r.returncode == 0:
            _FFMPEG_CACHE = (True, p)
            return p
    _FFMPEG_CACHE = (True, None)
    return None


def _find_ffprobe(ff: str) -> str | None:
    """ffprobe accanto a ffmpeg oppure nel PATH; None se assente."""
    cand = Path(ff).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if cand.is_file():
        return str(cand)
    for p in engines.iter_candidates(("ffprobe", "ffprobe.exe")):
        try:
            if Path(p).is_file():
                return p
        except OSError:
            continue
    return None


def _probe_duration(ff: str, src_path: str) -> float | None:
    """Durata del file in secondi (ffprobe); None → progresso indeterminato."""
    probe = _find_ffprobe(ff)
    if not probe:
        return None
    try:
        r = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(src_path)],
            capture_output=True, timeout=20, **NO_WINDOW,
        )
        value = float((r.stdout or b"").decode("utf-8", "replace").strip())
        return value if value > 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _pump_progress(
    proc: subprocess.Popen,
    progress,
    cancel,
    total_s: float | None,
    started: float,
) -> None:
    """Legge le righe di ``-progress pipe:1`` e segnala l'avanzamento reale.

    Si ferma subito (uccidendo ffmpeg) se l'utente annulla o se scade il timeout.
    """
    total = int(total_s) if total_s else None
    report(progress, 0, total, "seconds")
    for raw in proc.stdout:
        if cancel is not None and cancel():
            raise OperationCancelled()
        if time.monotonic() - started > FFMPEG_TIMEOUT:
            raise VideoTimeoutError(f"superato il timeout di {FFMPEG_TIMEOUT}s")
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("out_time_us=") and total:
            try:
                us = int(line.split("=", 1)[1])
            except ValueError:
                continue
            report(progress, min(int(us / 1_000_000), total), total, "seconds")


def _run_ffmpeg(
    ff: str,
    args: list[str],
    dst: Path,
    label: str = "Operazione",
    *,
    progress=None,
    cancel=None,
    total_s: float | None = None,
) -> int:
    """Esegue ffmpeg con gli argomenti dati e scrive l'output atomicamente su `dst`.

    Restituisce la dimensione in byte. Un fallimento non lascia file parziali.
    ``progress``/``cancel`` opzionali: avanzamento reale e annullo cooperativo.
    """
    # mkstemp apre l'fd: va chiuso subito, altrimenti su Windows il file resta
    # "in uso" e non possiamo fare rename/mover al termine.
    fd, tmpname = tempfile.mkstemp(suffix=dst.suffix, dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmpname)
    err = tempfile.TemporaryFile()

    started = time.monotonic()
    try:
        cmd = [ff, "-y", "-hide_banner", *args, "-progress", "pipe:1", "-nostats", "-loglevel", "error", str(tmp)]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=err, **NO_WINDOW
            )
        except OSError as e:
            raise ValueError(f"ffmpeg non avviabile: {e}") from e
        try:
            _pump_progress(proc, progress, cancel, total_s, started)
            code = proc.wait()
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        if code != 0:
            err.seek(0)
            tail = err.read().decode("utf-8", "replace").strip()[-400:]
            raise ValueError(f"ffmpeg ha fallito (codice {code}){(' — ' + tail) if tail else ''}")
        if total_s:
            report(progress, int(total_s), int(total_s), "seconds")
        # Spostamento atomico dell'output; su Windows può servire un tentativo in più
        # se un handle (antivirus) trattiene ancora il file.
        last_err: Exception | None = None
        for _ in range(5):
            try:
                tmp.replace(dst)
                break
            except PermissionError as e:  # noqa: PERF203
                last_err = e
                time.sleep(0.2)
        else:
            raise ValueError("Impossibile completare il salvataggio (file occupato sul sistema).") from last_err
    finally:
        err.close()
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return dst.stat().st_size


def _find_ffmpeg_or_raise() -> str:
    ff = _find_ffmpeg()
    if not ff:
        raise MissingFfmpegError(
            "ffmpeg non trovato o non avviabile: il componente incluso risulta "
            "mancante o danneggiato. Reinstalla l'app per ripristinarlo."
        )
    return ff


def transcode(
    src_path: str,
    dst_path: str,
    fmt: str = "mp4",
    crf: int | None = None,
    *,
    progress=None,
    cancel=None,
) -> int:
    """Trascode `src_path` in `dst_path` usando ffmpeg e restituisce la dimensione in byte.

    ``progress``/``cancel`` opzionali per il job in background (avanzamento reale
    sui secondi del sorgente, annullo che termina ffmpeg).
    """
    if not Path(src_path).is_file():
        raise ValueError("File sorgente non trovato")

    ext, vcodec, acodec = _out_container(fmt)
    if not Path(dst_path).suffix:
        raise ValueError("Percorso di destinazione senza estensione")
    if Path(dst_path).suffix.lower().lstrip(".") != ext:
        # se l'estensione non corrisponde al formato scelto, costringe quella del formato
        dst_path = str(Path(dst_path).with_suffix("." + ext))

    ff = _find_ffmpeg_or_raise()
    crf = 23 if crf is None else int(crf)
    args = [
        "-i", str(src_path),
        "-c:v", vcodec, "-crf", str(crf), "-preset", "medium",
        "-c:a", acodec, "-movflags", "+faststart",
    ]
    return _run_ffmpeg(
        ff, args, Path(dst_path), label="Transcode",
        progress=progress, cancel=cancel, total_s=_probe_duration(ff, str(src_path)),
    )


def extract_audio(
    src_path: str,
    dst_path: str,
    fmt: str = "mp3",
    *,
    progress=None,
    cancel=None,
) -> int:
    """Estrae la traccia audio di `src_path` in MP3 o M4A e restituisce la dimensione in byte.

    Solleva `NoAudioTrackError` se il sorgente non ha audio (es. video muto).
    """
    if not Path(src_path).is_file():
        raise ValueError("File sorgente non trovato")

    o = (fmt or "mp3").lower().lstrip(".")
    if o not in _AUDIO_OUT:
        raise ValueError(f"Formato audio di uscita non supportato: {fmt}")
    if not Path(dst_path).suffix:
        raise ValueError("Percorso di destinazione senza estensione")
    if Path(dst_path).suffix.lower().lstrip(".") != o:
        dst_path = str(Path(dst_path).with_suffix("." + o))

    ff = _find_ffmpeg_or_raise()
    codec, extra = _AUDIO_OUT[o]
    args = ["-i", str(src_path), "-vn", "-c:a", codec, *extra]
    try:
        return _run_ffmpeg(
            ff, args, Path(dst_path), label="Estrazione audio",
            progress=progress, cancel=cancel, total_s=_probe_duration(ff, str(src_path)),
        )
    except ValueError as e:
        msg = str(e).lower()
        if "does not contain any stream" in msg or "matches no streams" in msg:
            raise NoAudioTrackError("Il video non contiene una traccia audio.") from e
        raise


def video_to_gif(
    src_path: str,
    dst_path: str,
    fps: int = 10,
    width: int = 480,
    start: float | None = None,
    end: float | None = None,
    *,
    progress=None,
    cancel=None,
) -> int:
    """Crea una GIF animata in loop (palette ottimizzata) e restituisce la dimensione in byte.

    `start`/`end` (secondi) delimitano l'intervallo da estrarre; `width` è il
    lato largo in px. Con solo `start` si arriva alla fine del video.
    """
    if not Path(src_path).is_file():
        raise ValueError("File sorgente non trovato")
    if not Path(dst_path).suffix:
        raise ValueError("Percorso di destinazione senza estensione")
    if Path(dst_path).suffix.lower() != ".gif":
        dst_path = str(Path(dst_path).with_suffix(".gif"))

    fps = int(fps)
    width = int(width)
    if not 1 <= fps <= MAX_GIF_FPS:
        raise ValueError(f"fps GIF fuori intervallo (1-{MAX_GIF_FPS})")
    if not MIN_GIF_WIDTH <= width <= MAX_GIF_WIDTH:
        raise ValueError(f"larghezza GIF fuori intervallo ({MIN_GIF_WIDTH}-{MAX_GIF_WIDTH})")
    if start is not None and float(start) < 0:
        raise ValueError("inizio GIF deve essere >= 0")
    if end is not None and float(end) <= 0:
        raise ValueError("fine GIF deve essere > 0")
    if end is not None and start is not None and float(end) <= float(start):
        raise ValueError("fine GIF deve essere maggiore dell'inizio")

    ff = _find_ffmpeg_or_raise()
    vf = (
        f"fps={fps},scale={width}:-1:flags=lanczos,"
        "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    )
    args: list[str] = []
    if start is not None:
        args += ["-ss", str(float(start))]
    args += ["-i", str(src_path)]
    cut: float | None = None
    if end is not None:
        cut = float(end) - (float(start) if start is not None else 0.0)
        args += ["-t", str(cut)]
    args += ["-vf", vf, "-loop", "0"]
    if cut is not None:
        total: float | None = cut
    else:
        src_total = _probe_duration(ff, str(src_path))
        total = max(0.1, src_total - (float(start) if start is not None else 0.0)) if src_total else None
    return _run_ffmpeg(
        ff, args, Path(dst_path), label="Creazione GIF",
        progress=progress, cancel=cancel, total_s=total,
    )


def ffmpeg_available() -> bool:
    return _find_ffmpeg() is not None


def _reset_ffmpeg_cache() -> None:
    """Svuota la cache del binario (usato dai test per simulare presenza/assenza)."""
    global _FFMPEG_CACHE
    _FFMPEG_CACHE = None
