"""Test API di conversione (TestClient senza server)."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402
from converters import documents as docconv  # noqa: E402
from converters import video as vidconv  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


def test_convert_single_png_to_jpeg(client):
    res = client.post(
        "/api/convert",
        data={"fmt": "jpeg"},
        files=[("files", ("a.png", _png(), "image/png"))],
    )
    assert res.status_code == 200, res.text
    r = res.json()["results"][0]
    assert r["name"].endswith(".jpg")
    dl = client.get(r["download"])
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("image/jpeg")


def test_convert_multi_batch_and_zip(client):
    files = [
        ("files", (f"s{i}.png", _png(), "image/png")) for i in range(3)
    ]
    res = client.post("/api/convert", data={"fmt": "webp"}, files=files)
    assert res.status_code == 200
    names = [r["name"] for r in res.json()["results"]]
    assert len(names) == 3

    # collisione nome: stessa base in batch -> nome univoco
    res2 = client.post(
        "/api/convert",
        data={"fmt": "png"},
        files=[("files", ("dup.png", _png(), "image/png"))] * 2,
    )
    assert res2.status_code == 200
    n2 = [r["name"] for r in res2.json()["results"]]
    assert len(set(n2)) == 2, n2

    zip_res = client.get(f"/api/download?names={','.join(names)}")
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"


def test_reject_unknown_format(client):
    res = client.post(
        "/api/convert",
        data={"fmt": "bmp"},
        files=[("files", ("a.png", _png(), "image/png"))],
    )
    assert res.status_code == 400


def test_reject_unsupported_source(client):
    res = client.post(
        "/api/convert",
        data={"fmt": "jpeg"},
        files=[("files", ("nota.txt", b"ciao", "text/plain"))],
    )
    assert res.status_code == 422


def test_convert_with_quality_and_max_side(client):
    res = client.post(
        "/api/convert",
        data={"fmt": "jpeg", "quality": "70", "max_side": "64"},
        files=[("files", ("big.png", _png(size=(320, 180)), "image/png"))],
    )
    assert res.status_code == 200, res.text
    r = res.json()["results"][0]
    assert r["width"] == 64
    assert r["height"] == 36


def _png(size=(24, 24), color=(255, 0, 90)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_invalid_quality_defaults_not_error(client):
    res = client.post(
        "/api/convert",
        data={"fmt": "webp", "quality": "9000000000", "max_side": "-3"},
        files=[("files", ("a.png", _png(), "image/png"))],
    )
    assert res.status_code == 200, res.text
    assert res.json()["results"][0]["name"].endswith(".webp")


def test_config_endpoint(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    assert ".heic" in body["supported_in"]
    assert "gif" in body["supported_out"]


def _anim_gif(size=(20, 20)):
    from PIL import Image

    fr = [Image.new("RGB", size, c).convert("P") for c in [(0, 0, 0), (255, 0, 0)]]
    buf = io.BytesIO()
    fr[0].save(buf, format="GIF", save_all=True, append_images=fr[1:], duration=80, loop=0)
    return buf.getvalue()


def test_convert_animated_gif_to_gif(client):
    res = client.post(
        "/api/convert",
        data={"fmt": "gif"},
        files=[("files", ("a.gif", _anim_gif(), "image/gif"))],
    )
    assert res.status_code == 200, res.text
    r = res.json()["results"][0]
    assert r["name"].endswith(".gif")
    dl = client.get(r["download"])
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("image/gif")


def test_reject_batch_over_limit(client):
    from app.main import MAX_BATCH_FILES

    files = [("files", (f"s{i}.png", _png(), "image/png")) for i in range(MAX_BATCH_FILES + 1)]
    res = client.post("/api/convert", data={"fmt": "jpeg"}, files=files)
    assert res.status_code == 400, res.text


# ---------------- M3: Documenti ----------------

def _mini_pdf() -> bytes:
    """3 pagine di PDF generato dalle immagini."""
    return docconv.images_to_pdf([
        ("a.png", _png(size=(120, 80), color=(200, 30, 30))),
        ("b.png", _png(size=(120, 80), color=(30, 200, 30))),
        ("c.png", _png(size=(120, 80), color=(30, 30, 200))),
    ])


def test_convert_pdf_to_images_jpeg_all_pages(client):
    pdf = _mini_pdf()
    res = client.post(
        "/api/convert-pdf-to-images",
        data={"fmt": "jpeg", "dpi": "150", "quality": "80"},
        files=[("file", ("doc.pdf", pdf, "application/pdf"))],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pages"] == 3
    names = [r["name"] for r in body["results"]]
    assert len(names) == 3
    assert all(n.endswith(".jpeg") for n in names)
    # download funziona e restituisce immagine valida
    dl = client.get(body["results"][0]["download"])
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("image/jpeg")
    from PIL import Image

    Image.open(io.BytesIO(dl.content)).verify()


def test_convert_pdf_to_images_rejects_bad_fmt(client):
    res = client.post(
        "/api/convert-pdf-to-images",
        data={"fmt": "gif"},
        files=[("file", ("d.pdf", _mini_pdf(), "application/pdf"))],
    )
    assert res.status_code == 400


def test_convert_pdf_to_images_rejects_empty_file(client):
    res = client.post(
        "/api/convert-pdf-to-images",
        data={"fmt": "jpeg"},
        files=[("file", ("d.pdf", b"", "application/pdf"))],
    )
    assert res.status_code == 400


def test_convert_pdf_to_images_rejects_garbage(client):
    res = client.post(
        "/api/convert-pdf-to-images",
        data={"fmt": "jpeg"},
        files=[("file", ("d.pdf", b"not-a-pdf", "application/pdf"))],
    )
    assert res.status_code == 400


def test_convert_pdf_to_images_zip_batch(client):
    res = client.post(
        "/api/convert-pdf-to-images",
        data={"fmt": "png"},
        files=[("file", ("doc.pdf", _mini_pdf(), "application/pdf"))],
    )
    assert res.status_code == 200
    names = [r["name"] for r in res.json()["results"]]
    zip_res = client.get(f"/api/download?names={','.join(names)}")
    assert zip_res.status_code == 200
    assert zip_res.headers["content-type"] == "application/zip"


def test_convert_images_to_pdf_single(client):
    res = client.post(
        "/api/convert-images-to-pdf",
        files=[("files", ("solo.png", _png(), "image/png"))],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["images"] == 1
    assert body["results"][0]["name"].endswith(".pdf")
    dl = client.get(body["results"][0]["download"])
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("application/pdf")
    assert dl.content[:4] == b"%PDF"


def test_convert_images_to_pdf_multi(client):
    files = [
        ("files", (f"f{i}.png", _png(size=(80, 60)), "image/png")) for i in range(4)
    ]
    res = client.post("/api/convert-images-to-pdf", files=files)
    assert res.status_code == 200, res.text
    assert res.json()["images"] == 4


def test_convert_images_to_pdf_max_side(client):
    res = client.post(
        "/api/convert-images-to-pdf",
        data={"max_side": "50"},
        files=[("files", ("big.png", _png(size=(400, 200)), "image/png"))],
    )
    assert res.status_code == 200, res.text


def test_convert_images_to_pdf_rejects_non_image(client):
    res = client.post(
        "/api/convert-images-to-pdf",
        files=[("files", ("nota.txt", b"ciao", "text/plain"))],
    )
    assert res.status_code == 400


def test_config_documents_section(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    docs = body["documents"]
    assert "jpeg" in docs["pdf_out"]


# ---------------- M4: Tool (merge / split / rename) ----------------

def test_merge_pdfs_api(client):
    a = docconv.images_to_pdf([("x.png", _png(size=(80, 60), color=(200, 30, 30)))])
    b = docconv.images_to_pdf([("y.png", _png(size=(80, 60), color=(30, 30, 200)))])
    res = client.post(
        "/api/merge-pdfs",
        files=[
            ("files", ("a.pdf", a, "application/pdf")),
            ("files", ("b.pdf", b, "application/pdf")),
        ],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["inputs"] == 2
    assert body["pages"] == 2
    r = body["results"][0]
    assert r["name"].endswith(".pdf")
    dl = client.get(r["download"])
    assert dl.status_code == 200
    assert dl.content[:4] == b"%PDF"


def test_merge_pdfs_rejects_non_pdf(client):
    res = client.post(
        "/api/merge-pdfs",
        files=[("files", ("a.txt", b"ciao", "text/plain"))],
    )
    assert res.status_code == 400


def test_merge_pdfs_requires_two(client):
    a = docconv.images_to_pdf([("x.png", _png())])
    res = client.post("/api/merge-pdfs", files=[("files", ("a.pdf", a, "application/pdf"))])
    assert res.status_code == 200  # 1 PDF è accettato: produce un PDF valido
    assert res.json()["pages"] == 1


def test_split_pdf_api(client):
    pdf = _mini_pdf()  # 3 pagine
    res = client.post(
        "/api/split-pdf",
        data={"start": "2", "end": "3"},
        files=[("file", ("doc.pdf", pdf, "application/pdf"))],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pages"] == 2
    assert body["total_pages_source"] == 3
    dl = client.get(body["results"][0]["download"])
    assert dl.status_code == 200
    assert dl.content[:4] == b"%PDF"


def test_split_pdf_rejects_empty(client):
    res = client.post(
        "/api/split-pdf",
        files=[("file", ("d.pdf", b"", "application/pdf"))],
    )
    assert res.status_code == 400


def _pdf_edit_post(client, payload_files, data=None):
    return client.post(
        "/api/pdf-edit",
        data=data or {},
        files=payload_files,
    )


def test_pdf_edit_rotate_all_pages(client):
    pdf = _mini_pdf()  # 3 pagine
    res = _pdf_edit_post(
        client,
        [("file", ("d.pdf", pdf, "application/pdf"))],
        data={"action": "rotate", "pages": "tutte", "angle": "90"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["action"] == "rotate"
    dl = client.get(body["results"][0]["download"])
    assert dl.status_code == 200 and dl.content[:4] == b"%PDF"
    import pymupdf
    doc = pymupdf.Document(stream=dl.content)
    assert all(p.rotation == 90 for p in [doc[i] for i in range(doc.page_count)])


def test_pdf_edit_delete_pages(client):
    pdf = _mini_pdf()  # 3 pagine
    res = _pdf_edit_post(
        client,
        [("file", ("d.pdf", pdf, "application/pdf"))],
        data={"action": "delete", "pages": "[2]"},
    )
    assert res.status_code == 200, res.text
    import pymupdf
    doc = pymupdf.Document(stream=client.get(res.json()["results"][0]["download"]).content)
    assert doc.page_count == 2


def test_pdf_edit_reorder(client):
    pdf = _mini_pdf()  # 3 pagine
    res = _pdf_edit_post(
        client,
        [("file", ("d.pdf", pdf, "application/pdf"))],
        data={"action": "reorder", "order": "[3,1,2]"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    import pymupdf
    doc = pymupdf.Document(stream=client.get(body["results"][0]["download"]).content)
    assert doc.page_count == 3
    # la prima pagina del nuovo doc deve essere l'originale pagina 3 (blu), non la 1 (rossa)
    pix = doc[0].get_pixmap(dpi=40)
    # media del blu più alta che del rosso (pagina origine = blu)
    import statistics
    def chan(sel):
        vals = [pix.samples[i + sel] for i in range(0, pix.width * pix.height * pix.n, pix.n)]
        return statistics.mean(vals)
    assert chan(2) > chan(0)


def test_pdf_edit_watermark(client):
    pdf = _mini_pdf()
    res = _pdf_edit_post(
        client,
        [("file", ("d.pdf", pdf, "application/pdf"))],
        data={"action": "watermark", "wm_text": "CONFIDENZIALE", "wm_corner": "center"},
    )
    assert res.status_code == 200, res.text


def test_pdf_edit_signature(client):
    pdf = _mini_pdf()
    sig = _png(size=(120, 40), color=(10, 90, 200))
    res = client.post(
        "/api/pdf-edit",
        data={"action": "signature", "sig_page": "1", "sig_corner": "br"},
        files=[
            ("file", ("d.pdf", pdf, "application/pdf")),
            ("signature", ("sig.png", sig, "image/png")),
        ],
    )
    assert res.status_code == 200, res.text


def test_pdf_edit_signature_positional(client):
    """Nuovo: posizionamento libero via percentuali."""
    pdf = _mini_pdf()
    sig = _png(size=(120, 40), color=(10, 90, 200))
    res = client.post(
        "/api/pdf-edit",
        data={
            "action": "signature", "sig_page": "1",
            "sig_pos_x": "25", "sig_pos_y": "60",
            "sig_w_pct": "40", "sig_rot": "15", "sig_opacity": "80",
        },
        files=[
            ("file", ("d.pdf", pdf, "application/pdf")),
            ("signature", ("sig.png", sig, "image/png")),
        ],
    )
    assert res.status_code == 200, res.text


def test_pdf_edit_signature_missing_file(client):
    """Firma: nessuna immagine → 400."""
    pdf = _mini_pdf()
    res = client.post(
        "/api/pdf-edit",
        data={"action": "signature", "sig_page": "1"},
        files=[("file", ("d.pdf", pdf, "application/pdf"))],
    )
    assert res.status_code == 400


def test_pdf_edit_signature_rejects_non_image(client):
    pdf = _mini_pdf()
    res = client.post(
        "/api/pdf-edit",
        data={"action": "signature", "sig_page": "1"},
        files=[
            ("file", ("d.pdf", pdf, "application/pdf")),
            ("signature", ("sig.png", b"not-a-png", "image/png")),
        ],
    )
    assert res.status_code == 400


def test_signature_generate_ok(client):
    res = client.post(
        "/api/signature-generate",
        data={"name": "Mario Rossi", "style": "caveat", "size": "96"},
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"
    # PIL la apre
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(res.content))
    assert im.width > 0 and im.height > 0


def test_signature_generate_rejects_empty_name(client):
    res = client.post(
        "/api/signature-generate",
        data={"name": "   ", "style": "caveat"},
    )
    assert res.status_code == 400, res.text


def test_signature_generate_rejects_unknown_style(client):
    res = client.post(
        "/api/signature-generate",
        data={"name": "Mario", "style": "xyznope"},
    )
    assert res.status_code == 400, res.text


def test_signature_styles_lists_four_font(client):
    res = client.get("/api/signature-styles")
    assert res.status_code == 200, res.text
    names = [s["key"] for s in res.json()["styles"]]
    assert set(names) == {"caveat", "dancing", "greatvibes", "pacifico"}


def test_pdf_edit_rejects_non_pdf(client):
    res = _pdf_edit_post(
        client,
        [("file", ("x.txt", b"ciao", "text/plain"))],
        data={"action": "rotate"},
    )
    assert res.status_code == 400


def test_pdf_edit_rejects_invalid_action(client):
    res = _pdf_edit_post(
        client,
        [("file", ("d.pdf", _mini_pdf(), "application/pdf"))],
        data={"action": "explode"},
    )
    assert res.status_code == 400


def test_rename_preview_api(client):
    res = client.post(
        "/api/rename-preview",
        data={"names": ["a.jpg", "b.jpg"], "mode": "number", "value": "foto", "start": "1", "step": "1", "sep": "-"},
    )
    assert res.status_code == 200, res.text
    mapping = res.json()["mapping"]
    assert mapping == [
        {"from": "a.jpg", "to": "foto-1.jpg"},
        {"from": "b.jpg", "to": "foto-2.jpg"},
    ]


def test_rename_batch_api_returns_zip(client):
    res = client.post(
        "/api/rename-batch",
        data={"mode": "prefix", "value": "viaggio"},
        files=[
            ("files", ("a.jpg", _png(), "image/jpeg")),
            ("files", ("b.png", _png(), "image/png")),
        ],
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    assert "versocon_renamed.zip" in res.headers.get("content-disposition", "")
    import zipfile

    zf = zipfile.ZipFile(io.BytesIO(res.content))
    inner = zf.namelist()
    assert inner == ["viaggioa.jpg", "viaggiob.png"], inner


# ---------------- M4: Video (transcode via ffmpeg) ----------------

def test_config_video_section(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    vid = res.json()["video"]
    assert ".mp4" in vid["in"]
    assert "mp4" in vid["out"] and "webm" in vid["out"]
    assert isinstance(vid["ffmpeg_available"], bool)


def test_convert_video_rejects_non_video(client):
    res = client.post(
        "/api/convert-video",
        files=[("file", ("nota.txt", b"ciao", "text/plain"))],
    )
    assert res.status_code == 400


def test_convert_video_rejects_empty(client):
    res = client.post(
        "/api/convert-video",
        files=[("file", ("a.mp4", b"", "video/mp4"))],
    )
    assert res.status_code == 400


def test_convert_video_bad_fmt(client):
    res = client.post(
        "/api/convert-video",
        data={"fmt": "avi"},
        files=[("file", ("a.mp4", b"xxx", "video/mp4"))],
    )
    assert res.status_code == 400


def test_convert_video_missing_ffmpeg_503(client):
    if vidconv._find_ffmpeg():
        pytest.skip("ffmpeg installato: questo test copre il caso assente")
    res = client.post(
        "/api/convert-video",
        files=[("file", ("a.mp4", b"xxx", "video/mp4"))],
    )
    assert res.status_code == 503, res.text
    assert "ffmpeg" in res.json()["detail"].lower()


def test_convert_video_real_mp4(client):
    """Transcode end-to-end con un frame sintetico: solo se ffmpeg è installato."""
    if vidconv._find_ffmpeg() is None:
        pytest.skip("ffmpeg non installato")
    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src.mp4"
        cmd = [
            vidconv._find_ffmpeg(), "-y",
            "-f", "lavfi", "-i", "testsrc=duration=1:size=128x96:rate=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-loglevel", "error", str(src),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        if r.returncode != 0:
            pytest.skip("impossibile generare sorgente")
        data = src.read_bytes()
        res = client.post(
            "/api/convert-video",
            data={"fmt": "mp4"},
            files=[("file", ("src.mp4", data, "video/mp4"))],
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["results"][0]["name"].endswith(".mp4")
        assert body["results"][0]["size"] > 0
        dl = client.get(body["results"][0]["download"])
        assert dl.status_code == 200
        assert len(dl.content) > 0
