import sys

# Must be stripped before parse_universe_args reads positional args below.
REFETCH = "--refetch" in sys.argv
if REFETCH:
    sys.argv.remove("--refetch")

LEGACY_NULL = "--legacy-null" in sys.argv
if LEGACY_NULL:
    sys.argv.remove("--legacy-null")

from src.shared.naming import parse_universe_args  # noqa: E402

UNIVERSE_NAME, ARC, LOCATION, SLUG = parse_universe_args("Classroom of the Elite", "Year 1")
PASSES = (1, 2, 3)
