"""Group collection and consolidation for stage 1 — medium/large group passes,
overlap-based clustering across passes, and the surviving clusters formatted
for output/persistence.
"""
import logging
from collections import Counter

from src.infra.ai_clients.gemini_client import GeminiClient
from src.services.collection.cast.steps.constants import (
    ARC, DEDUP_OVERLAP, GROUP_TYPES, LOCATION, ROSTER_MIN_PASSES, SURVIVE_PASSES, UNIVERSE_NAME,
)
from src.services.collection.cast.steps.name_matching import name_key
from src.shared.decorators import announce, logged, report


def create_client() -> GeminiClient:
    return GeminiClient()


@announce("collecting groups: medium (own call), large+isolates (combined call)")
@report(lambda r: f"collected {sum(len(v) for v in r.values())} raw pass results")
def collect_raw_groups(client: GeminiClient, characters: list[str] | None = None) -> dict[str, list[dict]]:
    # characters: AniList's cast list for this title (see anime_db.py),
    # fetched before any model call now exists — passed as a ground-truth
    # reference, not a cap (see base_client.py's group_medium()/
    # group_large_isolates() for why this used to be impossible: groups
    # used to BE the roster's only source).
    #
    # Medium, large and isolates used to be 3 separate calls x 2 passes
    # (6 total); now 2 calls, 1 pass each (2026-09-23, cost cut) — medium
    # kept as its own prompt (opposite definition from large, risk of the
    # model blurring the two if combined), large+isolates combined into
    # one (unrelated axes, safe to ask together). Each value below is still
    # shaped as a list of pass-results (length 1 now, was 2) so
    # consolidate_groups/extract_candidate_names need no change — they
    # only ever iterated "however many passes came in."
    medium_result = client.group_medium(UNIVERSE_NAME, ARC, location=LOCATION, characters=characters)
    large_result = client.group_large_isolates(UNIVERSE_NAME, ARC, location=LOCATION, characters=characters)
    return {
        "medium": [{"groups": [g for g in medium_result.get("groups", []) if g.get("group_type") == "medium"]}],
        "large": [{"groups": [g for g in large_result.get("groups", []) if g.get("group_type") == "large"]}],
        "isolates": [{"isolates": large_result.get("isolates", [])}],
    }


def overlap(a: set, b: set) -> float:
    # overlap coefficient, not Jaccard: |A∩B| / min(|A|,|B|). Jaccard punishes
    # size mismatch twice (missing AND extra names), so a short pass that is a
    # clean subset of a long one still fails to cluster on one name of drift.
    # Overlap coefficient asks only "is the short list contained in the long
    # one," which is the actual question for "same group, different recall."
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


@logged(lambda _, group_type, names, passes:
        f"dropped {group_type} group {names[0]!r} (passes={sorted(passes)} < {SURVIVE_PASSES[group_type]})")
def _log_dropped_group(group_type: str, names: list[str], passes: set) -> None:
    pass


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
            _log_dropped_group(group_type, cl["names"], cl["passes"])
    return survivors


def find_leaders_outside_members(survivors: list[dict], group_type: str, key_fn=name_key) -> list[dict]:
    problems = []
    for cl in survivors:
        for leader in cl["leaders"]:
            if leader and key_fn(leader) not in cl["members"]:
                problems.append({"group_type": group_type, "group": cl["names"][0], "leader": leader})
    return problems


@logged(lambda _, problem: f"LEADER NOT IN MEMBERS ({problem['group_type']}, {problem['group']!r}): {problem['leader']!r}",
        level=logging.WARNING)
def _log_leader_not_in_members(problem: dict) -> None:
    pass


@announce("consolidating medium/large groups across passes")
@report(lambda r: f"groups={ {gt: len(r[gt]) for gt in r} }")
def consolidate_groups(raw_groups: dict[str, list[dict]], resolve) -> dict[str, list[dict]]:
    merged = {gt: merge_groups(raw_groups[gt], gt, resolve) for gt in GROUP_TYPES}
    for gt, survivors in merged.items():
        for problem in find_leaders_outside_members(survivors, gt, resolve):
            _log_leader_not_in_members(problem)
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


@logged(lambda _, members: f"synthesized one large group ({UNIVERSE_NAME!r}) from AniList's cast list: {len(members)} member(s)")
def _log_synthesized_large_group(members: set) -> None:
    pass


def synthesize_large_group_from_cast(merged_groups: dict, anilist_names: list[str],
                                      canon: dict, resolve) -> dict:
    """When no natural "large" group survived collection (the model's own
    passes never agreed on one, or never proposed one at all), AniList's
    full cast list for the title becomes one big group named for the
    title itself — everyone the roster and AniList agree exists.
    Membership is intersected with canon, so this can never add a name
    outside the roster; does nothing if AniList had nothing (empty
    anilist_names) or a real large group already exists."""
    if merged_groups.get("large") or not anilist_names:
        return merged_groups
    members = {resolve(n) for n in anilist_names} & canon.keys()
    if not members:
        return merged_groups
    merged_groups["large"] = [{
        "members": members, "passes": set(), "names": [UNIVERSE_NAME], "leaders": [None],
    }]
    _log_synthesized_large_group(members)
    return merged_groups


def find_medium_or_large_exclusive_names(presence: dict, canon: dict) -> tuple[list[str], list[str]]:
    in_medium = {k for k, p in presence.items() if len(p.get("medium", set())) >= ROSTER_MIN_PASSES}
    in_large = {k for k, p in presence.items() if len(p.get("large", set())) >= ROSTER_MIN_PASSES}
    only_medium = sorted(canon[k] for k in in_medium - in_large)
    only_large = sorted(canon[k] for k in in_large - in_medium)
    return only_medium, only_large
