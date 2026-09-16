"""Tutte le lingue di SUPPORTED devono avere le stesse chiavi e gli stessi {placeholder} di it.json."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "static" / "i18n"


def _supported() -> list[str]:
    """Lingue elencate in static/i18n.js (fonte di verità per il runtime)."""
    js = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
    m = re.search(r"SUPPORTED\s*=\s*\[([^\]]+)\]", js)
    assert m, "SUPPORTED non trovato in i18n.js"
    return re.findall(r'"([a-z]{2})"', m.group(1))


def _load(lang: str) -> dict:
    return json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))


def _placeholders(s: str) -> list[str]:
    return sorted(re.findall(r"\{(\w+)\}", s))


def test_all_supported_files_exist():
    langs = _supported()
    assert "it" in langs
    missing = [lang for lang in langs if not (I18N / f"{lang}.json").is_file()]
    assert missing == []


def test_no_duplicate_keys():
    """Una chiave ripetuta è valida per json.load (vince l'ultima) ma è un errore di merge."""
    dupes = {}
    for lang in _supported():
        raw = (I18N / f"{lang}.json").read_text(encoding="utf-8")
        seen, dup = set(), []
        for k in re.findall(r'^\s*"([^"]+)"\s*:', raw, re.M):
            if k in seen:
                dup.append(k)
            seen.add(k)
        if dup:
            dupes[lang] = sorted(set(dup))
    assert dupes == {}


def test_same_keys_it_en():
    assert set(_load("it")) == set(_load("en"))


def test_same_placeholders_it_en():
    it, en = _load("it"), _load("en")
    diff = {k: (_placeholders(it[k]), _placeholders(en[k])) for k in it if _placeholders(it[k]) != _placeholders(en[k])}
    assert diff == {}


def test_same_keys_all_languages():
    it = _load("it")
    diffs = {lang: sorted(set(it) ^ set(_load(lang))) for lang in _supported() if set(it) != set(_load(lang))}
    assert diffs == {}


def test_same_placeholders_all_languages():
    it = _load("it")
    diffs = {}
    for lang in _supported():
        other = _load(lang)
        bad = {k: (_placeholders(it[k]), _placeholders(other.get(k, ""))) for k in it if _placeholders(it[k]) != _placeholders(other.get(k, ""))}
        if bad:
            diffs[lang] = bad
    assert diffs == {}


# v0.3.1: Tesseract e ffmpeg sono inclusi nel pacchetto (bundle/installer/MSIX):
# i messaggi non devono più rimandare a installazioni separate.
_MOTORI_KEYS = (
    "api.ocr_not_installed",
    "api.ffmpeg_missing",
    "dyn.ocr_off",
    "dyn.ffmpeg_missing",
    "api.scan_engine_missing",
    "api.ocr_warning",
)
_REINSTALL_KEYS = tuple(k for k in _MOTORI_KEYS if k != "api.ffmpeg_missing")


def test_messaggi_motori_senza_invito_all_installazione():
    bad = ("winget", "choco install", "apt install", "brew install", "pip install")
    for lang in _supported():
        d = _load(lang)
        for k in _MOTORI_KEYS:
            low = d[k].lower()
            assert not any(b in low for b in bad), (lang, k, d[k])


def test_messaggi_motori_indicano_reinstallazione_it_en():
    for lang in ("it", "en"):
        d = _load(lang)
        for k in _REINSTALL_KEYS:
            low = d[k].lower()
            assert ("reinstalla" in low or "reinstall" in low), (lang, k, d[k])
