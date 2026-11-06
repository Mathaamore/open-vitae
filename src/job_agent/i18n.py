"""Product copy with an English fallback; candidate and job source text is never translated."""
from functools import lru_cache
import json
from pathlib import Path
import re

ROOT=Path(__file__).with_name('locales')


@lru_cache(maxsize=8)
def catalog(locale='en'):
    english=json.loads((ROOT/'en.json').read_text())
    if locale=='en' or not re.fullmatch(r'[a-z]{2}(?:-[A-Z]{2})?',locale):
        return english
    path=ROOT/(locale+'.json')
    return {**english,**(json.loads(path.read_text()) if path.is_file() else {})}


def tr(key, *, locale='en', **values):
    return catalog(locale)[key].format_map(values)


@lru_cache(maxsize=1)
def legacy_messages():
    return json.loads((ROOT/'legacy-fr.json').read_text())


def system_text(value):
    """Only call for app-owned status, validation and preparation messages."""
    if not isinstance(value,str):return value
    legacy=legacy_messages()
    if value in legacy:return tr(legacy[value])
    for prefix,key in legacy.items():
        if prefix.endswith(': ') and value.startswith(prefix):return tr(key)+value[len(prefix):]
    return value
