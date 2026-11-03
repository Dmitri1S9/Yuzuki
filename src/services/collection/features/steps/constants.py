import sys

# Must be stripped before parse_universe_args reads positional args below.
REFETCH = "--refetch" in sys.argv
if REFETCH:
    sys.argv.remove("--refetch")

LEGACY_NULL = "--legacy-null" in sys.argv
if LEGACY_NULL:
    sys.argv.remove("--legacy-null")

from src.shared.naming import parse_universe_args  # noqa: E402

UNIVERSE_NAME, ARC, LOCATION, SLUG, _ANILIST_TITLE = parse_universe_args("Classroom of the Elite", "Year 1")
# Ordinals: 2 passes, real reconciliation (consensus.ordinal_consensus —
# Borda + hill-climbing search adapted from consensus.py, since ordinals
# have 8-10 tiers and two passes landing one tier apart is normal).
# Flags: 1 pass now (user's call) — a flag's own model call is expensive
# enough per-parameter (51 flags) that a 2nd pass wasn't worth doubling the
# cost for, and there's no reconciliation left to do with only one rater
# (consensus.flag_consensus just reshapes that one pass's own placement
# into the same block/tier output shape everything downstream expects).
PASSES = (1, 2)
FLAG_PASSES = (1,)
