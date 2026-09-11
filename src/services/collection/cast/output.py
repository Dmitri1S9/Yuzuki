"""Logging bootstrap, output assembly, and the JSON handoff file stage 1
writes for stage 2/3/4 to read within the same pipeline run (the database is
the durable record; this file is this run's inter-stage communication —
there's no shared memory between the separate `docker compose run` processes
each stage runs as).
"""
import json
import logging

from src.services.collection.cast.constants import ARC, LOCATION, SLUG, UNIVERSE_NAME
from src.services.collection.cast.groups import find_medium_or_large_exclusive_names
from src.shared.paths import run_path

log = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")


def assemble_output(roster, groups_out, raw_cluster_count, spelling_merge_count,
                     alias_pairs, canon, dropped, ambiguous, presence) -> dict:
    only_medium, only_large = find_medium_or_large_exclusive_names(presence, canon)
    return {
        "universe": {"universe": UNIVERSE_NAME, "time_period": ARC, "location": LOCATION},
        "roster": roster,
        "groups": groups_out,
        "quality": {
            "raw_name_clusters": raw_cluster_count,
            "spelling_merges": spelling_merge_count,
            "aliases_detected": len(alias_pairs),
            "roster_size": len(roster),
            "dropped_below_threshold": len(canon) - len(roster),
            "dropped_names": dropped,
            "ambiguous_name_matches": ambiguous,
            "groups_per_type": {gt: len(groups_out[gt]) for gt in groups_out},
            "medium_only": only_medium,
            "large_only": only_large,
        },
    }


def write_output_file(output: dict) -> None:
    with open(run_path(f"stage1_cast_{SLUG}.json"), "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


def log_final_summary(output: dict) -> None:
    q = output["quality"]
    log.info("raw_clusters=%d spelling_merged=%d aliases=%d roster=%d dropped=%d groups=%s",
             q["raw_name_clusters"], q["spelling_merges"], q["aliases_detected"],
             q["roster_size"], q["dropped_below_threshold"], q["groups_per_type"])
