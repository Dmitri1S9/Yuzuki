"""Builds and parses the character-portrait URL. Lives in shared/, not
api/media.py, because both src/api (serves the route) and
src/services/collection/cast (drafts this URL into the roster DCS reviews,
before anything is confirmed) need it, and services never imports from api.
"""
import os
import re
from urllib.parse import quote, unquote

YUZUKI_PUBLIC_URL = os.environ.get("YUZUKI_PUBLIC_URL", "http://localhost:8044")

_PORTRAIT_PATH = re.compile(r"/characters/(\d+)/([^/]+)/portrait$")


def portrait_url_for(universe_id: int, name: str) -> str:
    return f"{YUZUKI_PUBLIC_URL}/characters/{universe_id}/{quote(name, safe='')}/portrait"


def parse_portrait_url(url: str | None) -> tuple[int, str] | None:
    """Reverse of portrait_url_for. Used at DCS-confirm time to recover which
    (universe_id, name) row a DCS-echoed image_url actually points at, when
    the confirmed name differs — a DCS-side rename edits the roster row's
    name in place without touching its cached image_url, so on confirm the
    URL can point at an old name sync_roster is about to delete (see
    api/routes/confirm.py)."""
    if not url:
        return None
    m = _PORTRAIT_PATH.search(url)
    if not m:
        return None
    return int(m.group(1)), unquote(m.group(2))
