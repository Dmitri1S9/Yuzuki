import re
import sys


def slugify(universe: str, arc: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", f"{universe}_{arc}".lower()).strip("_")


def parse_universe_args(default_name: str, default_arc: str, default_location: str = ""):
    args = sys.argv[1:]
    name = args[0] if len(args) > 0 else default_name
    arc = args[1] if len(args) > 1 else default_arc
    location = args[2] if len(args) > 2 else default_location
    return name, arc, location, slugify(name, arc)
