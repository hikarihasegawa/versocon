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
    """ffmpeg non disponibile sul sistema."""


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


def _run_ffmpeg(ff: str, args: list[str], dst: Path, label: str = "Operazione") -> int:
    """Esegue ffmpeg con gli argomenti dati e scrive l'output atomicamente su `dst`.

    Restituisce la dimensione in byte. Un fallimento non lascia file parziali.
    """
    # mkstemp apre l'fd: va chiuso subito, altrimenti su Windows il file resta
    # "in uso" e non possiamo fare rename/mover al termine.
    fd, tmpname = tempfile.mkstemp(suffix=dst.suffix, dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmpname)

    try:
        cmd = [ff, "-y", "-hide_banner", *args, "-loglevel", "error", str(tmp)]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT, **NO_WINDOW)
        except subprocess.TimeoutExpired as e:
            raise VideoTimeoutError(f"{label}: superato il timeout di {FFMPEG_TIMEOUT}s") from e
        if r.returncode != 0:
            tail = (r.stderr or b"").decode("utf-8", "replace").strip()[-400:]
            raise ValueError(f"ffmpeg ha fallito (codice {r.returncode}){(' — ' + tail) if tail else ''}")
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
            "ffmpeg non trovato: installa ffmpeg (winget install Gyan.FFmpeg) e riprova."
        )
    return ff


def transcode(src_path: str, dst_path: str, fmt: str = "mp4", crf: int | None = None) -> int:
    """Trascode `src_path` in `dst_path` usando ffmpeg e restituisce la dimensione in byte."""
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
    return _run_ffmpeg(ff, args, Path(dst_path), label="Transcode")


def extract_audio(src_path: str, dst_path: str, fmt: str = "mp3") -> int:
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
        return _run_ffmpeg(ff, args, Path(dst_path), label="Estrazione audio")
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
    duration: float | None = None,
) -> int:
    """Crea una GIF animata in loop (palette ottimizzata) e restituisce la dimensione in byte.

    `start`/`duration` (secondi) ritagliano il segmento; `width` è il lato largo in px.
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
    if duration is not None and float(duration) <= 0:
        raise ValueError("durata GIF deve essere > 0")

    ff = _find_ffmpeg_or_raise()
    vf = (
        f"fps={fps},scale={width}:-1:flags=lanczos,"
        "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    )
    args: list[str] = []
    if start is not None:
        args += ["-ss", str(float(start))]
    args += ["-i", str(src_path)]
    if duration is not None:
        args += ["-t", str(float(duration))]
    args += ["-vf", vf, "-loop", "0"]
    return _run_ffmpeg(ff, args, Path(dst_path), label="Creazione GIF")


def ffmpeg_available() -> bool:
    return _find_ffmpeg() is not None


def _reset_ffmpeg_cache() -> None:
    """Svuota la cache del binario (usato dai test per simulare presenza/assenza)."""
    global _FFMPEG_CACHE
    _FFMPEG_CACHE = None
