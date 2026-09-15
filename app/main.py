"""VersoCon — convertitore di file, GUI web stile anime."""
from __future__ import annotations

import atexit
import io
import os
import shutil
import tempfile
import time
import urllib.parse
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from converters import compress as compconv
from converters import documents as docconv
from converters import pdfedit as pdfeditconv
from converters import extract as exconv
from converters import images as imgconv
from converters import sign as sconv
from converters import tools as toolconv
from converters import video as vidconv

from app import constants
from app.i18n import t as T
from app.security import LocalOnlyMiddleware, safe_child
from app.version import __version__


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    # Avvio via `uvicorn` CLI: su SIGTERM uvicorn ri-solleva il segnale e
    # atexit non gira, quindi puliamo qui. Nell'app desktop provvede atexit.
    shutil.rmtree(OUT_DIR, ignore_errors=True)


app = FastAPI(title="VersoCon", version=__version__, lifespan=_lifespan)
app.add_middleware(LocalOnlyMiddleware)

BASE_DIR = constants.ROOT
_TMP_ROOT = Path(tempfile.gettempdir())
_STALE_AFTER_S = 72 * 3600
_KEEP_IN_LEGACY = frozenset({"crash.log", "current_url.txt"})


def _purge_stale_outputs() -> None:
    """Rimuove output di sessioni precedenti (crash/kill) e la vecchia cartella
    condivisa `versocon/` delle versioni <= 0.2.4. Best-effort, mai bloccante.

    Su Windows `%TEMP%\\versocon` e `%LOCALAPPDATA%\\Temp\\VersoCon` (usata da
    run.py per crash.log e current_url.txt) sono la STESSA cartella (filesystem
    case-insensitive): quei due file vanno preservati."""
    legacy = _TMP_ROOT / "versocon"
    if legacy.is_dir():
        for item in legacy.iterdir():
            if item.name.lower() in _KEEP_IN_LEGACY:
                continue
            try:
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
            except OSError:
                pass
    now = time.time()
    for d in _TMP_ROOT.glob("versocon-*"):
        try:
            if d.is_dir() and now - d.stat().st_mtime > _STALE_AFTER_S:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


_purge_stale_outputs()
# Cartella privata per questa sessione (mkdtemp: nome univoco, permessi 0700).
# Viene cancellata alla chiusura: i file convertiti vivono solo finché l'app è aperta.
OUT_DIR = Path(tempfile.mkdtemp(prefix="versocon-"))
atexit.register(shutil.rmtree, OUT_DIR, ignore_errors=True)


def _read_capped(uf: UploadFile, limit: int) -> bytes:
    """Legge al massimo limit+1 byte: il chiamante vede comunque len > limit e
    rifiuta, ma un file enorme non viene mai caricato per intero in RAM."""
    return uf.file.read(limit + 1)

VALID_OUT = ("jpeg", "png", "webp", "gif")
MAX_BATCH_FILES = 500


@app.get("/api/config")
def config():
    return {
        "version": app.version,
        "supported_in": sorted(imgconv.ACCEPTED_EXT),
        "supported_out": list(VALID_OUT),
        "documents": {
            "pdf_out": ["jpeg", "png", "webp"],
        },
        "video": {
            "in": sorted(vidconv.VIDEO_IN_EXT),
            "out": ["mp4", "webm"],
            "ffmpeg_available": vidconv.ffmpeg_available(),
        },
        "ocr": exconv.ocr_info(),
        "support": {"kofi_url": constants.KOFI_URL},
        "note": "HEIC/HEIF require pillow-heif (installed).",
    }


@app.post("/api/engines/recheck")
def engines_recheck():
    """Rilegge ffmpeg e Tesseract ignorando la cache (bottone «Ricontrolla»).

    Utile quando l'utente installa un motore mentre l'app è già aperta: il
    processo ha ancora il vecchio ambiente e le cache erano negative.
    """
    vidconv._reset_ffmpeg_cache()
    exconv.reset_ocr_cache()
    return {
        "video": {"ffmpeg_available": vidconv.ffmpeg_available()},
        "ocr": exconv.ocr_info(),
    }


def _open_support_in_browser() -> None:
    import threading
    import webbrowser

    def _open() -> None:
        webbrowser.open(constants.KOFI_URL, new=1)

    threading.Thread(target=_open, daemon=True).start()


@app.post("/api/support")
def support(request: Request):
    if not constants.KOFI_URL:
        raise HTTPException(503, T(request, "api.support_not_configured"))
    _open_support_in_browser()
    return {"opened": True, "url": constants.KOFI_URL}


def _sanitize_quality(quality) -> int | None:
    if quality is None or quality == "":
        return None
    try:
        return max(1, min(100, int(quality)))
    except (TypeError, ValueError):
        return None


def _sanitize_max_side(max_side) -> int | None:
    if max_side is None or max_side == "":
        return None
    try:
        v = int(max_side)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _image_size(data: bytes) -> tuple[int, int] | None:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:  # noqa: BLE001 - dimension info is best-effort
        return None


def _read_upload(request: Request, uf: UploadFile) -> bytes:
    data = _read_capped(uf, 200 * 1024 * 1024)
    name = Path(uf.filename or "").name
    if not data:
        raise HTTPException(400, T(request, "api.file_empty_named", name=name))
    if not imgconv.is_convertible(name):
        raise HTTPException(400, T(request, "api.file_type_unsupported", name=name))
    if len(data) > 200 * 1024 * 1024:
        raise HTTPException(400, T(request, "api.file_200mb_limit", name=name))
    return data


@app.post("/api/convert")
def convert(
    request: Request,
    files: list[UploadFile] = File(...),
    fmt: str = Form("jpeg"),
    quality: int | None = Form(None),
    max_side: int | None = Form(None),
    strip_exif: bool = Form(False),
):
    fmt_l = (fmt or "jpeg").lower().lstrip(".")
    if fmt_l == "jpg":
        fmt_l = "jpeg"
    if fmt_l not in VALID_OUT:
        raise HTTPException(400, T(request, "api.out_format_unsupported", fmt=fmt))
    if not files:
        raise HTTPException(400, T(request, "api.no_files"))
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(400, T(request, "api.too_many_files", max=MAX_BATCH_FILES, n=len(files)))

    quality = _sanitize_quality(quality)
    max_side = _sanitize_max_side(max_side)

    results = []
    used: set[str] = set()
    for i, uf in enumerate(files):
        stem = Path(uf.filename).stem or f"img{i + 1}"
        base, n = stem, 1
        while f"{base}.{imgconv.output_ext(fmt_l)}" in used:
            n += 1
            base = f"{stem}-{n}"
        try:
            data = _read_upload(request, uf)
        except HTTPException as e:
            results.append({"name": uf.filename, "error": str(e.detail)})
            continue
        ext = imgconv.output_ext(fmt_l)
        dst_name = f"{base}.{ext}"
        try:
            out = imgconv.convert_bytes(
                data, fmt_l, quality=quality, max_side=max_side, strip_exif=strip_exif
            )
        except Exception as e:  # noqa: BLE001 - report per-file errors to UI
            results.append({"name": uf.filename, "error": f"decode failed: {e}"})
            continue
        dst = OUT_DIR / dst_name
        dst.write_bytes(out)
        used.add(dst_name)
        entry = {
            "name": dst_name,
            "src": uf.filename,
            "size": len(out),
            "path": str(dst),
            "download": f"/api/file/{dst_name}",
        }
        dims = _image_size(out)
        if dims:
            entry["width"], entry["height"] = dims
        results.append(entry)

    ok = [r for r in results if "error" not in r]
    if not ok:
        raise HTTPException(422, detail={"message": T(request, "api.all_failed"), "results": results})
    return {"results": results}


@app.get("/api/file/{name}")
def download_file(request: Request, name: str):
    p = safe_child(OUT_DIR, name)
    if p is None or not p.is_file():
        raise HTTPException(404, T(request, "api.file_not_found"))
    return FileResponse(p, filename=p.name)


@app.get("/api/download")
def download_zip(request: Request, names: str):
    """Zip dei file separati da virgola (parametro names)."""
    items = [n.strip() for n in (names or "").split(",") if n.strip()]
    if not items:
        raise HTTPException(400, T(request, "api.no_files_specified"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in items:
            p = safe_child(OUT_DIR, n)
            if p is not None and p.is_file():
                zf.write(p, p.name)
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="versocon.zip"'},
    )


@app.post("/api/convert-pdf-to-images")
def convert_pdf_to_images(
    request: Request,
    file: UploadFile = File(...),
    fmt: str = Form("jpeg"),
    dpi: int | None = Form(None),
    quality: int | None = Form(None),
):
    data = _read_capped(file, docconv.MAX_DOC_BYTES)
    name = Path(file.filename or "").name
    if not data:
        raise HTTPException(400, T(request, "api.file_empty"))
    if len(data) > docconv.MAX_DOC_BYTES:
        raise HTTPException(400, T(request, "api.file_100mb_limit", name=name))
    try:
        ext = docconv.pdf_to_image_ext(fmt)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        pages = docconv.pdf_to_images(data, ext, dpi=dpi, quality=quality)
    except Exception as e:  # noqa: BLE001 - PDF corrotto / non supportato
        raise HTTPException(400, T(request, "api.pdf_unreadable", detail=str(e)))

    results = []
    used: set[str] = set()
    stem = Path(file.filename).stem or "pagina"
    for i, page_bytes in enumerate(pages, start=1):
        base, n = f"{stem}-pag{i:02d}", 1
        while f"{base}.{ext}" in used:
            n += 1
            base = f"{stem}-pag{i:02d}-{n}"
        name = f"{base}.{ext}"
        dst = OUT_DIR / name
        dst.write_bytes(page_bytes)
        used.add(name)
        results.append({
            "name": name,
            "src": file.filename,
            "size": len(page_bytes),
            "path": str(dst),
            "download": f"/api/file/{name}",
        })
    if not results:
        raise HTTPException(422, T(request, "api.no_pages_found"))
    return {"results": results, "pages": len(results)}


@app.post("/api/convert-images-to-pdf")
def convert_images_to_pdf(
    request: Request,
    files: list[UploadFile] = File(...),
    max_side: int | None = Form(None),
):
    if not files:
        raise HTTPException(400, T(request, "api.no_files"))
    if len(files) > docconv.MAX_IMAGES_PER_PDF:
        raise HTTPException(400, T(request, "api.max_images_per_pdf", max=docconv.MAX_IMAGES_PER_PDF, n=len(files)))
    payload: list[tuple[str, bytes]] = []
    for f in files:
        fname = Path(f.filename or "").name
        if not docconv.image_is_supported(fname):
            raise HTTPException(400, T(request, "api.img_format_unsupported", name=fname))
        raw = _read_capped(f, docconv.MAX_DOC_BYTES)
        if not raw:
            raise HTTPException(400, T(request, "api.file_empty_named", name=fname))
        if len(raw) > docconv.MAX_DOC_BYTES:
            raise HTTPException(400, T(request, "api.file_100mb_limit", name=fname))
        payload.append((fname, raw))
    ms = None
    if max_side is not None and max_side != "":
        try:
            v = int(max_side)
            ms = v if v > 0 else None
        except (TypeError, ValueError):
            ms = None
    try:
        out = docconv.images_to_pdf(payload, max_side=ms)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001 - PDF generation failure
        raise HTTPException(500, T(request, "api.pdf_gen_failed", detail=str(e)))
    name = "versocon.pdf"
    dst = OUT_DIR / name
    dst.write_bytes(out)
    return {
        "results": [{
            "name": name,
            "size": len(out),
            "path": str(dst),
            "download": f"/api/file/{name}",
        }],
        "images": len(payload),
    }



def _save_video_upload(request: Request, file: UploadFile) -> tuple[Path, str]:
    """Copia un upload video su disco a blocchi (mai l'intero file in RAM).

    Restituisce (percorso del temp, nome originale). Il chiamante rimuove il temp.
    """
    vname = Path(file.filename or "").name
    if not vidconv.video_is_supported(vname):
        raise HTTPException(400, T(request, "api.video_format_unsupported", name=vname, exts=", ".join(sorted(vidconv.VIDEO_IN_EXT))))

    # Nome univoco: due conversioni in parallelo non si sovrascrivono il sorgente.
    orig_ext = Path(vname).suffix.lower() or ".mp4"
    fd, src_name = tempfile.mkstemp(prefix=".src-", suffix=orig_ext, dir=str(OUT_DIR))
    src = Path(src_name)
    written = 0
    with os.fdopen(fd, "wb") as out_f:
        while chunk := file.file.read(1024 * 1024):
            written += len(chunk)
            if written > vidconv.MAX_VIDEO_BYTES:
                break
            out_f.write(chunk)
    if written == 0 or written > vidconv.MAX_VIDEO_BYTES:
        src.unlink(missing_ok=True)
        if written == 0:
            raise HTTPException(400, T(request, "api.file_empty"))
        raise HTTPException(400, T(request, "api.file_2gb_limit", name=vname))
    return src, vname


def _video_out_path(stem: str, ext: str) -> tuple[str, Path]:
    """Nome di uscita univoco in OUT_DIR per il video dato."""
    dst_name, n = f"{stem}.{ext}", 1
    while (OUT_DIR / dst_name).exists():
        n += 1
        dst_name = f"{stem}-{n}.{ext}"
    return dst_name, OUT_DIR / dst_name


def _video_result(dst_name: str, src_name: str, dst: Path, size: int) -> dict:
    """Payload standard di risposta per un output video."""
    return {
        "results": [{
            "name": dst_name,
            "src": src_name,
            "size": size,
            "path": str(dst),
            "download": f"/api/file/{dst_name}",
        }],
    }


@app.post("/api/convert-video")
def convert_video(
    request: Request,
    file: UploadFile = File(...),
    fmt: str = Form("mp4"),
    crf: int | None = Form(None),
):
    """Transcode di un video verso mp4 (H.264/AAC) o webm (VP9/Vorbis)."""
    try:
        out_ext = vidconv._out_container(fmt)[0]
    except ValueError as e:
        raise HTTPException(400, str(e))

    src, src_name = _save_video_upload(request, file)
    stem = Path(src_name).stem or "video"
    dst_name, dst = _video_out_path(stem, out_ext)
    try:
        try:
            size = vidconv.transcode(str(src), str(dst), fmt=fmt, crf=crf)
        except vidconv.MissingFfmpegError as e:
            raise HTTPException(503, T(request, "api.ffmpeg_missing") + str(e))
        except vidconv.VideoTimeoutError as e:
            raise HTTPException(504, T(request, "api.ffmpeg_timeout") + str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001 - failure generica di transcode
            raise HTTPException(500, T(request, "api.transcode_failed", detail=str(e)))
    finally:
        if src.exists():
            src.unlink()
    return _video_result(dst_name, src_name, dst, size)


@app.post("/api/video-audio")
def video_audio(
    request: Request,
    file: UploadFile = File(...),
    fmt: str = Form("mp3"),
):
    """Estrae la traccia audio di un video in mp3 (libmp3lame) o m4a (AAC)."""
    out_ext = (fmt or "mp3").lower().lstrip(".")
    if out_ext not in vidconv._AUDIO_OUT:
        raise HTTPException(400, f"Formato audio di uscita non supportato: {fmt}")
    src, src_name = _save_video_upload(request, file)
    stem = Path(src_name).stem or "audio"
    dst_name, dst = _video_out_path(stem, out_ext)
    try:
        try:
            size = vidconv.extract_audio(str(src), str(dst), fmt=fmt)
        except vidconv.MissingFfmpegError as e:
            raise HTTPException(503, T(request, "api.ffmpeg_missing") + str(e))
        except vidconv.VideoTimeoutError as e:
            raise HTTPException(504, T(request, "api.ffmpeg_timeout") + str(e))
        except vidconv.NoAudioTrackError as e:
            raise HTTPException(400, T(request, "api.video_no_audio"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001 - failure generica di estrazione
            raise HTTPException(500, T(request, "api.audio_extract_failed", detail=str(e)))
    finally:
        if src.exists():
            src.unlink()
    return _video_result(dst_name, src_name, dst, size)


@app.post("/api/video-gif")
def video_gif(
    request: Request,
    file: UploadFile = File(...),
    fps: int = Form(10),
    width: int = Form(480),
    start: float | None = Form(None),
    duration: float | None = Form(None),
):
    """Crea una GIF animata in loop da un video (palette ottimizzata)."""
    src, src_name = _save_video_upload(request, file)
    stem = Path(src_name).stem or "video"
    dst_name, dst = _video_out_path(stem, "gif")
    try:
        try:
            size = vidconv.video_to_gif(str(src), str(dst), fps=fps, width=width, start=start, duration=duration)
        except vidconv.MissingFfmpegError as e:
            raise HTTPException(503, T(request, "api.ffmpeg_missing") + str(e))
        except vidconv.VideoTimeoutError as e:
            raise HTTPException(504, T(request, "api.ffmpeg_timeout") + str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except Exception as e:  # noqa: BLE001 - failure generica GIF
            raise HTTPException(500, T(request, "api.gif_create_failed", detail=str(e)))
    finally:
        if src.exists():
            src.unlink()
    return _video_result(dst_name, src_name, dst, size)


def _read_pdf_upload(request: Request, uf: UploadFile) -> bytes:
    name = Path(uf.filename or "").name
    if Path(name).suffix.lower() != ".pdf":
        raise HTTPException(400, T(request, "api.file_not_pdf", name=name))
    data = _read_capped(uf, toolconv.MAX_DOC_BYTES)
    if not data:
        raise HTTPException(400, T(request, "api.file_empty_named", name=name))
    if len(data) > toolconv.MAX_DOC_BYTES:
        raise HTTPException(400, T(request, "api.file_100mb_limit", name=name))
    return data


@app.post("/api/merge-pdfs")
def merge_pdfs(request: Request, files: list[UploadFile] = File(...)):
    """Unisce più PDF in un unico documento (ordine di upload)."""
    if not files:
        raise HTTPException(400, T(request, "api.no_pdfs"))
    if len(files) > toolconv.MAX_PDF_FILES:
        raise HTTPException(400, T(request, "api.max_pdfs", max=toolconv.MAX_PDF_FILES, n=len(files)))
    payload: list[tuple[str, bytes]] = []
    for f in files:
        try:
            payload.append((Path(f.filename or "").name, _read_pdf_upload(request, f)))
        except HTTPException:
            raise
    try:
        out = toolconv.merge_pdfs(payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, T(request, "api.merge_failed", detail=str(e)))
    name = "versocon_merged.pdf"
    dst = OUT_DIR / name
    dst.write_bytes(out)
    return {
        "results": [{
            "name": name,
            "size": len(out),
            "path": str(dst),
            "download": f"/api/file/{name}",
        }],
        "inputs": len(payload),
        "pages": toolconv.pdf_page_count(out),
    }


@app.post("/api/split-pdf")
def split_pdf(
    request: Request,
    file: UploadFile = File(...),
    start: int | None = Form(None),
    end: int | None = Form(None),
):
    """Estrae le pagine [start, end] (1-based, incluse) in un nuovo PDF."""
    data = _read_pdf_upload(request, file)
    try:
        out, pages, total = toolconv.split_pdf(data, start=start, end=end)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, T(request, "api.pages_extract_failed", detail=str(e)))
    stem = Path(file.filename).stem or "pdf"
    name = f"{stem}_pag{start}-{end}.pdf"
    dst = OUT_DIR / name
    dst.write_bytes(out)
    return {
        "results": [{
            "name": name,
            "src": file.filename,
            "size": len(out),
            "path": str(dst),
            "download": f"/api/file/{name}",
        }],
        "pages": pages,
        "total_pages_source": total,
    }


@app.post("/api/rename-preview")
def rename_preview_endpoint(
    request: Request,
    names: list[str] = Form(...),
    mode: str = Form("prefix"),
    value: str = Form(""),
    start: int = Form(1),
    step: int = Form(1),
    sep: str = Form("-"),
):
    """Anteprima della rinomina: restituisce la corrispondenza vecchio→nuovo."""
    if not names:
        raise HTTPException(400, T(request, "api.no_names"))
    if len(names) > MAX_BATCH_FILES:
        raise HTTPException(400, T(request, "api.too_many_names", max=MAX_BATCH_FILES))
    payload = [(n, b"") for n in names]
    try:
        renamed = toolconv.rename_files(payload, mode=mode, value=value, start=start, step=step)
    except ValueError as e:
        raise HTTPException(400, str(e))
    mapping = [(o, n) for (o, _), (n, _) in zip(payload, renamed)]
    return {"mapping": [{"from": o, "to": n} for o, n in mapping]}


@app.post("/api/rename-batch")
def rename_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    mode: str = Form("prefix"),
    value: str = Form(""),
    start: int = Form(1),
    step: int = Form(1),
    sep: str = Form("-"),
):
    """Rinomina un batch di file secondo pattern e restituisce uno ZIP."""
    if not files:
        raise HTTPException(400, T(request, "api.no_files"))
    payload: list[tuple[str, bytes]] = []
    for f in files:
        name = Path(f.filename or "").name
        data = f.file.read()
        if not data:
            raise HTTPException(400, T(request, "api.file_empty_named", name=name))
        payload.append((name, data))
    try:
        renamed = toolconv.rename_files(payload, mode=mode, value=value, start=start, step=step)
    except ValueError as e:
        raise HTTPException(400, str(e))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for new_name, raw in renamed:
            zf.writestr(new_name, raw)
    mapping = [(o, n) for (o, _), (n, _) in zip(payload, renamed)]
    return Response(
        buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="versocon_renamed.zip"',
            "X-VersoCon-Rename-Map": urllib.parse.quote(",".join(f"{o}=>{n}" for o, n in mapping)),
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Compressione: immagine + PDF
# ──────────────────────────────────────────────────────────────────────────────
@app.post("/api/compress-image")
def compress_image(
    request: Request,
    file: UploadFile = File(...),
    fmt: str = Form("jpeg"),
    quality: int | None = Form(None),
    max_side: int | None = Form(None),
    target_bytes: int | None = Form(None),
):
    """Comprime un'immagine; target_bytes (se presente) vince su quality."""
    name = Path(file.filename or "").name
    if not compconv.image_is_compressible(name):
        raise HTTPException(400, T(request, "api.img_compress_unsupported", name=name))
    data = _read_capped(file, compconv.MAX_BYTES)
    if not data:
        raise HTTPException(400, T(request, "api.file_empty_named", name=name))
    if len(data) > compconv.MAX_BYTES:
        raise HTTPException(400, T(request, "api.file_100mb_limit", name=name))
    q = _sanitize_quality(quality)
    ms = _sanitize_max_side(max_side)
    tb = None
    if target_bytes is not None and target_bytes != "":
        try:
            tb = int(target_bytes)
            if tb <= 0:
                tb = None
        except (TypeError, ValueError):
            tb = None
    try:
        out, meta = compconv.compress_image(
            data, out_format=fmt, quality=q, max_side=ms, target_bytes=tb
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, T(request, "api.compress_failed", detail=str(e)))
    ext = "jpg" if (fmt or "jpeg") in ("jpeg", "jpg") else (fmt or "jpeg")
    stem = Path(name).stem or "immagine"
    dst_name, n = f"{stem}_c.{ext}", 1
    while (OUT_DIR / dst_name).exists():
        n += 1
        dst_name = f"{stem}_c-{n}.{ext}"
    dst = OUT_DIR / dst_name
    dst.write_bytes(out)
    src_size = len(data)
    saved_pct = round(100 - (len(out) / src_size * 100)) if src_size else 0
    return {
        "results": [{
            "name": dst_name, "src": name,
            "size": len(out), "src_size": src_size,
            "saved_pct": max(0, saved_pct),
            "path": str(dst), "download": f"/api/file/{dst_name}",
            **{k: v for k, v in meta.items() if k != "size"},
        }],
    }


@app.post("/api/compress-pdf")
def compress_pdf(
    request: Request,
    file: UploadFile = File(...),
    level: str = Form("medium"),
):
    """Comprime un PDF (low = min, medium = default, high = max)."""
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() != ".pdf":
        raise HTTPException(400, T(request, "api.file_not_pdf", name=name))
    data = _read_capped(file, compconv.MAX_BYTES)
    if not data:
        raise HTTPException(400, T(request, "api.file_empty_named", name=name))
    if len(data) > compconv.MAX_BYTES:
        raise HTTPException(400, T(request, "api.file_100mb_limit", name=name))
    try:
        out, meta = compconv.compress_pdf(data, level=level)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, T(request, "api.pdf_compress_failed", detail=str(e)))
    stem = Path(name).stem or "pdf"
    lvl = (level or "medium").lower()
    dst_name, n = f"{stem}_c-{lvl}.pdf", 1
    while (OUT_DIR / dst_name).exists():
        n += 1
        dst_name = f"{stem}_c-{lvl}-{n}.pdf"
    dst = OUT_DIR / dst_name
    dst.write_bytes(out)
    src_size = len(data)
    saved_pct = round(100 - (len(out) / src_size * 100)) if src_size else 0
    return {
        "results": [{
            "name": dst_name, "src": name,
            "size": len(out), "src_size": src_size,
            "saved_pct": max(0, saved_pct),
            "path": str(dst), "download": f"/api/file/{dst_name}",
            **{k: v for k, v in meta.items() if k != "size"},
        }],
    }


@app.post("/api/pdf-to-text")
def pdf_to_text(
    request: Request,
    file: UploadFile = File(...),
    ocr: str = Form("auto"),
    lang: str = Form("it"),
):
    """Estrae il testo da un PDF. `ocr` ∈ {auto, on, off} (default auto).

    Ritorna { pages: [ {page, text, ocr} ], results: [{name,size,download}],
    ocr_available: bool, warning?: str }.
    """
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() != ".pdf":
        raise HTTPException(400, T(request, "api.file_not_pdf", name=name))
    data = file.file.read()
    if not data:
        raise HTTPException(400, T(request, "api.file_empty_named", name=name))
    mode = (ocr or "auto").lower()
    if mode not in ("auto", "on", "off"):
        raise HTTPException(400, T(request, "api.ocr_mode_invalid", mode=ocr))
    lang = (lang or "it").strip() or "eng"
    ocr_available = exconv.ocr_enabled()
    warning = None
    if mode in ("on", "auto") and not ocr_available:
        warning = T(request, "api.ocr_warning")
    if mode == "on" and not ocr_available:
        raise HTTPException(501, T(request, "api.ocr_not_installed"))
    try:
        pages_text = exconv.extract_text(data, mode=mode, lang=lang)
    except exconv.OcrEngineMissingError as e:
        # in auto con motore assente: degrada a solo nativo (già segnalato in warning)
        if mode == "auto":
            pages_text = exconv.extract_text(data, mode="off", lang=lang)
        else:
            raise HTTPException(501, T(request, "api.ocr_not_installed")) from e
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, T(request, "api.extract_text_failed", detail=str(e)))
    if mode == "on" and warning is None:
        # OCR forzato su pagine che hanno già testo: quello nativo è esatto, l'OCR no.
        native = sum(1 for t in exconv.page_texts(data) if t.strip())
        if native:
            warning = T(request, "api.ocr_forced_native", n=native, total=len(pages_text))

    stem = Path(name).stem or "pdf"
    dst_name, n = f"{stem}.txt", 1
    while (OUT_DIR / dst_name).exists():
        n += 1
        dst_name = f"{stem}-{n}.txt"
    dst = OUT_DIR / dst_name
    dst.write_text("\n\n".join(t if t else "(senza testo)" for t in pages_text), encoding="utf-8")

    pages_out = [
        {
            "page": i + 1,
            "text": t,
            "ocr": (mode == "on") or (mode == "auto" and not (t and t.strip()) and ocr_available),
        }
        for i, t in enumerate(pages_text)
    ]
    payload = {
        "pages": pages_out,
        "text": "\n\n".join(pages_text),
        "results": [{
            "name": dst_name, "src": name,
            "size": dst.stat().st_size,
            "path": str(dst), "download": f"/api/file/{dst_name}",
        }],
        "ocr_available": ocr_available,
    }
    if warning:
        payload["warning"] = warning
    return payload


@app.post("/api/image-ocr")
def image_ocr(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("text"),
    lang: str = Form("it"),
):
    """OCR di un'immagine (foto o scansione).

    `mode` ∈ {text, pdf}: "text" → .txt con il testo riconosciuto;
    "pdf" → PDF ricercabile (immagine + layer di testo invisibile).
    Ritorna { results: [{name,size,download}], text?, ocr_available }.
    """
    name = Path(file.filename or "").name
    if not compconv.image_is_compressible(name):
        raise HTTPException(400, T(request, "api.file_type_unsupported", name=name))
    data = _read_capped(file, compconv.MAX_BYTES)
    if not data:
        raise HTTPException(400, T(request, "api.file_empty_named", name=name))
    if len(data) > compconv.MAX_BYTES:
        raise HTTPException(400, T(request, "api.file_100mb_limit", name=name))
    m = (mode or "text").strip().lower()
    if m not in ("text", "pdf"):
        raise HTTPException(400, T(request, "api.ocr_output_invalid", mode=mode))
    ocr_lang = (lang or "it").strip() or "eng"
    try:
        if m == "text":
            text = exconv.ocr_image_file(data, lang=ocr_lang)
        else:
            out = exconv.image_to_searchable_pdf(data, lang=ocr_lang)
    except exconv.OcrEngineMissingError as e:
        raise HTTPException(501, T(request, "api.ocr_not_installed")) from e
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, T(request, "api.extract_text_failed", detail=str(e)))

    stem = Path(name).stem or "immagine"
    if m == "text":
        dst_name, n = f"{stem}.txt", 1
        while (OUT_DIR / dst_name).exists():
            n += 1
            dst_name = f"{stem}-{n}.txt"
    else:
        dst_name, n = f"{stem}_ocr.pdf", 1
        while (OUT_DIR / dst_name).exists():
            n += 1
            dst_name = f"{stem}_ocr-{n}.pdf"
    dst = OUT_DIR / dst_name
    if m == "text":
        dst.write_text(text, encoding="utf-8")
    else:
        dst.write_bytes(out)
    payload = {
        "ocr_available": True,
        "results": [{
            "name": dst_name, "src": name,
            "size": dst.stat().st_size,
            "path": str(dst), "download": f"/api/file/{dst_name}",
        }],
    }
    if m == "text":
        payload["text"] = text
    return payload


def _expand_pages(data: bytes, pages_json: str) -> list[int]:
    """Espande una lista pagine: "tutte"/""/lista JSON → lista 1-based completa/parziale."""
    import json as _json
    raw = (pages_json or "").strip()
    if raw.lower() in ("", "tutte", "all", "*"):
        return list(range(1, pdfeditconv.page_count(data) + 1))
    out = _json.loads(raw)
    if isinstance(out, int):
        out = [out]
    return out


def _json_or_none(raw: str, field: str):
    """Parsa un campo Form JSON opzionale; None se vuoto."""
    import json as _json
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return _json.loads(raw)
    except _json.JSONDecodeError as e:
        raise ValueError(f"{field}: JSON non valido") from e


def _save_pdf_output(out: bytes, name: str, suffix: str) -> dict:
    """Salva il PDF modificato in OUT_DIR con nome univoco e payload standard."""
    stem = Path(name).stem or "pdf"
    dst_name, n = f"{stem}_{suffix}.pdf", 1
    while (OUT_DIR / dst_name).exists():
        n += 1
        dst_name = f"{stem}_{suffix}-{n}.pdf"
    dst = OUT_DIR / dst_name
    dst.write_bytes(out)
    return {
        "results": [{
            "name": dst_name, "src": name,
            "size": len(out), "path": str(dst),
            "download": f"/api/file/{dst_name}",
        }],
    }


@app.post("/api/pdf-edit")
def api_pdf_edit(
    request: Request,
    file: UploadFile = File(...),
    action: str = Form(...),
    # riordino / eliminazione
    order: str = Form(""),          # JSON lista 1-based, es. "[3,1,2]"
    pages: str = Form(""),          # JSON lista 1-based, es. "[1,3]" o "2"
    # rotazione
    angle: int = Form(90),
    # watermark
    wm_text: str = Form(""),
    wm_corner: str = Form("br"),
    wm_size: int = Form(48),
    wm_opacity: float = Form(0.2),
    wm_rotate: int = Form(0),
    # firma (immagine: firma disegnata o caricata)
    signature: UploadFile | None = File(None),
    sig_page: int = Form(1),
    # posizionamento: legacy (angolo) oppure manuale (percentuali)
    sig_corner: str = Form("bl"),
    sig_width: float = Form(2.0),
    sig_pos_x: str = Form(""),        # 0-100 (percentuale, centro). se vuoto → usa sig_corner
    sig_pos_y: str = Form(""),
    sig_w_pct: str = Form(""),        # larghezza % pagina
    sig_rot: int = Form(0),           # gradi
    sig_opacity: float = Form(100.0), # 0-100
    # editor v2 — testo cercato / annotazioni / testo libero
    page_num: int = Form(1),
    needle: str = Form(""),
    replacement: str = Form(""),
    text_body: str = Form(""),
    anno_kind: str = Form("highlight"),
    note_icon: str = Form("Note"),
    color: str = Form(""),            # '#rrggbb' (vuoto → default azione)
    annot_opacity: float = Form(0.35),
    x_pct: float = Form(50.0),
    y_pct: float = Form(50.0),
    w_pct: float = Form(30.0),
    h_pct: float = Form(10.0),
    anno_rotate: int = Form(0),
    text_size: float = Form(12.0),
    font_family: str = Form("helv"),
    ink_strokes: str = Form(""),      # JSON [[[x,y],...], ...] in % pagina
    redact_rects: str = Form(""),     # JSON [[x,y,w,h], ...] in % pagina
    redact_fill: str = Form("#000000"),
    replace_fill: str = Form(""),
    # numerazione / intestazione / pagine / moduli
    num_start: int = Form(1),
    num_prefix: str = Form(""),
    num_suffix: str = Form(""),
    num_digits: int = Form(6),
    num_position: str = Form("br"),
    hf_header: str = Form(""),
    hf_footer: str = Form(""),
    hf_position: str = Form("center"),
    hf_size: float = Form(10.0),
    hf_margin: int = Form(24),
    insert_at: int = Form(1),
    insert_count: int = Form(1),
    form_values: str = Form(""),      # JSON {"campo": "valore", ...}
    # sicurezza / OCR (FEAT-B)
    pdf_pw: str = Form(""),           # password apertura (protect/unprotect)
    pdf_pw_owner: str = Form(""),     # password owner (vuoto → casuale)
    allow_print: bool = Form(True),
    allow_copy: bool = Form(True),
    allow_modify: bool = Form(False),
    ocr_lang: str = Form("it"),
    ocr_dpi: int = Form(200),
):
    """Editor PDF. `action` ∈ {reorder,delete,rotate,watermark,signature,
    annotate,note,ink,stamp,text,redact,replace,number,headerfooter,
    insertpage,extract,form,protect,unprotect,searchable}."""
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() != ".pdf":
        raise HTTPException(400, T(request, "api.file_not_pdf", name=name))
    data = file.file.read()
    if not data:
        raise HTTPException(400, T(request, "api.file_empty_named", name=name))
    act = (action or "").strip().lower()
    if act not in ("reorder", "delete", "rotate", "watermark", "signature",
                   "annotate", "note", "ink", "stamp", "text", "redact",
                   "replace", "number", "headerfooter", "insertpage",
                   "extract", "form", "protect", "unprotect", "searchable"):
        raise HTTPException(400, T(request, "api.action_invalid", action=action))

    import json
    try:
        if act == "reorder":
            try:
                order_list = json.loads(order) if order else None
            except json.JSONDecodeError as e:
                raise ValueError(T(request, "api.order_invalid")) from e
            if not order_list:
                raise ValueError(T(request, "api.order_invalid"))
            out = pdfeditconv.reorder_pages(data, order_list)
        elif act == "delete":
            try:
                pg = _expand_pages(data, pages)
            except json.JSONDecodeError as e:
                raise ValueError(T(request, "api.pages_invalid")) from e
            out = pdfeditconv.delete_pages(data, pg)
        elif act == "rotate":
            try:
                pg = _expand_pages(data, pages)
            except json.JSONDecodeError as e:
                raise ValueError(T(request, "api.pages_invalid")) from e
            if not pg:
                pg = list(range(1, pdfeditconv.page_count(data) + 1))
            out = pdfeditconv.rotate_pages(data, pg, angle=angle)
        elif act == "watermark":
            if not (wm_text or "").strip():
                raise ValueError(T(request, "api.watermark_empty"))
            out = pdfeditconv.watermark_text(
                data, wm_text, corner=wm_corner.lower(),
                font_size=wm_size, opacity=wm_opacity, rotate=wm_rotate,
            )
        elif act == "signature":
            sig_img = signature.file.read() if signature and signature.filename else b""
            if not sig_img:
                raise ValueError(T(request, "api.signature_missing"))
            # priorità: sig_pos_x/y + sig_w_pct (nuovi) > sig_corner (legacy) > default
            if (sig_pos_x or "").strip():
                xp = float(sig_pos_x); yp = float(sig_pos_y or 85); wp = float(sig_w_pct or 30)
            else:
                corner = (sig_corner or "bl").lower()
                map_xy = {"tl": (15, 10), "tr": (85, 10), "bl": (15, 90), "br": (85, 90), "center": (50, 50)}
                xp, yp = map_xy.get(corner, (85, 90))
                wp = 30.0  # ~2in su pagina letter è ~30% della larghezza
            out = pdfeditconv.place_signature(
                data, sig_img, page=sig_page,
                x_pct=xp, y_pct=yp, width_pct=wp,
                rotation=sig_rot, opacity=sig_opacity,
            )
        elif act == "annotate":
            out = pdfeditconv.annotate_text(data, page_num, needle, kind=anno_kind,
                                            color=color, opacity=annot_opacity)
        elif act == "note":
            out = pdfeditconv.add_note(data, page_num, x_pct, y_pct, text_body,
                                       icon=note_icon, color=color or "#e2382c")
        elif act == "ink":
            strokes = _json_or_none(ink_strokes, "strokes")
            out = pdfeditconv.add_ink(data, page_num, strokes,
                                      color=color or "#e2382c", width=text_size)
        elif act == "stamp":
            out = pdfeditconv.add_stamp(data, page_num, text_body, x_pct, y_pct,
                                        w_pct=w_pct, h_pct=h_pct,
                                        color=color or "#e2382c",
                                        font_size=text_size, rotate=anno_rotate)
        elif act == "text":
            out = pdfeditconv.add_text(data, page_num, text_body, x_pct, y_pct,
                                       font_size=text_size,
                                       color=color or "#141210", font=font_family)
        elif act == "redact":
            rects = _json_or_none(redact_rects, "rects")
            out = pdfeditconv.redact(data, needle=needle, rects=rects,
                                     page=(page_num if rects else None), fill=redact_fill)
        elif act == "replace":
            out = pdfeditconv.find_replace(data, needle, replacement,
                                           pages=_expand_pages(data, pages), fill=replace_fill or None)
        elif act == "number":
            out = pdfeditconv.number_pages(
                data, start=num_start, prefix=num_prefix, suffix=num_suffix,
                digits=num_digits, position=num_position, font_size=text_size,
                color=color or "#141210", pages=_expand_pages(data, pages),
                margin=hf_margin,
            )
        elif act == "headerfooter":
            out = pdfeditconv.header_footer(
                data, header=hf_header, footer=hf_footer, position=hf_position,
                font_size=hf_size, color=color or "#141210",
                pages=_expand_pages(data, pages), margin=hf_margin,
                date=time.strftime("%Y-%m-%d"),
            )
        elif act == "insertpage":
            out = pdfeditconv.insert_blank_page(data, at=insert_at, count=insert_count)
        elif act == "extract":
            out = pdfeditconv.extract_pages(data, _expand_pages(data, pages))
        elif act == "protect":
            if not pdf_pw:
                raise HTTPException(400, T(request, "api.password_required"))
            out = pdfeditconv.protect(
                data, pdf_pw, owner_pw=pdf_pw_owner,
                allow_print=allow_print, allow_copy=allow_copy,
                allow_modify=allow_modify,
            )
        elif act == "unprotect":
            try:
                out = pdfeditconv.unprotect(data, pdf_pw)
            except pdfeditconv.PasswordError as e:
                raise HTTPException(400, T(request, "api.password_wrong")) from e
        elif act == "searchable":
            try:
                pg = _expand_pages(data, pages) if (pages or "").strip() else None
            except json.JSONDecodeError as e:
                raise ValueError(T(request, "api.pages_invalid")) from e
            try:
                out = exconv.searchable_pdf(
                    data, lang=((ocr_lang or "it").strip() or "eng"),
                    dpi=ocr_dpi, pages=pg,
                )
            except exconv.OcrEngineMissingError as e:
                raise HTTPException(501, T(request, "api.ocr_not_installed")) from e
        else:  # form
            values = _json_or_none(form_values, "form_values")
            if not isinstance(values, dict):
                raise ValueError("form_values: atteso oggetto JSON {campo: valore}")
            out = pdfeditconv.fill_form(data, values)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, T(request, "api.editor_failed", detail=str(e)))

    suffix = {"reorder": "re", "delete": "del", "rotate": "rot",
              "watermark": "wm", "signature": "sig", "annotate": "anno",
              "note": "note", "ink": "ink", "stamp": "stamp", "text": "txt",
              "redact": "red", "replace": "repl", "number": "num",
              "headerfooter": "hf", "insertpage": "blank",
              "extract": "extract", "form": "form",
              "protect": "prot", "unprotect": "unlock",
              "searchable": "ocr"}[act]
    payload = _save_pdf_output(out, name, suffix)
    payload["action"] = act
    return payload


@app.post("/api/pdf-form-fields")
def api_pdf_form_fields(request: Request, file: UploadFile = File(...)):
    """Elenca i campi modulo di un PDF (per la UI di compilazione)."""
    name = Path(file.filename or "").name
    if Path(name).suffix.lower() != ".pdf":
        raise HTTPException(400, T(request, "api.file_not_pdf", name=name))
    data = file.file.read()
    if not data:
        raise HTTPException(400, T(request, "api.file_empty_named", name=name))
    try:
        return {"fields": pdfeditconv.form_fields(data)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, T(request, "api.editor_failed", detail=str(e)))


@app.post("/api/signature-generate")
def api_signature_generate(
    request: Request,
    name: str = Form(...),
    style: str = Form("greatvibes"),
    size: int = Form(96),
    color: str = Form("#000000"),
):
    """Genera una calligrafica PNG da nome+stile+colore (4 font bundled)."""
    try:
        png = sconv.generate(name.strip(), style.lower(), max(24, min(600, size)), color)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, T(request, "api.sign_gen_failed", detail=str(e)))
    return Response(content=png, media_type="image/png",
                    headers={"Content-Disposition": 'attachment; filename="firm.png"'})


@app.get("/api/signature-styles")
def api_signature_styles():
    """Elenco font calligrafici disponibili (per il selettore UI)."""
    return {"styles": [
        {"key": s.key, "label": s.label, "file": s.file} for s in sconv.list_styles()
    ]}


app.mount("/", StaticFiles(directory=str(BASE_DIR / "static"), html=True), name="static")
