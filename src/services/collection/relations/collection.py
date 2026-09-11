"""Relation collection: medium-group-scoped queries, the general-pool with
3-round star reduction, and between-group allied/rival queries.
"""
import logging
from itertools import combinations

from src.infra.ai_clients.gemini_client import GeminiClient
from src.services.collection.relations.constants import (
    ARC, DIRECTED_TYPES, GENERAL_POOL_ROUNDS, RELATION_TYPES, STAR_MIN_CANDIDATES,
    STAR_WINDOW, UNIVERSE_NAME,
)
from src.shared.decorators import announce

log = logging.getLogger(__name__)


def create_client() -> GeminiClient:
    return GeminiClient()


def collection_plan(n: int) -> tuple[int, float]:
    """Passes and temperature by candidate-list length. temp=0 with a single
    pass (max-likelihood, no need for diversity); temp=0.4 once there's more
    than one pass to spread across."""
    if n <= 15:
        return 1, 0.0
    if n <= 35:
        return 2, 0.4
    return 3, 0.4


def collect_for_list(client, characters, level_tag):
    """Run all 4 relation types over `characters`, per collection_plan(len(characters))."""
    num_passes, temp = collection_plan(len(characters))
    log.info("%-24s n=%-3d -> %d pass(es), temp=%.1f", level_tag, len(characters), num_passes, temp)
    results = {rt: {} for rt in RELATION_TYPES}
    for rt in RELATION_TYPES:
        for p in range(1, num_passes + 1):
            log.info("  %-24s relation=%-8s pass=%d", level_tag, rt, p)
            results[rt][str(p)] = client.relations(
                rt, characters, UNIVERSE_NAME, ARC, pass_number=p, temperature=temp
            )
    return results


def pairs_from_result(rt, result):
    """For combined_degree only — decomposes any N-way clique into pairs so
    each participant's degree counts. The merged output keeps cliques intact
    instead (see merge.merge_pass_results)."""
    if rt in DIRECTED_TYPES:
        return [(r["source"], r["target"]) for r in result["relations"]]
    return [pair for r in result["relations"] for pair in combinations(r["members"], 2)]


def combined_degree(round_results, characters):
    """Union pairs within this round per relation type, then degree(c) =
    number of distinct (type, partner) edges touching c — a character
    active in 2 relation types has more attention-pull than one active in 1,
    even toward the same partner."""
    degree = {c: 0 for c in characters}
    for rt, by_pass in round_results.items():
        seen = set()
        for result in by_pass.values():
            for pair in pairs_from_result(rt, result):
                key = pair if rt in DIRECTED_TYPES else tuple(sorted(pair))
                seen.add(key)
        for a, b in seen:
            if a in degree:
                degree[a] += 1
            if b in degree:
                degree[b] += 1
    return degree


def apply_star_reduction(names, degree):
    if not degree:
        return list(names), []
    m = max(degree.values())
    candidates = [n for n in names if degree.get(n, 0) >= m - STAR_WINDOW]
    if len(candidates) < STAR_MIN_CANDIDATES:
        return list(names), []
    removed = set(candidates)
    return [n for n in names if n not in removed], sorted(removed)


@announce("collecting general_pool relations (up to 3 rounds, star reduction between rounds)")
def collect_general_pool(client, roster):
    current = list(roster)
    rounds = []
    for round_idx in range(1, GENERAL_POOL_ROUNDS + 1):
        results = collect_for_list(client, current, f"general_pool r{round_idx}")
        rounds.append({"round": round_idx, "candidates": list(current), "results": results})
        if round_idx < GENERAL_POOL_ROUNDS:
            degree = combined_degree(results, current)
            current, removed = apply_star_reduction(current, degree)
            log.info("general_pool r%d -> removed %d star(s): %s", round_idx, len(removed), removed)
    return rounds


@announce("collecting medium-group-scoped relations")
def collect_medium_groups(client, medium_groups):
    per_group = []
    for g in medium_groups:
        members = g["members"]
        if len(members) < 2:
            continue
        results = collect_for_list(client, members, f"medium:{g['name']}")
        per_group.append({"group": g["name"], "members": members, "results": results})
    return per_group


def collect_group_relations(client, groups):
    """groups: combined large+medium group dicts. Two single-pass, temp=0
    calls (allied, rival) — result is a separate table, never merged into
    character edges."""
    group_names = {g["name"] for g in groups}
    result = {}
    dropped = []
    for kind in ("allied", "rival"):
        log.info("group_relations       kind=%-6s n_groups=%d", kind, len(groups))
        response = client.group_relations(kind, groups, UNIVERSE_NAME, ARC)
        pairs = []
        seen = set()
        for pair in response["pairs"]:
            if len(pair) != 2:
                dropped.append({"kind": kind, "pair": pair, "reason": "not a 2-element pair"})
                continue
            bad = [g for g in pair if g not in group_names]
            if bad:
                dropped.append({"kind": kind, "pair": pair, "not_in_groups": bad})
                continue
            key = tuple(sorted(pair))
            if key not in seen:
                seen.add(key)
                pairs.append(list(key))
        result[kind] = pairs
    for d in dropped:
        log.warning("DROPPED group_relations %s", d)
    return result, dropped
