"""it.json ed en.json devono avere le stesse chiavi e gli stessi segnaposto {x}."""
import json
import re
from pathlib import Path

I18N = Path(__file__).resolve().parent.parent / "static" / "i18n"


def _load(lang: str) -> dict:
    return json.loads((I18N / f"{lang}.json").read_text(encoding="utf-8"))


def _placeholders(s: str) -> list[str]:
    return sorted(re.findall(r"\{(\w+)\}", s))


def test_same_keys_it_en():
    assert set(_load("it")) == set(_load("en"))


def test_same_placeholders_it_en():
    it, en = _load("it"), _load("en")
    diff = {k: (_placeholders(it[k]), _placeholders(en[k])) for k in it if _placeholders(it[k]) != _placeholders(en[k])}
    assert diff == {}
