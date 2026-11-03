from src.shared.naming import parse_universe_args

UNIVERSE_NAME, ARC, LOCATION, SLUG, ANILIST_TITLE = parse_universe_args("Classroom of the Elite", "Year 1")
# The exact AniList media title to search for, when an arc doesn't map
# onto the same title as the universe's own display name (e.g. a later
# season/movie with an unrelated-looking title) — see naming.py. Empty
# means "search with UNIVERSE_NAME itself," the common case.
ANILIST_TITLE = ANILIST_TITLE or UNIVERSE_NAME

CAST_PASSES = {"medium": 1, "large": 1, "isolates": 1}
GROUP_TYPES = ("medium", "large")
# Cut back to 1 pass, and the 3 group types combined into a single call
# (see groups.py's collect_raw_groups/client.group_all) — 2026-09-23,
# explicit cost cut ("надо что-то резать"): this was 3 types x 2 passes =
# 6 calls, now 1. Was previously restored to 2 passes on 2026-09-21
# specifically because 1 pass had no second pass to corroborate against,
# so a one-off hallucinated group or character survived unfiltered
# (confirmed live). That risk is back, accepted knowingly this time — a
# human still reviews every roster/group in DCS before anything is
# persisted, so a fabrication is caught there, not silently written to
# the database.
SURVIVE_PASSES = {"medium": 1, "large": 1}
DEDUP_OVERLAP = {"medium": 0.70, "large": 0.50}
ROSTER_MIN_PASSES = 1

SPECIAL_CHAR_MAP = {
    "ō": "o", "Ō": "O", "ū": "u", "Ū": "U", "ā": "a", "Ā": "A",
    "ē": "e", "Ē": "E", "ī": "i", "Ī": "I",
}
ROMANIZATION_MAP = [("ou", "o"), ("uu", "u"), ("oo", "o")]
