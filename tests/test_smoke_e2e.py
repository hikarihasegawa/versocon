"""Smoke E2E su browser reale: l'app vera, servita da uvicorn, percorsa dall'UI.

Non fa parte della run normale: viene raccolto solo con ``VERSOCON_E2E=1`` e
Playwright installato (``pip install -r requirements-e2e.txt`` +
``python -m playwright install chromium``). La CI lo esegue nel job ``smoke-e2e``.

Copre il flusso principale: benvenuto al primo avvio (lingua live, opt-in
update spento di default, zero chiamate di rete), conversione foto con download
reale del file, editor PDF con anteprima pdf.js e anteprima live. Tutto in una
OUT_DIR temporanea di sessione: nessun dato utente viene toccato.
"""
from __future__ import annotations

import io
import os
import socket
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("VERSOCON_E2E") != "1",
    reason="smoke E2E: serve VERSOCON_E2E=1 e Playwright installato",
)

playwright_sync = pytest.importorskip("playwright.sync_api")

EXPECT_TIMEOUT = 20_000
WELCOME_TITLE = {"it": "Benvenuto in VersoCon", "en": "Welcome to VersoCon"}


@pytest.fixture(scope="session")
def base_url() -> str:
    import uvicorn

    from app.main import app

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started:
        assert time.monotonic() < deadline, "server E2E non pronto in 30s"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def browser():
    with playwright_sync.sync_playwright() as pw:
        chromium = pw.chromium.launch()
        yield chromium
        chromium.close()


class SmokePage:
    """Facciata minima: pagina, richieste osservate e igiene della console."""

    def __init__(self, page):
        self.page = page
        self.requests: list[str] = []
        self.errors: list[str] = []
        page.on("request", lambda r: self.requests.append(r.url))
        page.on("console", self._on_console)
        page.on("pageerror", lambda exc: self.errors.append(f"pageerror: {exc}"))

    def _on_console(self, msg):
        if msg.type == "error" and "favicon" not in msg.text.lower():
            self.errors.append(msg.text)

    def goto(self, base_url: str) -> None:
        self.page.goto(base_url + "/", wait_until="load")

    def close_welcome(self) -> None:
        dlg = self.page.locator("#welcomeDlg")
        if dlg.is_visible():
            self.page.click("#welcomeOk")
            dlg.wait_for(state="hidden")

    def update_calls(self) -> list[str]:
        return [u for u in self.requests if "/api/update" in u]


@pytest.fixture()
def smoke(browser):
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    smoke = SmokePage(page)
    yield smoke
    context.close()
    assert smoke.errors == [], f"errori console/browser: {smoke.errors}"


def test_primo_avvio_benvenuto_lingua_e_optin_off(smoke, base_url):
    page = smoke.page
    smoke.goto(base_url)

    dlg = page.locator("#welcomeDlg")
    expect = playwright_sync.expect
    expect(dlg).to_be_visible(timeout=EXPECT_TIMEOUT)
    assert page.evaluate("document.activeElement && document.activeElement.id") == "welcomeOk"

    lang = page.evaluate("window.IC.lang")
    target = "en" if lang == "it" else "it"
    page.select_option("#welcomeLang", target)
    expect(page.locator("#welcomeTitle")).to_have_text(WELCOME_TITLE[target], timeout=EXPECT_TIMEOUT)

    page.click("#welcomeOk")
    expect(dlg).not_to_be_visible(timeout=EXPECT_TIMEOUT)
    # l'evento `close` del dialog è accodato: attende che lo stato sia salvato
    page.wait_for_function(
        "() => localStorage.getItem('versocon.onboarded') === '1'", timeout=EXPECT_TIMEOUT
    )
    assert page.evaluate("localStorage.getItem('versocon.updatecheck')") == "0"
    assert smoke.update_calls() == []

    page.reload(wait_until="load")
    expect(dlg).not_to_be_visible(timeout=EXPECT_TIMEOUT)
    assert smoke.update_calls() == []


@pytest.fixture()
def png_file(tmp_path: Path) -> Path:
    from PIL import Image

    path = tmp_path / "e2e-foto.png"
    Image.new("RGB", (64, 48), (200, 40, 40)).save(path)
    return path


def test_conversione_foto_con_download_reale(smoke, base_url, png_file):
    from PIL import Image

    page = smoke.page
    smoke.goto(base_url)
    smoke.close_welcome()

    page.set_input_files("#fileInput", str(png_file))
    expect = playwright_sync.expect
    expect(page.locator("#fileList li.file")).to_have_count(1, timeout=EXPECT_TIMEOUT)

    page.click('.seg-btn[data-fmt="jpeg"]')
    page.click("#btnConvert")
    link = page.locator("#resultsList a[download]")
    expect(link).to_be_visible(timeout=EXPECT_TIMEOUT)
    assert page.locator("#resultsList .fname").inner_text() == "e2e-foto.jpg"

    with page.expect_download(timeout=EXPECT_TIMEOUT) as dl:
        link.click()
    download = dl.value
    assert download.suggested_filename == "e2e-foto.jpg"
    data = Path(download.path()).read_bytes()
    assert data[:2] == b"\xff\xd8"
    img = Image.open(io.BytesIO(data))
    assert (img.format, img.size) == ("JPEG", (64, 48))


def test_editor_pdf_anteprima_e_live(smoke, base_url, tmp_path: Path):
    import fitz

    pdf = tmp_path / "e2e-doc.pdf"
    doc = fitz.open()
    for n in range(2):
        p = doc.new_page(width=300, height=400)
        p.insert_text((60, 100), f"Pagina {n + 1}", fontsize=20)
    doc.save(pdf)
    doc.close()

    page = smoke.page
    smoke.goto(base_url)
    smoke.close_welcome()
    page.click("#tabBtn-pdf")
    page.click('#tabPdf .subtabs .subtab[data-sub="pdf-edit"]')
    page.set_input_files("#edPdfIn", str(pdf))

    expect = playwright_sync.expect
    expect(page.locator("#edPreview")).to_be_visible(timeout=EXPECT_TIMEOUT)
    expect(page.locator("#edPgLabel")).to_have_text("1 / 2", timeout=EXPECT_TIMEOUT)
    dims = page.evaluate(
        "() => { const c = document.getElementById('edCanvas'); return [c.width, c.height]; }"
    )
    assert dims[0] > 0 and dims[1] > 0

    # La rotazione non ha anteprima server finché non scegli una direzione:
    # l'anteprima live si verifica con la filigrana (azione con parametri attivi).
    page.click('#edTools .ed-tool[data-tool="watermark"]')
    prev = page.locator("#edPrevImg")
    expect(prev).to_be_visible(timeout=EXPECT_TIMEOUT)
    assert page.evaluate(
        "() => { const i = document.getElementById('edPrevImg');"
        " return i.complete && i.naturalWidth > 0; }"
    )


def test_editor_ruota_pannello_toggle_e_catena(smoke, base_url, tmp_path: Path):
    """Regressione (2026-09-17): verso unico percepito e rotazione «persa» dopo
    Applica. Copre: pannello parametri sotto il tasto premuto + toggle al
    ripremere, verso 270°, anteprima che non ri-applica, doppio click bloccato,
    catena rotate→watermark con rotazione conservata."""
    import fitz

    pdf = tmp_path / "e2e-ruota.pdf"
    doc = fitz.open()
    p = doc.new_page(width=300, height=400)
    p.insert_text((20, 40), "MARK-TOP", fontsize=26)
    doc.save(pdf)
    doc.close()

    page = smoke.page
    smoke.goto(base_url)
    smoke.close_welcome()
    page.click("#tabBtn-pdf")
    page.click('#tabPdf .subtabs .subtab[data-sub="pdf-edit"]')
    page.set_input_files("#edPdfIn", str(pdf))
    expect = playwright_sync.expect
    expect(page.locator("#edPreview")).to_be_visible(timeout=EXPECT_TIMEOUT)

    def block_state(tool: str) -> dict:
        return page.evaluate(
            """(tool) => { const b = document.querySelector('#edTools .ed-tool[data-tool="' + tool + '"]');
                 const el = document.getElementById('edBlock-' + tool);
                 return {hidden: el.hidden, expanded: b.getAttribute('aria-expanded'),
                         inGrid: el.classList.contains('ed-block-inline'),
                         gap: Math.round(el.getBoundingClientRect().top - b.getBoundingClientRect().bottom)}; }""",
            tool,
        )

    # rotate è l'azione attiva di default: pannello aperto subito sotto il tasto
    st = block_state("rotate")
    assert not st["hidden"] and st["expanded"] == "true" and st["inGrid"]
    assert 0 <= st["gap"] < 60, f"pannello non adiacente al tasto: {st}"

    # ripremere lo stesso tasto = collassa; ancora = riespande
    page.click('#edTools .ed-tool[data-tool="rotate"]')
    assert block_state("rotate")["hidden"] is True
    page.click('#edTools .ed-tool[data-tool="rotate"]')
    st = block_state("rotate")
    assert not st["hidden"] and st["expanded"] == "true"

    # altra funzione: il pannello si sposta sotto il nuovo tasto
    page.click('#edTools .ed-tool[data-tool="watermark"]')
    st = block_state("watermark")
    assert not st["hidden"] and st["inGrid"] and 0 <= st["gap"] < 60
    assert block_state("rotate")["hidden"] is True

    # verso antiorario con la freccia: applicato e verificato sull'artefatto reale
    page.click('#edTools .ed-tool[data-tool="rotate"]')
    page.click("#edRotLeft")
    expect(page.locator("#edPrevImg")).to_be_visible(timeout=EXPECT_TIMEOUT)
    # coerenza anteprima: canvas e PNG server entrambi orizzontali, PNG non stirato
    m = page.evaluate(
        """() => { const c = document.getElementById('edCanvas');
             const i = document.getElementById('edPrevImg');
             const r = i.getBoundingClientRect();
             return {canvas: [c.width, c.height], nat: [i.naturalWidth, i.naturalHeight],
                     css: [r.width, r.height]}; }"""
    )
    assert m["canvas"][0] > m["canvas"][1], f"canvas non ruotato: {m}"
    assert m["nat"][0] > m["nat"][1], f"PNG server non ruotato: {m}"
    ar_nat = m["nat"][0] / m["nat"][1]
    ar_css = m["css"][0] / m["css"][1]
    assert abs(ar_nat - ar_css) < 0.05, f"PNG stirato: natural {ar_nat:.2f} vs css {ar_css:.2f}"
    page.click("#btnEdApply")
    expect(page.locator("#edDownload")).to_be_visible(timeout=EXPECT_TIMEOUT)
    page.wait_for_timeout(800)
    r = page.request.get(base_url + page.get_attribute("#edDownload", "href"))
    assert r.ok
    out = fitz.open(stream=r.body(), filetype="pdf")
    assert out[0].rotation == 270, f"rotation applicata: {out[0].rotation}"
    out.close()

    # l'anteprima non ri-applica l'azione appena applicata (niente effetto doppio)
    assert page.evaluate("() => document.getElementById('edPrevImg').hidden") is True

    # secondo click senza toccare le frecce: nessuna rotazione doppia, avviso chiaro
    page.click("#btnEdApply")
    page.wait_for_timeout(500)
    msg = page.evaluate("() => window.IC.t('dyn.rot_choose')")
    assert msg in page.locator("#toast").text_content()
    r = page.request.get(base_url + page.get_attribute("#edDownload", "href"))
    out = fitz.open(stream=r.body(), filetype="pdf")
    assert out[0].rotation == 270
    out.close()

    # catena: watermark sul documento ruotato; l'aspetto resta ruotato e la
    # rotazione viene materializzata nel contenuto (/Rotate 0, rect landscape)
    page.click('#edTools .ed-tool[data-tool="watermark"]')
    page.fill("#edWmText", "VERIFICA-E2E")
    page.click("#btnEdApply")
    page.wait_for_timeout(1500)
    r = page.request.get(base_url + page.get_attribute("#edDownload", "href"))
    out = fitz.open(stream=r.body(), filetype="pdf")
    assert out[0].rotation == 0 and out[0].rect.width > out[0].rect.height
    assert "VERIFICA-E2E" in out[0].get_text()
    out.close()
