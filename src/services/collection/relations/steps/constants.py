from src.shared.naming import parse_universe_args

UNIVERSE_NAME, ARC, LOCATION, SLUG, _ANILIST_TITLE = parse_universe_args("Classroom of the Elite", "Year 1")

RELATION_TYPES = ("for", "against", "want", "with")
DIRECTED_TYPES = ("for", "want")

GENERAL_POOL_ROUNDS = 3
STAR_REDUCTION_FRACTION = 0.25  # remove the top quarter by combined degree each round
STAR_MIN_POOL = 15              # never shrink the pool below this — matches
                                 # SINGLE_PASS_MAX_N below, so a pool already
                                 # this small gets no benefit from another round
STAR_MIN_REMOVE = 3             # don't bother reducing for a small handful

SINGLE_PASS_MAX_N = 15            # a list this size has too few possible pairs
                                    # to need more than one deterministic pass
MIN_NEW_PAIRS_FOR_THIRD_PASS = 3  # pass 2 must turn up at least this many pairs
                                    # unseen in pass 1 to justify a 3rd pass

LOW_INFO_MIN_DEGREE = 2  # a single, one-sided mention (e.g. one directed "for"
                          # found once) isn't enough to justify spending flag/
                          # ordinal collection on a character — not a confirmed
                          # isolate, just thin. Isolates are exempt: their
                          # relation count can be 0 or 1 and that's still real
                          # signal (a positively-identified loner), not absence
                          # of information.
