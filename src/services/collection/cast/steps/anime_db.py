"""AniList (anilist.co) — the authoritative source for one title's actual
character list, used two ways in stage 1:

1. Images (images.py) — fetch_character_images(): identity comes from the
   source being tied to the title, not from guessing whether a search
   result looks right, which is what actually fixes "wrong character" /
   "wrong show" (see images.py's docstring for the real cases a blind
   image search got wrong).
2. Roster backstop (roster.py's merge_anilist_names, called from main.py)
   — fetch_cast_names(): the LLM's own blind group-collection passes can
   consistently miss even a main character (confirmed live and repeatedly
   across several runs of this exact title: the female lead never
   surfaced once from blind collection). AniList's own cast list for the
   title is ground truth for "does this character exist in this show,"
   independent of whatever the model's passes happened to mention — names
   it has that the model missed still make the roster, marked as
   database-confirmed rather than low_confidence.
3. Group-collection prompts (base_client.py's group()) — that same cast
   list, passed as a reference the model checks its own recall against
   and prefers exact spelling from. Only ever names, never the bios
   below — explicitly display-only, per the user's own instruction, to
   keep the per-flag-call cost multiplier out of this entirely.

fetch_character_descriptions() is separate from all three: display-only
text for DCS's Library tab (a character's bio/role blurb), never sent to
the model in any prompt — deliberately, since the same short text
repeated across the ~102 flag-collection calls (51 flags x 2 passes)
would cost roughly 17x what it costs the ~6 group-collection calls, for
a stage where the answer only needs a name, not a biography.

One GraphQL request per universe per use (not per character) — the whole
cast list comes back in one call. AniList's rate limit (from a live
response header: x-ratelimit-limit: 30/min) is generous at that request
rate; retried with backoff regardless, since a transient failure here
should fall back to whatever the caller's own fallback is (ddgs for
images, "no backstop" for the roster), not silently give up on the whole
universe.
"""
import re
import time

import httpx

from src.shared.decorators import logged

_ANILIST_URL = "https://graphql.anilist.co"
_QUERY = """
query ($search: String, $page: Int) {
  Media(search: $search, type: ANIME) {
    id
    characters(sort: ROLE, perPage: 25, page: $page) {
      pageInfo { hasNextPage }
      nodes {
        name { full native alternative }
        image { large }
        description(asHtml: false)
      }
    }
  }
}
"""
_SPOILER_MARKUP = re.compile(r"~!|!~")
_BOLD_MARKUP = re.compile(r"__(.*?)__")

_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 3.0
# AniList caps this connection at 25/page regardless of what's requested
# (confirmed live) — a small cast (most titles) fits on page 1, but a huge
# franchise like My Hero Academia lists 500+ characters there, sorted by
# ROLE (main -> supporting -> background), so stopping at page 1 silently
# dropped everyone past the first 25 main/supporting names. 8 pages (200
# characters) comfortably covers every named character that could plausibly
# matter to any one arc, without pulling in hundreds of background extras.
_MAX_PAGES = 8


@logged(lambda _, universe_name, page:
        f"AniList lookup failed for {universe_name!r} (page {page}) after {_MAX_ATTEMPTS} attempts")
def _log_fetch_failed(universe_name: str, page: int) -> None:
    pass


@logged(lambda _, universe_name: f"AniList has no title matching {universe_name!r}")
def _log_no_title_match(universe_name: str) -> None:
    pass


def _fetch_character_nodes(universe_name: str) -> list[dict]:
    """Raw AniList character nodes for this title (up to _MAX_PAGES worth,
    sorted main -> supporting -> background), or [] if the title isn't
    found or the request fails after retries."""
    nodes: list[dict] = []
    for page in range(1, _MAX_PAGES + 1):
        data = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = httpx.post(
                    _ANILIST_URL,
                    json={"query": _QUERY, "variables": {"search": universe_name, "page": page}},
                    timeout=15.0,
                )
                response.raise_for_status()
                data = response.json()
                break
            except Exception:
                if attempt == _MAX_ATTEMPTS:
                    _log_fetch_failed(universe_name, page)
                    return nodes
                time.sleep(_RETRY_DELAY_SECONDS * attempt)

        media = (data.get("data") or {}).get("Media")
        if not media:
            if page == 1:
                _log_no_title_match(universe_name)
            return nodes
        characters = media["characters"]
        nodes.extend(characters["nodes"])
        if not characters["pageInfo"]["hasNextPage"]:
            break
    return nodes


@logged(lambda out, universe_name: f"AniList: {universe_name!r} -> {len(out)} character image(s)")
def fetch_character_images(universe_name: str) -> dict[str, str]:
    """{lowercased character name: portrait URL} for every character
    AniList's cast list for this title has an image for — every known
    name/alternative spelling maps to the same image, so a lookup doesn't
    need its own fuzzy matching."""
    out: dict[str, str] = {}
    for node in _fetch_character_nodes(universe_name):
        image_url = (node.get("image") or {}).get("large")
        if not image_url:
            continue
        name_field = node.get("name") or {}
        names = [name_field.get("full"), name_field.get("native")] + (name_field.get("alternative") or [])
        for n in names:
            if n:
                out[n.strip().lower()] = image_url
    return out


@logged(lambda names, universe_name: f"AniList: {universe_name!r} -> {len(names)} cast name(s)")
def fetch_cast_names(universe_name: str) -> list[str]:
    """Every character's canonical display name (name.full) from AniList's
    cast list for this title — no images, just the roster backstop list.
    A character with no full name (rare, a data gap on AniList's side) is
    skipped, not guessed at."""
    names = [node["name"]["full"] for node in _fetch_character_nodes(universe_name)
             if (node.get("name") or {}).get("full")]
    return names


@logged(lambda out, universe_name: f"AniList: {universe_name!r} -> {len(out)} character(s) with alias data")
def fetch_cast_aliases(universe_name: str) -> dict[str, list[str]]:
    """{character full name: [native/alternative names]} from AniList's own
    cast list — free replacement for the old dedicated alias_names() Gemini
    call: AniList already returns a character's codename/nickname/native
    spelling in the same nodes fetch_cast_names() reads, under `native` and
    `alternative`, just discarded there. Keyed by the character's own full
    name (unresolved against canon here — roster.py's merge_anilist_aliases
    does that, the same way merge_anilist_names() resolves fetch_cast_names()
    output)."""
    out: dict[str, list[str]] = {}
    for node in _fetch_character_nodes(universe_name):
        name_field = node.get("name") or {}
        full = name_field.get("full")
        if not full:
            continue
        alts = [a for a in ([name_field.get("native")] + (name_field.get("alternative") or [])) if a and a != full]
        if alts:
            out[full] = alts
    return out


def fetch_character_descriptions(universe_name: str) -> dict[str, str]:
    """{lowercased character name: bio text} — display-only, for DCS's
    Library tab (a character's role/personality blurb from AniList's own
    write-up). Never passed into any model prompt — see the module
    docstring for why. AniList's markdown-ish spoiler (~!...!~) and bold
    (__...__) markers are stripped for plain display; spoiler *content*
    is kept, not redacted — this is a personal admin tool, not a
    public-facing reader."""
    out: dict[str, str] = {}
    for node in _fetch_character_nodes(universe_name):
        raw = node.get("description")
        if not raw:
            continue
        text = _BOLD_MARKUP.sub(r"\1", _SPOILER_MARKUP.sub("", raw)).strip()
        name_field = node.get("name") or {}
        names = [name_field.get("full"), name_field.get("native")] + (name_field.get("alternative") or [])
        for n in names:
            if n:
                out[n.strip().lower()] = text
    return out


def lookup(name: str, by_lowercased_name: dict[str, str]) -> str | None:
    """Generic accessor for either dict this module returns (images or
    descriptions) — both are keyed the same way."""
    return by_lowercased_name.get(name.strip().lower())
