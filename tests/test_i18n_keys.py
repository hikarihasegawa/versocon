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
