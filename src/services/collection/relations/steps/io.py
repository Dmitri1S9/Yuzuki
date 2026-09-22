"""Logging bootstrap and this run's I/O. Stage 1's roster/groups are read
from Postgres — the DCS-approved state, which may include human edits made
after stage 1's own model run finished (a rename, a deleted fabricated name,
an added character) — never from a leftover file, which would silently miss
exactly those edits.
"""
import logging

from src.repository import UniverseRepository
from src.services.collection.relations.steps.constants import ARC, LOCATION, UNIVERSE_NAME
from src.services.collection.relations.steps.low_info import has_small_group
from src.shared.decorators import announce, report

log = logging.getLogger(__name__)
_universe_repo = UniverseRepository()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")


def _group_to_dict(g) -> dict:
    return {"name": g.get_name(), "members": g.get_members()}


@announce("loading approved roster + groups from the database")
@report(lambda r: f"approved roster: {len(r[0])} characters, {len(r[2])} medium groups, {len(r[3])} large groups")
def load_cast_data():
    universe = _universe_repo.get_universe(UNIVERSE_NAME, ARC)
    if universe is None:
        raise RuntimeError(
            f"universe {UNIVERSE_NAME!r}/{ARC!r} not found — run stage 1 (cast) and approve the "
            "roster in DCS before running stage 3 (relations)")
    roster = [c.get_name() for c in universe.get_roster()]
    isolate_set = {c.get_name() for c in universe.get_roster() if c.is_isolated()}
    medium_groups = [_group_to_dict(g) for g in universe.get_groups() if g.get_type() == "medium"]
    large_groups = [_group_to_dict(g) for g in universe.get_groups() if g.get_type() == "large"]
    return roster, isolate_set, medium_groups, large_groups, universe.get_id()


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


def log_final_summary(out: dict, roster: list[str]) -> None:
    q = out["quality"]
    log.info("edge counts: %s", q["edge_counts"])
    log.info("edge counts by level: %s", q["edge_counts_by_level"])
    log.info("has_small_group: %d characters", len(out["has_small_group"]))
    log.info("group_relations: allied=%d rival=%d",
              len(out["group_relations"]["allied"]), len(out["group_relations"]["rival"]))
    log.info("low_info characters: %d / %d", len(out["low_info_characters"]), len(roster))
