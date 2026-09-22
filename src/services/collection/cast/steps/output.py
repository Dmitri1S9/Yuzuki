"""Logging bootstrap and output assembly. Stage 1's roster/groups draft is
handed to DCS in-memory (push_draft_to_dcs, steps/persistence.py) and to
Postgres once a human approves it (confirm_roster) — later stages read that
approved database state directly, not a leftover file from this run.
"""
import logging

from src.services.collection.cast.steps.constants import ARC, LOCATION, UNIVERSE_NAME
from src.services.collection.cast.steps.groups import find_medium_or_large_exclusive_names

log = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")


def assemble_output(roster, groups_out, raw_cluster_count, spelling_merge_count,
                     alias_pairs, canon, ambiguous, presence) -> dict:
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
            "low_confidence_count": sum(1 for c in roster if c["low_confidence"]),
            "confirmed_by_database_count": sum(1 for c in roster if c["confirmed_by_database"]),
            "ambiguous_name_matches": ambiguous,
            "groups_per_type": {gt: len(groups_out[gt]) for gt in groups_out},
            "medium_only": only_medium,
            "large_only": only_large,
        },
    }


def log_final_summary(output: dict) -> None:
    q = output["quality"]
    log.info("raw_clusters=%d spelling_merged=%d aliases=%d roster=%d low_confidence=%d "
             "confirmed_by_database=%d groups=%s",
             q["raw_name_clusters"], q["spelling_merges"], q["aliases_detected"],
             q["roster_size"], q["low_confidence_count"], q["confirmed_by_database_count"],
             q["groups_per_type"])
