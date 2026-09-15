"""Test editor PDF v2: annotazioni, testo, redazione, trova&sostituisci,
numerazione, intestazioni, pagine, moduli.

Copre il livello converter (`converters/pdfedit.py`) e il contratto HTTP
(`POST /api/pdf-edit` nuove azioni, `POST /api/pdf-form-fields`) con
round-trip reale del PDF prodotto via `/api/file/<name>`.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402

from app.main import app  # noqa: E402
from converters import pdfedit  # noqa: E402


def _make_pdf(n_pages: int = 2, text: str = "Ciao mondo") -> bytes:
    doc = pymupdf.Document()
    for i in range(n_pages):
        page = doc.new_page(width=300, height=200)
        page.insert_text((20, 100), f"PAGINA-{i + 1} {text}", fontsize=18)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_colored_pdf() -> bytes:
    """Pagina con fascia colorata a sinistra e testo sopra: serve a verificare che
    la sostituzione preservi lo sfondo (non lo copra con un box bianco/nero)."""
    doc = pymupdf.Document()
    page = doc.new_page(width=300, height=200)
    page.draw_rect(pymupdf.Rect(0, 0, 90, 200), color=None, fill=(0.12, 0.23, 0.37))
    page.insert_text((20, 60), "Eden", fontsize=18, color=(0.9, 0.75, 0.3))
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_rotated_pdf() -> bytes:
    """Pagina con testo ruotato di 90° (come le fasce laterali delle copertine)."""
    doc = pymupdf.Document()
    page = doc.new_page(width=300, height=200)
    page.insert_text((60, 180), "EDEN", fontsize=18, rotate=90)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_index_pdf() -> bytes:
    """Riga in un'unica span (come le voci d'indice): la sostituzione deve
    posizionarsi dove sta la parola trovata, non all'inizio della riga."""
    doc = pymupdf.Document()
    page = doc.new_page(width=300, height=200)
    page.insert_text((20, 100), "01 Cosa rende Eden diversa", fontsize=14)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pixel(pdf: bytes, x: int, y: int) -> tuple[int, int, int]:
    """Colore RGB del pixel (x, y) della prima pagina renderizzata a 72 dpi."""
    pix = _load(pdf)[0].get_pixmap(dpi=72)
    i = (y * pix.width + x) * pix.n
    return tuple(pix.samples[i:i + 3])


def _make_form_pdf() -> bytes:
    doc = pymupdf.Document()
    page = doc.new_page(width=300, height=200)
    w = pymupdf.Widget()
    w.rect = pymupdf.Rect(20, 20, 200, 50)
    w.field_name = "nome"
    w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
    w.field_value = ""
    page.add_widget(w)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _load(b: bytes) -> pymupdf.Document:
    return pymupdf.Document(stream=b, filetype="pdf")


def _annot_types(b: bytes, page: int = 1) -> list[str]:
    doc = _load(b)
    return [a.type[1] for a in (doc[page - 1].annots() or [])]


@pytest.fixture()
def client():
    return TestClient(app)


def _post_edit(client, pdf: bytes, **fields):
    name = fields.pop("name", "doc.pdf")
    data = {k: str(v) for k, v in fields.items()}
    return client.post("/api/pdf-edit", data=data,
                       files=[("file", (name, pdf, "application/pdf"))])


# --------------------------------------------------------------------------
# Annotazioni su testo
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kind,expected", [
    ("highlight", "Highlight"), ("underline", "Underline"),
    ("strikeout", "StrikeOut"), ("squiggly", "Squiggly"),
])
def test_annotate_all_kinds(kind, expected):
    out = pdfedit.annotate_text(_make_pdf(1), 1, "Ciao", kind=kind)
    assert _annot_types(out) == [expected]


def test_annotate_color_and_opacity():
    doc = _load(pdfedit.annotate_text(_make_pdf(1), 1, "Ciao", color="#00ff00", opacity=0.5))
    annot = next(doc[0].annots())
    assert annot.colors["stroke"][1] == pytest.approx(1.0)
    assert annot.opacity == pytest.approx(0.5, abs=0.01)


def test_annotate_text_not_found():
    with pytest.raises(ValueError, match="non trovato"):
        pdfedit.annotate_text(_make_pdf(1), 1, "assente")


def test_annotate_empty_needle_rejected():
    with pytest.raises(ValueError, match="vuoto"):
        pdfedit.annotate_text(_make_pdf(1), 1, "   ")


def test_annotate_bad_kind_rejected():
    with pytest.raises(ValueError, match="non valido"):
        pdfedit.annotate_text(_make_pdf(1), 1, "Ciao", kind="glow")


def test_annotate_bad_color_rejected():
    with pytest.raises(ValueError, match="#rrggbb"):
        pdfedit.annotate_text(_make_pdf(1), 1, "Ciao", color="verde")


def test_annotate_bad_page_rejected():
    with pytest.raises(ValueError, match="fuori range"):
        pdfedit.annotate_text(_make_pdf(1), 3, "Ciao")


# --------------------------------------------------------------------------
# Nota / penna / timbro / testo libero
# --------------------------------------------------------------------------
def test_note_content_and_icon():
    doc = _load(pdfedit.add_note(_make_pdf(1), 1, 50, 20, "da rivedere", icon="Comment"))
    page = doc[0]
    annot = next(page.annots())
    assert annot.type[1] == "Text"
    assert annot.info.get("content") == "da rivedere"


def test_note_empty_text_rejected():
    with pytest.raises(ValueError, match="vuoto"):
        pdfedit.add_note(_make_pdf(1), 1, 10, 10, " ")


def test_note_bad_icon_rejected():
    with pytest.raises(ValueError, match="Icona"):
        pdfedit.add_note(_make_pdf(1), 1, 10, 10, "x", icon="Skull")


def test_ink_creates_annot():
    strokes = [[[10, 10], [30, 30], [50, 10]], [[60, 10], [80, 40]]]
    out = pdfedit.add_ink(_make_pdf(1), 1, strokes, color="#000000", width=3)
    assert _annot_types(out) == ["Ink"]


@pytest.mark.parametrize("bad", [None, [], [[10, 10]], [[[10, 10]], "x"]])
def test_ink_invalid_strokes_rejected(bad):
    with pytest.raises(ValueError):
        pdfedit.add_ink(_make_pdf(1), 1, bad)


def test_stamp_text():
    out = pdfedit.add_stamp(_make_pdf(1), 1, "APPROVATO", 30, 40)
    assert "APPROVATO" in _load(out)[0].get_text()


def test_stamp_rotation_portrait_rect():
    out = pdfedit.add_stamp(_make_pdf(1), 1, "OK", 40, 30, w_pct=10, h_pct=50, rotate=90)
    assert "OK" in _load(out)[0].get_text()


def test_stamp_long_text_shrinks_without_error():
    out = pdfedit.add_stamp(_make_pdf(1), 1, "TESTO MOLTO LUNGO " * 6, 10, 10, h_pct=6)
    assert _load(out).page_count == 1


def test_stamp_bad_rotate_rejected():
    with pytest.raises(ValueError, match="Rotazione"):
        pdfedit.add_stamp(_make_pdf(1), 1, "X", 10, 10, rotate=45)


def test_stamp_empty_text_rejected():
    with pytest.raises(ValueError, match="vuoto"):
        pdfedit.add_stamp(_make_pdf(1), 1, "  ", 10, 10)


def test_add_text_visible_and_font():
    out = pdfedit.add_text(_make_pdf(1), 1, "Testo libero", 10, 50, font="tiro")
    assert "Testo libero" in _load(out)[0].get_text()


def test_add_text_empty_rejected():
    with pytest.raises(ValueError, match="vuoto"):
        pdfedit.add_text(_make_pdf(1), 1, "", 10, 50)


def test_add_text_bad_font_rejected():
    with pytest.raises(ValueError, match="Font"):
        pdfedit.add_text(_make_pdf(1), 1, "x", 10, 50, font="comic")


# --------------------------------------------------------------------------
# Redazione vera
# --------------------------------------------------------------------------
def test_redact_removes_text():
    out = pdfedit.redact(_make_pdf(1), needle="Ciao")
    assert "Ciao" not in _load(out)[0].get_text()


def test_redact_rects_on_page():
    out = pdfedit.redact(_make_pdf(1), rects=[[5, 40, 90, 15]], page=1)
    assert "Ciao" not in _load(out)[0].get_text()


def test_redact_not_found_rejected():
    with pytest.raises(ValueError, match="non trovato"):
        pdfedit.redact(_make_pdf(1), needle="assente")


def test_redact_no_input_rejected():
    with pytest.raises(ValueError, match="Specifica"):
        pdfedit.redact(_make_pdf(1))


def test_redact_rects_require_page():
    with pytest.raises(ValueError, match="pagina"):
        pdfedit.redact(_make_pdf(1), rects=[[10, 10, 10, 10]])


def test_redact_bad_rect_rejected():
    with pytest.raises(ValueError, match="Rettangolo"):
        pdfedit.redact(_make_pdf(1), rects=[[10, 10]], page=1)


def test_redact_fill_color_custom():
    out = pdfedit.redact(_make_pdf(1), needle="Ciao", fill="#ff0000")
    assert "Ciao" not in _load(out)[0].get_text()


# --------------------------------------------------------------------------
# Trova & sostituisci
# --------------------------------------------------------------------------
def test_find_replace_basic():
    out = pdfedit.find_replace(_make_pdf(2), "Ciao", "Salve")
    text = "".join(_load(out)[i].get_text() for i in range(2))
    assert "Salve" in text and "Ciao" not in text


def test_find_replace_deletion():
    out = pdfedit.find_replace(_make_pdf(1), "Ciao mondo", "")
    assert "Ciao" not in _load(out)[0].get_text()


def test_find_replace_pages_subset():
    out = pdfedit.find_replace(_make_pdf(2), "Ciao", "Salve", pages=[2])
    doc = _load(out)
    assert "Ciao" in doc[0].get_text()
    assert "Salve" in doc[1].get_text()


def test_find_replace_keeps_font_size():
    out = pdfedit.find_replace(_make_pdf(1), "mondo", "OK")
    spans = [s for b in _load(out)[0].get_text("dict")["blocks"]
             for ln in b["lines"] for s in ln["spans"] if "OK" in s["text"]]
    assert spans and spans[0]["size"] == pytest.approx(18.0, abs=0.5)


def test_find_replace_not_found_rejected():
    with pytest.raises(ValueError, match="non trovato"):
        pdfedit.find_replace(_make_pdf(1), "assente", "x")


def test_find_replace_empty_needle_rejected():
    with pytest.raises(ValueError, match="vuoto"):
        pdfedit.find_replace(_make_pdf(1), "  ", "x")


def test_find_replace_preserva_sfondo_regressione():
    """Regressione: la sostituzione non deve coprire lo sfondo con un box opaco."""
    out = pdfedit.find_replace(_make_colored_pdf(), "Eden", "Test")
    assert "Test" in _load(out)[0].get_text()
    # il pixel centrale dell'area sostituita deve restare il blu della fascia
    assert _pixel(out, 30, 52) == pytest.approx((31, 59, 94), abs=10)


def test_find_replace_deletion_preserva_sfondo():
    """Anche la cancellazione (replacement vuoto) deve lasciare intatto lo sfondo."""
    out = pdfedit.find_replace(_make_colored_pdf(), "Eden", "")
    assert "Eden" not in _load(out)[0].get_text()
    assert _pixel(out, 30, 52) == pytest.approx((31, 59, 94), abs=10)


def test_find_replace_fill_esplicito_copre():
    """Il parametro `fill` resta disponibile come copertura esplicita (opt-in)."""
    out = pdfedit.find_replace(_make_colored_pdf(), "Eden", "Test", fill="#000000")
    assert _pixel(out, 30, 52) == pytest.approx((0, 0, 0), abs=12)


def test_find_replace_testo_ruotato_resta_verticale():
    """Regressione: un testo verticale sostituito deve restare verticale e in sede."""
    out = pdfedit.find_replace(_make_rotated_pdf(), "EDEN", "TEST")
    lines = [ln for b in _load(out)[0].get_text("dict")["blocks"]
             for ln in b.get("lines", []) if any("TEST" in s["text"] for s in ln["spans"])]
    assert lines, "sostituzione non trovata"
    line = lines[0]
    assert abs(line["dir"][1]) > 0.9, f"direzione non verticale: {line['dir']}"
    x0, y0, x1, y1 = line["bbox"]
    assert (x1 - x0) < (y1 - y0), f"bbox non verticale: {line['bbox']}"


def test_find_replace_parola_dentro_span_lunga_non_sovrappone():
    """Regressione: match dentro una span lunga → il rimpiazzo va dove stava la
    parola, non all'inizio della span (voci d'indice sovrapposte)."""
    out = pdfedit.find_replace(_make_index_pdf(), "Eden", "Test")
    pg = _load(out)[0]
    assert not pg.search_for("Eden"), "testo originale ancora presente"
    test_r = pg.search_for("Test")[0]
    cosa_r = pg.search_for("Cosa")[0]
    assert test_r.x0 >= cosa_r.x1 - 1, f"rimpiazzo sovrapposto: Test {test_r} vs Cosa {cosa_r}"
    assert test_r.x0 > 90, f"rimpiazzo all'inizio della riga: x0={test_r.x0}"


# --------------------------------------------------------------------------
# Numerazione / intestazioni
# --------------------------------------------------------------------------
def test_number_default_bates():
    doc = _load(pdfedit.number_pages(_make_pdf(2)))
    assert "000001" in doc[0].get_text()
    assert "000002" in doc[1].get_text()


def test_number_prefix_suffix_digits_start():
    out = pdfedit.number_pages(_make_pdf(2), start=7, prefix="VR-", suffix="/A",
                               digits=3, position="tl")
    t0 = _load(out)[0].get_text()
    assert "VR-007/A" in t0


def test_number_pages_subset_consumes_counter_in_order():
    out = pdfedit.number_pages(_make_pdf(3), pages=[3, 1], digits=2)
    doc = _load(out)
    assert "01" in doc[2].get_text()
    assert "02" in doc[0].get_text()
    assert "01" not in doc[1].get_text() and "02" not in doc[1].get_text()


def test_number_bad_position_rejected():
    with pytest.raises(ValueError, match="Posizione"):
        pdfedit.number_pages(_make_pdf(1), position="sx")


def test_number_negative_start_rejected():
    with pytest.raises(ValueError, match="negativo"):
        pdfedit.number_pages(_make_pdf(1), start=-1)


def test_header_footer_placeholders():
    out = pdfedit.header_footer(_make_pdf(2), header="Riservato {page}/{pages}",
                                footer="Data {date}", date="2026-09-15")
    doc = _load(out)
    assert "Riservato 1/2" in doc[0].get_text()
    assert "Data 2026-09-15" in doc[1].get_text()


def test_header_footer_bad_position_rejected():
    with pytest.raises(ValueError, match="Posizione"):
        pdfedit.header_footer(_make_pdf(1), header="x", position="middle")


def test_header_footer_empty_rejected():
    with pytest.raises(ValueError, match="almeno"):
        pdfedit.header_footer(_make_pdf(1))


# --------------------------------------------------------------------------
# Pagine
# --------------------------------------------------------------------------
def test_insert_blank_page_middle():
    doc = _load(pdfedit.insert_blank_page(_make_pdf(2), at=2, count=2))
    assert doc.page_count == 4
    assert "PAGINA-1" in doc[0].get_text()
    assert doc[1].get_text().strip() == "" and doc[2].get_text().strip() == ""
    assert "PAGINA-2" in doc[3].get_text()


def test_insert_blank_page_at_end_allowed():
    doc = _load(pdfedit.insert_blank_page(_make_pdf(2), at=3))
    assert doc.page_count == 3


@pytest.mark.parametrize("at,count", [(0, 1), (9, 1), (1, 0), (1, 51)])
def test_insert_blank_page_range_rejected(at, count):
    with pytest.raises(ValueError, match="fuori range"):
        pdfedit.insert_blank_page(_make_pdf(2), at=at, count=count)


def test_extract_pages_order():
    doc = _load(pdfedit.extract_pages(_make_pdf(3), [3, 1]))
    assert doc.page_count == 2
    assert "PAGINA-3" in doc[0].get_text()
    assert "PAGINA-1" in doc[1].get_text()


def test_extract_empty_and_out_of_range_rejected():
    with pytest.raises(ValueError, match="Nessuna pagina"):
        pdfedit.extract_pages(_make_pdf(2), [])
    with pytest.raises(ValueError, match="fuori range"):
        pdfedit.extract_pages(_make_pdf(2), [5])


# --------------------------------------------------------------------------
# Moduli
# --------------------------------------------------------------------------
def test_form_fields_listing():
    fields = pdfedit.form_fields(_make_form_pdf())
    assert fields == [{"page": 1, "name": "nome", "type": "text", "value": ""}]


def test_fill_form_sets_value():
    out = pdfedit.fill_form(_make_form_pdf(), {"nome": "Mario"})
    assert [w.field_value for w in _load(out)[0].widgets()] == ["Mario"]


def test_fill_form_unknown_field_rejected():
    with pytest.raises(ValueError, match="non trovati"):
        pdfedit.fill_form(_make_form_pdf(), {"nome": "Mario", "cognome": "Rossi"})


def test_fill_form_no_widgets_rejected():
    with pytest.raises(ValueError, match="non contiene campi"):
        pdfedit.fill_form(_make_pdf(1), {"nome": "Mario"})


def test_fill_form_empty_dict_rejected():
    with pytest.raises(ValueError, match="Nessun campo"):
        pdfedit.fill_form(_make_form_pdf(), {})


# --------------------------------------------------------------------------
# API: contratto HTTP
# --------------------------------------------------------------------------
def test_api_annotate(client):
    res = _post_edit(client, _make_pdf(1), action="annotate", page_num=1,
                     needle="Ciao", anno_kind="highlight")
    assert res.status_code == 200
    body = res.json()
    assert body["action"] == "annotate"
    out = client.get(body["results"][0]["download"]).content
    assert _annot_types(out) == ["Highlight"]


def test_api_replace_roundtrip(client):
    res = _post_edit(client, _make_pdf(2), action="replace",
                     needle="Ciao", replacement="Salve")
    assert res.status_code == 200
    out = client.get(res.json()["results"][0]["download"]).content
    assert "Salve" in _load(out)[0].get_text()


def test_api_insertpage_roundtrip(client):
    res = _post_edit(client, _make_pdf(2), action="insertpage", insert_at=1, insert_count=1)
    assert res.status_code == 200
    out = client.get(res.json()["results"][0]["download"]).content
    assert _load(out).page_count == 3


def test_api_extract_roundtrip(client):
    res = _post_edit(client, _make_pdf(3), action="extract", pages="[2]")
    assert res.status_code == 200
    out = client.get(res.json()["results"][0]["download"]).content
    doc = _load(out)
    assert doc.page_count == 1 and "PAGINA-2" in doc[0].get_text()


def test_api_ink_roundtrip(client):
    res = _post_edit(client, _make_pdf(1), action="ink",
                     ink_strokes="[[[10,10],[40,40]]]")
    assert res.status_code == 200
    out = client.get(res.json()["results"][0]["download"]).content
    assert _annot_types(out) == ["Ink"]


def test_api_redact_bad_json_400(client):
    res = _post_edit(client, _make_pdf(1), action="redact",
                     redact_rects="{non-json", page_num=1)
    assert res.status_code == 400


def test_api_form_fill_roundtrip(client):
    res = _post_edit(client, _make_form_pdf(), action="form",
                     form_values='{"nome": "Mario"}')
    assert res.status_code == 200
    out = client.get(res.json()["results"][0]["download"]).content
    assert [w.field_value for w in _load(out)[0].widgets()] == ["Mario"]


def test_api_form_on_plain_pdf_400(client):
    res = _post_edit(client, _make_pdf(1), action="form", form_values='{"nome": "x"}')
    assert res.status_code == 400
    assert "modulo" in res.json()["detail"]


def test_api_form_fields_endpoint(client):
    res = client.post("/api/pdf-form-fields",
                      files=[("file", ("f.pdf", _make_form_pdf(), "application/pdf"))])
    assert res.status_code == 200
    assert res.json()["fields"][0]["name"] == "nome"


def test_api_form_fields_non_pdf_400(client):
    res = client.post("/api/pdf-form-fields",
                      files=[("file", ("f.txt", b"x", "text/plain"))])
    assert res.status_code == 400


def test_api_unknown_action_400(client):
    res = _post_edit(client, _make_pdf(1), action="explode")
    assert res.status_code == 400


def test_api_replace_missing_text_400(client):
    res = _post_edit(client, _make_pdf(1), action="replace",
                     needle="assente", replacement="x")
    assert res.status_code == 400
    assert "non trovato" in res.json()["detail"]
