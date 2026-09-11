"""Logging bootstrap and this run's JSON handoff files — stage 1's output is
read here, relations_passes/relations_merged are written here for stage 2/4
to read within the same pipeline run (see cast/output.py's docstring for why
these files exist alongside the database).
"""
import json
import logging

from src.services.collection.relations.constants import ARC, LOCATION, SLUG, UNIVERSE_NAME
from src.services.collection.relations.low_info import has_small_group
from src.shared.decorators import announce, report
from src.shared.paths import run_path

log = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")


@announce("loading frozen roster + groups from stage 1's output")
@report(lambda r: f"frozen roster: {len(r[0])} characters, {len(r[2])} medium groups, {len(r[3])} large groups")
def load_cast_data():
    with open(run_path(f"stage1_cast_{SLUG}.json"), encoding="utf-8") as f:
        cast = json.load(f)
    roster = [r["name"] for r in cast["roster"]]
    isolate_set = {r["name"] for r in cast["roster"] if r["is_isolated"]}
    medium_groups = cast["groups"]["medium"]
    large_groups = cast["groups"]["large"]
    return roster, isolate_set, medium_groups, large_groups


def write_passes_file(medium_per_group, general_rounds) -> None:
    with open(run_path(f"relations_passes_{SLUG}.json"), "w", encoding="utf-8") as f:
        json.dump({"medium_groups": medium_per_group, "general_pool": general_rounds},
                   f, ensure_ascii=False, indent=2)


def assemble_output(merged, dropped, group_relations, group_relations_dropped,
                     low_info, general_rounds) -> dict:
    edge_counts_by_level = {}
    for rt, entries in merged.items():
        for e in entries:
            key = (rt, e["source_level"].split(":")[0])
            edge_counts_by_level[key] = edge_counts_by_level.get(key, 0) + 1
    return {
        "universe": {"universe": UNIVERSE_NAME, "time_period": ARC, "location": LOCATION},
        "relations": merged,
        "group_relations": group_relations,  # separate table, never merged into character edges
        "has_small_group": has_small_group(merged),
        "low_info_characters": low_info,  # 0 relations, not isolate — stage2 skips flag/ordinal collection for these
        "quality": {
            "dropped": len(dropped),
            "edge_counts": {rt: len(e) for rt, e in merged.items()},
            "edge_counts_by_level": {f"{rt}/{lvl}": c for (rt, lvl), c in sorted(edge_counts_by_level.items())},
            "general_pool_final_size": len(general_rounds[-1]["candidates"]),
            "group_relations_dropped": len(group_relations_dropped),
        },
    }


def write_merged_output_file(out: dict) -> None:
    with open(run_path(f"relations_merged_{SLUG}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def log_final_summary(out: dict, roster: list[str]) -> None:
    q = out["quality"]
    log.info("edge counts: %s", q["edge_counts"])
    log.info("edge counts by level: %s", q["edge_counts_by_level"])
    log.info("has_small_group: %d characters", len(out["has_small_group"]))
    log.info("group_relations: allied=%d rival=%d",
              len(out["group_relations"]["allied"]), len(out["group_relations"]["rival"]))
    log.info("low_info characters: %d / %d", len(out["low_info_characters"]), len(roster))
