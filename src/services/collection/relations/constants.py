from src.shared.naming import parse_universe_args

UNIVERSE_NAME, ARC, LOCATION, SLUG = parse_universe_args("Classroom of the Elite", "Year 1")

RELATION_TYPES = ("for", "against", "want", "with")
DIRECTED_TYPES = ("for", "want")

GENERAL_POOL_ROUNDS = 3
STAR_WINDOW = 2          # remove degree in [M-2, M]
STAR_MIN_CANDIDATES = 3  # ...but only if that band catches >=3 people

LOW_INFO_MIN_DEGREE = 2  # a single, one-sided mention (e.g. one directed "for"
                          # found once) isn't enough to justify spending flag/
                          # ordinal collection on a character — not a confirmed
                          # isolate, just thin. Isolates are exempt: their
                          # relation count can be 0 or 1 and that's still real
                          # signal (a positively-identified loner), not absence
                          # of information.
