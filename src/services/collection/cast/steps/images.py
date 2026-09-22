"""Stage 1 character images — for each roster name, a portrait and an
existence signal, sourced from two services with very different
reliability:

1. AniList (anime_db.py) — PRIMARY. One request per universe returns the
   whole official cast list with artwork for that exact title. Identity
   is guaranteed by the source (it's that title's own curated character
   list), which is what actually fixes "wrong character" / "wrong show"
   (see below) — not a guess from search-result relevance.
2. ddgs (free web search, no API key) — FALLBACK, only for names AniList's
   list doesn't cover (deep-cut/minor characters, or a title AniList
   doesn't have). Everything below about ddgs's own unreliability is about
   this fallback path, not the primary one.

ddgs findings, all confirmed live and still relevant to the fallback path:
- DuckDuckGo does not strictly AND two quoted phrases — a query for a
  fabricated name still returns generic results about the universe alone
  (a made-up name got the same raw hit count as the real female lead).
  existence_hits therefore counts only the results whose own title/body
  actually contain the character's name, not the raw result count.
- ddgs races several backend engines and raises the same generic "no
  results" exception whether a query genuinely has none or every engine
  in that batch just got rate-limited/blocked — an identical query for a
  very well-known character flip-flopped between 7 real hits and "no
  results" seconds apart. Retried (exponential backoff) before trusting a
  failure as a real zero. That flakiness gets much worse across a whole
  roster run back-to-back (firing ~12 ddgs calls with no pacing gets most
  of a batch rate-limited at once), so existence_hits distinguishes
  "checked, found nothing" (0) from "couldn't check" (None) — a network
  failure is not evidence a character is fabricated.
- An unquoted image-search query can surface a face-detected image of the
  *wrong* character from the *right* show (the face-crop check only
  verifies "one anime face," never identity) — quoted name + quoted title
  narrows this but can't eliminate it, which is exactly why AniList is
  primary now and this is the fallback.
- ddgs has no published rate limit (it's an unofficial scraper, not a
  real API) — sustained back-to-back requests get rate-limited within
  seconds; ~2s spacing plus retries recovers most of the time, not all.

A ddgs candidate is never stored as-is: it must crop to exactly one
detected face (face.py's crop_to_face) or it's discarded and the next
candidate is tried. An AniList image skips that rejection (center-cropped
if a face isn't found — the source already guarantees identity, so a
missed face detection isn't a reason to throw away a known-correct
image). Either way the accepted image is re-hosted locally (see
src/api/main.py's /media mount), not linked from the original URL, since
what's stored is a derived (cropped) image.
"""
import functools
import hashlib
import logging
import os
import time
from pathlib import Path

import httpx
from ddgs import DDGS

from src.repository import CharacterRepository
from src.services.collection.cast.steps import anime_db
from src.services.collection.cast.steps.constants import ANILIST_TITLE, UNIVERSE_NAME
from src.services.collection.cast.steps.face import center_crop_square, crop_to_face
from src.shared.decorators import announce, report

log = logging.getLogger(__name__)

_character_repo = CharacterRepository()

_MAX_ATTEMPTS = 4
_RETRY_BASE_DELAY_SECONDS = 2.0
_MAX_IMAGE_CANDIDATES = 6
_PER_CHARACTER_DELAY_SECONDS = 2.0

MEDIA_DIR = Path("media/characters")
YUZUKI_PUBLIC_URL = os.environ.get("YUZUKI_PUBLIC_URL", "http://localhost:8044")


def _search_with_retry(fn, *args, **kwargs) -> list[dict] | None:
    """None = every attempt failed (rate-limited/blocked) — distinct from a
    successful call that returned zero results."""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return fn(*args, **kwargs)
        except Exception:
            if attempt == _MAX_ATTEMPTS:
                return None
            time.sleep(_RETRY_BASE_DELAY_SECONDS * attempt)  # 2s, 4s, 6s
    return None


_DOWNLOAD_HEADERS = {
    # Several image hosts 403 a request with no User-Agent at all (confirmed
    # live: half of a real candidate list failed to download without this).
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def _download(url: str) -> bytes | None:
    try:
        response = httpx.get(url, timeout=15.0, follow_redirects=True, headers=_DOWNLOAD_HEADERS)
        response.raise_for_status()
        return response.content
    except Exception:
        return None


def _save_portrait(universe_name: str, name: str, cropped: bytes) -> str:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    slug = hashlib.sha1(f"{universe_name}|{name}".encode()).hexdigest()[:16]
    (MEDIA_DIR / f"{slug}.jpg").write_bytes(cropped)
    # ?v= busts both the browser's HTTP cache and React's "src didn't
    # change, don't refetch" — the filename is stable (hashed from
    # universe+name) so a re-fetched image would otherwise silently keep
    # showing the old cached file after a manual refresh.
    return f"{YUZUKI_PUBLIC_URL}/media/characters/{slug}.jpg?v={int(time.time())}"


def _portrait_from_anilist(name: str, universe_name: str, anilist_images: dict[str, str]) -> str | None:
    url = anime_db.lookup(name, anilist_images)
    if url is None:
        return None
    image_bytes = _download(url)
    if image_bytes is None:
        return None
    cropped = crop_to_face(image_bytes) or center_crop_square(image_bytes)
    if cropped is None:
        return None
    return _save_portrait(universe_name, name, cropped)


def _portrait_from_ddgs(ddgs: DDGS, name: str, universe_name: str) -> str | None:
    # Quoted name + quoted title (not a loose unquoted query) — see module
    # docstring. Trades coverage for correctness on purpose: a character
    # this narrows to zero candidates for gets no image rather than a
    # wrong one, and can be filled in by hand in the Library tab instead.
    images = _search_with_retry(
        ddgs.images, f'"{name}" "{universe_name}" character', max_results=_MAX_IMAGE_CANDIDATES)
    for img in images or []:
        url = img.get("image")
        if not url:
            continue
        image_bytes = _download(url)
        if image_bytes is None:
            continue
        cropped = crop_to_face(image_bytes)
        if cropped is None:
            continue
        return _save_portrait(universe_name, name, cropped)

    log.info("no single-face ddgs candidate found for %r (of %d searched)", name, _MAX_IMAGE_CANDIDATES)
    return None


def find_portrait(name: str, universe_name: str, ddgs: DDGS, anilist_images: dict[str, str]) -> str | None:
    return (_portrait_from_anilist(name, universe_name, anilist_images)
            or _portrait_from_ddgs(ddgs, name, universe_name))


def lookup_character_image(
    ddgs: DDGS, name: str, universe_name: str, anilist_images: dict[str, str] | None = None,
) -> tuple[str | None, int | None]:
    if anilist_images is None:
        anilist_images = anime_db.fetch_character_images(universe_name)

    query = f'"{name}" "{universe_name}"'
    results = _search_with_retry(ddgs.text, query, max_results=8)
    if results is None:
        existence_hits = None  # every attempt was rate-limited/blocked — no signal, not "fake"
    else:
        name_lower = name.lower()
        existence_hits = sum(
            1 for r in results if name_lower in (r.get("title", "") + " " + r.get("body", "")).lower()
        )

    image_url = find_portrait(name, universe_name, ddgs, anilist_images)

    return image_url, existence_hits


@announce("fetching character images + existence signal (AniList primary, ddgs fallback)")
@report(lambda r: f"images_found={sum(1 for e in r if e['image_url'])}/{len(r)}")
def collect_character_images(roster: list[dict]) -> list[dict]:
    # AniList images come from ANILIST_TITLE (the specific season/movie,
    # when it differs from the universe's own display name — see
    # constants.py); ddgs queries below still use UNIVERSE_NAME, the
    # show's recognizable name, since that's a general web search, not an
    # AniList title match.
    anilist_images = anime_db.fetch_character_images(ANILIST_TITLE)
    with DDGS() as ddgs:
        for i, entry in enumerate(roster):
            if i > 0:
                time.sleep(_PER_CHARACTER_DELAY_SECONDS)
            image_url, existence_hits = lookup_character_image(
                ddgs, entry["name"], UNIVERSE_NAME, anilist_images)
            entry["image_url"] = image_url
            entry["existence_hits"] = existence_hits
    return roster


@announce("saving character images + existence signal to database")
def persist_character_images(universe_id: int, roster: list[dict]) -> None:
    for entry in roster:
        _character_repo.save_character_image(
            universe_id, entry["name"], entry.get("image_url"), entry.get("existence_hits"),
        )
