"""Operator-only raster configuration; no company input or external geocoder."""

import re
from urllib.parse import urlsplit
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def map_options():
    value = settings.MAP_TILE_URL.strip()
    if not value:
        return {"map_tile_url": "", "map_tile_origin": ""}
    try:
        url = urlsplit(value)
        _ = url.port
    except ValueError:
        raise ImproperlyConfigured("BEARINGS_MAP_TILE_URL has an invalid HTTPS authority") from None
    if (
        len(value) > 2048
        or not re.fullmatch(r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]{1,5})?", url.netloc)
        or url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 or char in "'\";<>\\" for char in value)
        or any(value.count("{" + field + "}") != 1 for field in ("z", "x", "y"))
        or "{" in value.replace("{z}", "").replace("{x}", "").replace("{y}", "")
        or "}" in value.replace("{z}", "").replace("{x}", "").replace("{y}", "")
    ):
        raise ImproperlyConfigured(
            "BEARINGS_MAP_TILE_URL must be an HTTPS XYZ template without credentials, queries or extra placeholders"
        )
    return {"map_tile_url": value, "map_tile_origin": f"https://{url.netloc}"}
