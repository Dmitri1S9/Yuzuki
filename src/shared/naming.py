import re
import sys


def slugify(universe: str, arc: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", f"{universe}_{arc}".lower()).strip("_")


def display_name(name: str, alias_map: dict[str, list[str]]) -> str:
    """`name` with any known aliases appended in parentheses — a recognition
    aid for prompts that only ever send a bare name list otherwise (e.g. a
    hero known in-story mostly by a codename, when the roster only has
    their civilian name, or vice versa). 2026-09-23, user's call: the model
    sometimes doesn't connect a bare name to who it actually is, especially
    a well-known alias/codename it would recognize instantly.

    The caller's prompt must still parse the model's OUTPUT against the
    bare `name` (see collection.py's rank()/flag() calls, which pass this
    for `characters=` but keep the plain roster for scores_from_result) —
    the system prompts instruct the model to answer with the bare name
    only, never echoing the parenthetical back. Names with no known alias
    pass through unchanged."""
    aliases = alias_map.get(name)
    if not aliases:
        return name
    return f"{name} (aka {', '.join(aliases)})"


def normalize_for_match(s: str) -> str:
    return " ".join(s.split()).lower()


def resolve_alias(item: str, roster: list[str], alias_map: dict[str, list[str]]) -> str:
    """Resolves `item` (a name string that came back FROM the model) to its
    canonical roster spelling, if `item` is that name's exact spelling, a
    known alias of it, or either with different casing/whitespace — passes
    `item` through unchanged if it matches nothing known. Companion to
    display_name(): the system prompts tell the model to always answer
    with the bare canonical name, never the "(aka ...)" alias it was given
    for recognition — confirmed live it doesn't always listen, and the
    fix is the same wherever a response gets matched back against the
    roster: the exact string the model picked doesn't matter, only that
    it resolves to one known character. Builds the variant->name lookup
    fresh each call — fine at this scale (dozens of names), not a hot loop."""
    variant_to_name = {
        normalize_for_match(variant): name
        for name in roster
        for variant in [name, *alias_map.get(name, [])]
    }
    return variant_to_name.get(normalize_for_match(item), item)


def parse_universe_args(default_name: str, default_arc: str, default_location: str = "",
                         default_anilist_title: str = ""):
    # anilist_title: a 4th, optional CLI arg — the exact AniList media
    # title to search for, when it differs from the universe's own display
    # name. A franchise's arc names don't appear in AniList's own title
    # metadata (confirmed live: "University Arc" matches nothing; the
    # actual season is titled "...Santa Claus...", unrelated-looking on
    # its own) — there's no way to auto-resolve which season/movie an arc
    # corresponds to, so this is a human call, not something to guess at.
    # Defaults to empty, meaning "search with the universe name itself."
    args = sys.argv[1:]
    name = args[0] if len(args) > 0 else default_name
    arc = args[1] if len(args) > 1 else default_arc
    location = args[2] if len(args) > 2 else default_location
    anilist_title = args[3] if len(args) > 3 else default_anilist_title
    return name, arc, location, slugify(name, arc), anilist_title
