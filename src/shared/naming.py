import re
import sys


def slugify(universe: str, arc: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", f"{universe}_{arc}".lower()).strip("_")


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
