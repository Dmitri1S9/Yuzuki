"""Group collection and consolidation for stage 1 — medium/large group passes,
overlap-based clustering across passes, and the surviving clusters formatted
for output/persistence.
"""
import logging
from collections import Counter

from src.infra.ai_clients.gemini_client import GeminiClient
from src.services.collection.cast.constants import (
    ARC, CAST_PASSES, DEDUP_OVERLAP, GROUP_TYPES, LOCATION, ROSTER_MIN_PASSES,
    SURVIVE_PASSES, UNIVERSE_NAME,
)
from src.services.collection.cast.roster import name_key
from src.shared.decorators import announce, report

log = logging.getLogger(__name__)


def create_client() -> GeminiClient:
    return GeminiClient()


def run_group(client: GeminiClient, group_type: str) -> list[dict]:
    results = []
    for pass_number in range(1, CAST_PASSES[group_type] + 1):
        log.info("  %s pass=%d ...", group_type, pass_number)
        results.append(client.group(group_type, UNIVERSE_NAME, ARC,
                                     pass_number=pass_number, location=LOCATION))
    return results


@announce("collecting groups: medium/large/isolates, 3 passes each, no character list given")
@report(lambda r: f"collected {sum(len(v) for v in r.values())} raw pass results")
def collect_raw_groups(client: GeminiClient) -> dict[str, list[dict]]:
    return {ct: run_group(client, ct) for ct in CAST_PASSES}


def overlap(a: set, b: set) -> float:
    # overlap coefficient, not Jaccard: |A∩B| / min(|A|,|B|). Jaccard punishes
    # size mismatch twice (missing AND extra names), so a short pass that is a
    # clean subset of a long one still fails to cluster on one name of drift.
    # Overlap coefficient asks only "is the short list contained in the long
    # one," which is the actual question for "same group, different recall."
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def merge_groups(results: list[dict], group_type: str, key_fn=name_key) -> list[dict]:
    raw_groups = []
    for pass_idx, pass_data in enumerate(results, start=1):
        for g in pass_data.get("groups", []):
            members = {key_fn(m) for m in g["members"]}
            if members:
                raw_groups.append({"name": g["name"], "members": members,
                                    "pass": pass_idx, "leader": g.get("leader")})

    clusters: list[dict] = []
    for rg in raw_groups:
        for cl in clusters:
            if overlap(cl["members"], rg["members"]) >= DEDUP_OVERLAP[group_type]:
                cl["members"] |= rg["members"]
                cl["passes"].add(rg["pass"])
                cl["names"].append(rg["name"])
                cl["leaders"].append(rg["leader"])
                break
        else:
            clusters.append({"members": set(rg["members"]), "passes": {rg["pass"]},
                              "names": [rg["name"]], "leaders": [rg["leader"]]})

    survivors = []
    for cl in clusters:
        if len(cl["passes"]) >= SURVIVE_PASSES[group_type]:
            survivors.append(cl)
        else:
            log.info("dropped %s group %r (passes=%s < %d)", group_type,
                     cl["names"][0], sorted(cl["passes"]), SURVIVE_PASSES[group_type])
    return survivors


def find_leaders_outside_members(survivors: list[dict], group_type: str, key_fn=name_key) -> list[dict]:
    problems = []
    for cl in survivors:
        for leader in cl["leaders"]:
            if leader and key_fn(leader) not in cl["members"]:
                problems.append({"group_type": group_type, "group": cl["names"][0], "leader": leader})
    return problems


@announce("consolidating medium/large groups across passes")
@report(lambda r: f"groups={ {gt: len(r[gt]) for gt in r} }")
def consolidate_groups(raw_groups: dict[str, list[dict]], resolve) -> dict[str, list[dict]]:
    merged = {gt: merge_groups(raw_groups[gt], gt, resolve) for gt in GROUP_TYPES}
    for gt, survivors in merged.items():
        for problem in find_leaders_outside_members(survivors, gt, resolve):
            log.warning("LEADER NOT IN MEMBERS (%s, %r): %r",
                        problem["group_type"], problem["group"], problem["leader"])
    return merged


def format_groups_for_output(merged_groups: dict, canon: dict) -> dict:
    return {
        gt: [{"name": Counter(cl["names"]).most_common(1)[0][0],
              "name_variants": sorted(set(cl["names"])),
              "passes": sorted(cl["passes"]),
              "members": sorted(canon[k] for k in cl["members"] if k in canon)}
             for cl in merged_groups[gt]]
        for gt in GROUP_TYPES
    }


def find_medium_or_large_exclusive_names(presence: dict, canon: dict) -> tuple[list[str], list[str]]:
    in_medium = {k for k, p in presence.items() if len(p.get("medium", set())) >= ROSTER_MIN_PASSES}
    in_large = {k for k, p in presence.items() if len(p.get("large", set())) >= ROSTER_MIN_PASSES}
    only_medium = sorted(canon[k] for k in in_medium - in_large)
    only_large = sorted(canon[k] for k in in_large - in_medium)
    return only_medium, only_large
