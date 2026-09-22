from src.shared.naming import parse_universe_args

UNIVERSE_NAME, ARC, LOCATION, SLUG, ANILIST_TITLE = parse_universe_args("Classroom of the Elite", "Year 1")
# The exact AniList media title to search for, when an arc doesn't map
# onto the same title as the universe's own display name (e.g. a later
# season/movie with an unrelated-looking title) — see naming.py. Empty
# means "search with UNIVERSE_NAME itself," the common case.
ANILIST_TITLE = ANILIST_TITLE or UNIVERSE_NAME

CAST_PASSES = {"medium": 2, "large": 2, "isolates": 2}
GROUP_TYPES = ("medium", "large")
# Restored from 1 pass (2026-09-21, user's call) — 1 pass had no second
# pass to corroborate against, so a one-off hallucinated group or character
# survived unfiltered every time (confirmed live: fabricated characters
# reaching the roster). 2 passes brings back real corroboration — both
# thresholds now require the name/group to show up in BOTH passes, not just
# once.
SURVIVE_PASSES = {"medium": 2, "large": 2}
DEDUP_OVERLAP = {"medium": 0.70, "large": 0.50}
ROSTER_MIN_PASSES = 2

SPECIAL_CHAR_MAP = {
    "ō": "o", "Ō": "O", "ū": "u", "Ū": "U", "ā": "a", "Ā": "A",
    "ē": "e", "Ē": "E", "ī": "i", "Ī": "I",
}
ROMANIZATION_MAP = [("ou", "o"), ("uu", "u"), ("oo", "o")]

ALIAS_PASSES = 1
ALIAS_MIN_HITS = 2  # a pair needs EITHER 2 separate passes each naming it in
                    # any direction, OR both directions (A->B and B->A)
                    # independently stated within the SAME single pass — the
                    # full roster goes in as candidates every pass (not
                    # filtered by how often a name itself surfaced), so a
                    # rare name still gets its own chance each pass to name
                    # its counterpart and vice versa. One unidirectional
                    # mention in one pass alone is noise, not evidence.
                    # With ALIAS_PASSES=1 the cross-pass path can never
                    # trigger — only same-pass mutual mentions (A->B and
                    # B->A both stated in the one pass) link a pair now.
                    # Left at 2, not lowered to 1: dropping it would accept
                    # a single unconfirmed claim and risk merging two
                    # unrelated characters, which is exactly what this
                    # threshold exists to prevent.
