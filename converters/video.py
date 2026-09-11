"""Video: transcode base verso MP4 (H.264/AAC) o WebM (VP9/Vorbis) via ffmpeg.

ffmpeg è opzionale: se assente l'app continua a lavorare su tutto il resto e
restituisce un errore 503 chiaro.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

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


class MissingFfmpegError(RuntimeError):
    """ffmpeg non disponibile sul sistema."""


class VideoTimeoutError(RuntimeError):
    """Il transcode ha superato il timeout."""


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
    for name in ("ffmpeg", "ffmpeg.exe"):
        p = shutil.which(name)
        if not p:
            continue
        try:
            r = subprocess.run([p, "-version"], capture_output=True, timeout=8, **NO_WINDOW)
        except Exception:  # noqa: BLE001 - stub, timeout, permessi
            continue
        if r.returncode == 0:
            _FFMPEG_CACHE = (True, p)
            return p
    _FFMPEG_CACHE = (True, None)
    return None


def transcode(src_path: str, dst_path: str, fmt: str = "mp4", crf: int | None = None) -> int:
    """Trascode `src_path` in `dst_path` usando ffmpeg e restituisce la dimensione in byte.

    Scrive in un file temporaneo nella stessa cartella di destinazione e lo sposta
    atomicamente al termine, così un fallimento non lascia file parziali.
    """
    if not Path(src_path).is_file():
        raise ValueError("File sorgente non trovato")

    ext, vcodec, acodec = _out_container(fmt)
    if not Path(dst_path).suffix:
        raise ValueError("Percorso di destinazione senza estensione")
    if Path(dst_path).suffix.lower().lstrip(".") != ext:
        # se l'estensione non corrisponde al formato scelto, costringe quella del formato
        dst_path = str(Path(dst_path).with_suffix("." + ext))

    ff = _find_ffmpeg()
    if not ff:
        raise MissingFfmpegError(
            "ffmpeg non trovato: installa ffmpeg (winget install Gyan.FFmpeg) e riprova."
        )

    crf = 23 if crf is None else int(crf)
    dst = Path(dst_path)

    # mkstemp apre l'fd: va chiuso subito, altrimenti su Windows il file resta
    # "in uso" e non possiamo fare rename/mover al termine.
    fd, tmpname = tempfile.mkstemp(suffix="." + ext, dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmpname)

    try:
        cmd = [
            ff, "-y", "-hide_banner", "-i", str(src_path),
            "-c:v", vcodec, "-crf", str(crf), "-preset", "medium",
            "-c:a", acodec, "-movflags", "+faststart", "-loglevel", "error", str(tmp),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=FFMPEG_TIMEOUT, **NO_WINDOW)
        except subprocess.TimeoutExpired as e:
            raise VideoTimeoutError(f"Transcode superato il timeout di {FFMPEG_TIMEOUT}s") from e
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


def ffmpeg_available() -> bool:
    return _find_ffmpeg() is not None


def _reset_ffmpeg_cache() -> None:
    """Svuota la cache del binario (usato dai test per simulare presenza/assenza)."""
    global _FFMPEG_CACHE
    _FFMPEG_CACHE = None
