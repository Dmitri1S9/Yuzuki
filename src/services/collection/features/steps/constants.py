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
# Both ordinals and flags now collect 2 passes — the 3rd pass's marginal
# gain wasn't worth paying for (user's call). Both go through
# consensus.flag_consensus's 2-pass algorithm now (build blocks from
# agreement, drop the worst-disagreeing characters until kappa clears
# target) instead of consensus.consensus_rank's 3-pass hill-climbing search,
# which has hardcoded 3-pass assumptions (kappa_raw_12/13/23, etc.) and
# isn't a drop-in fit for 2 passes. consensus_rank is left in place, tested,
# unused — not deleted, in case 3-pass ordinals come back.
PASSES = (1, 2)
FLAG_PASSES = (1, 2)
