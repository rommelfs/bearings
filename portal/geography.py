"""Offline Luxembourg postal/place centroids; never infer an exact building or IP location."""

import hashlib
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


def address_digest(address):
    return hashlib.sha256(address.strip().encode()).hexdigest()


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def gazetteer():
    rows = json.loads((Path(__file__).parent / "data/lu-postal.json").read_text())
    codes, places = {}, {}
    for row in rows:
        codes.setdefault(row[0], []).append(row)
        places.setdefault(normalize(row[1]), []).append(row)
    return codes, places


def local_location(address):
    text = normalize(address)
    # Explicit foreign country statements prevent an accidental Luxembourg match.
    if re.search(
        r"\b(france|belgium|belgique|belgien|germany|deutschland|netherlands|nederland|united kingdom|united states)\b",
        text,
    ):
        return None
    if not re.search(r"\b(luxembourg|luxemburg|letzebuerg)\b|\bl\s*-\s*\d{4}\b|(?m:^\s*lu\s*$)", text):
        return None
    codes, places = gazetteer()
    explicit = set(re.findall(r"\bl\s*-\s*(\d{4})(?!\d)", text))
    if len(explicit) > 1:
        return None
    selected = codes.get(next(iter(explicit)), []) if explicit else []
    if not explicit:
        # Unprefixed codes require a matching place on the same line, so a house
        # number or year never silently becomes a postal code.
        matches = []
        for m in re.finditer(r"(?<!\d)(\d{4})\s+([^,\n]+)", text):
            matches.extend(r for r in codes.get(m[1], []) if normalize(r[1]) == m[2].strip(" ,"))
        if len({r[0] for r in matches}) > 1:
            return None
        selected = matches
    if selected:
        named = [r for r in selected if re.search(r"(?<!\w)" + re.escape(normalize(r[1])) + r"(?!\w)", text)]
        selected = named or selected
        return {
            "lat": sum(r[2] for r in selected) / len(selected),
            "lon": sum(r[3] for r in selected) / len(selected),
            "method": "postal",
            "label": "Approximate postal area · L-" + selected[0][0],
        }
    if explicit:
        return None
    # Whole locality lines only, excluding the ambiguous city/country name.
    names = {line.strip(" ,") for line in text.splitlines()} - {"luxembourg", "luxemburg", "letzebuerg"}
    found = [name for name in names if name in places]
    if len(found) != 1:
        return None
    selected = places[found[0]]
    if (
        max(r[2] for r in selected) - min(r[2] for r in selected) > 0.05
        or max(r[3] for r in selected) - min(r[3] for r in selected) > 0.05
    ):
        return None
    return {
        "lat": sum(r[2] for r in selected) / len(selected),
        "lon": sum(r[3] for r in selected) / len(selected),
        "method": "place",
        "label": "Approximate locality · " + selected[0][1],
    }
