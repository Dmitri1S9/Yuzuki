from src.shared.naming import parse_universe_args

UNIVERSE_NAME, ARC, LOCATION, SLUG = parse_universe_args("Classroom of the Elite", "Year 1")

CAST_PASSES = {"medium": 3, "large": 3, "isolates": 3}
GROUP_TYPES = ("medium", "large")
SURVIVE_PASSES = {"medium": 2, "large": 2}
DEDUP_OVERLAP = {"medium": 0.70, "large": 0.50}
ROSTER_MIN_PASSES = 2

SPECIAL_CHAR_MAP = {
    "ō": "o", "Ō": "O", "ū": "u", "Ū": "U", "ā": "a", "Ā": "A",
    "ē": "e", "Ē": "E", "ī": "i", "Ī": "I",
}
ROMANIZATION_MAP = [("ou", "o"), ("uu", "u"), ("oo", "o")]

ALIAS_PASSES = 3
ALIAS_MIN_HITS = 2  # a pair needs EITHER 2 separate passes each naming it in
                    # any direction, OR both directions (A->B and B->A)
                    # independently stated within the SAME single pass — the
                    # full roster goes in as candidates every pass (not
                    # filtered by how often a name itself surfaced), so a
                    # rare name still gets its own chance each pass to name
                    # its counterpart and vice versa. One unidirectional
                    # mention in one pass alone is noise, not evidence.
