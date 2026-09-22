"""Character-to-character relation collection: medium-group-scoped queries
and the general pool with star reduction between rounds. Group-to-group
relations (allied/rival/part_of) live in group_relations.py instead.
"""
import logging
from itertools import combinations

from src.infra.ai_clients.gemini_client import GeminiClient
from src.services.collection.relations.steps.constants import (
    ARC, DIRECTED_TYPES, GENERAL_POOL_ROUNDS, MIN_NEW_PAIRS_FOR_THIRD_PASS,
    RELATION_TYPES, SINGLE_PASS_MAX_N, STAR_MIN_POOL, STAR_MIN_REMOVE,
    STAR_REDUCTION_FRACTION, UNIVERSE_NAME,
)
from src.shared.decorators import announce

log = logging.getLogger(__name__)


def create_client() -> GeminiClient:
    return GeminiClient()


def pairs_from_result(rt, result):
    """Decomposes any N-way clique into pairs, for yield/degree counting
    only. The merged output keeps cliques intact instead (see
    merge.merge_pass_results)."""
    if rt in DIRECTED_TYPES:
        return [(r["source"], r["target"]) for r in result["relations"]]
    return [pair for r in result["relations"] for pair in combinations(r["members"], 2)]


def canon_pair(rt, pair):
    return pair if rt in DIRECTED_TYPES else tuple(sorted(pair))


def collect_relation_type(client, characters, level_tag, rt):
    """Adaptive per-type pass budget, replacing a fixed count decided from
    list size alone. Real data (MHA Sports Festival, 61-candidate general
    pool) showed list-size and even pass-1 yield are both poor predictors of
    whether pass 2 is worth running — one type ("want") looked sparse on
    pass 1 (6 pairs) and still doubled its total on pass 2 (+6 new), while a
    rich-looking type ("against", 20 pairs on pass 1) got zero new pairs
    from its pass 2. So pass 2 is never pre-emptively skipped from pass 1's
    yield alone; instead pass 3 is gated on pass 2's actual measured yield,
    which the same data shows is a reliable signal (the one pass that added
    nothing new was correctly the one worth stopping after).
    A list of SINGLE_PASS_MAX_N or fewer has so few possible pairs that one
    deterministic pass covers it; temp=0 there since there is no second pass
    to diversify against. Passes 2/3, when they run, use temp=0.4 to spread
    across different answers instead of repeating pass 1."""
    n = len(characters)
    results = {}
    seen_pairs = set()

    def run_pass(p, temp):
        log.info("  %-24s relation=%-8s pass=%d temp=%.1f", level_tag, rt, p, temp)
        result = client.relations(rt, characters, UNIVERSE_NAME, ARC, pass_number=p, temperature=temp)
        results[str(p)] = result
        pairs = {canon_pair(rt, pr) for pr in pairs_from_result(rt, result)}
        new_pairs = pairs - seen_pairs
        seen_pairs.update(pairs)
        return new_pairs

    run_pass(1, 0.0)
    if n <= SINGLE_PASS_MAX_N:
        return results

    new_in_pass2 = run_pass(2, 0.4)
    if len(new_in_pass2) < MIN_NEW_PAIRS_FOR_THIRD_PASS:
        log.info("  %-24s relation=%-8s stopping at 2 passes (pass 2 added %d new pair(s), need >=%d for a 3rd)",
                  level_tag, rt, len(new_in_pass2), MIN_NEW_PAIRS_FOR_THIRD_PASS)
        return results

    run_pass(3, 0.4)
    return results


def collect_for_list(client, characters, level_tag):
    """Run all 4 relation types over `characters`, each with its own
    adaptive pass budget (see collect_relation_type) — some types are
    consistently sparser than others and should not pay for passes a richer
    type earns."""
    log.info("%-24s n=%-3d", level_tag, len(characters))
    return {rt: collect_relation_type(client, characters, level_tag, rt) for rt in RELATION_TYPES}


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
                seen.add(canon_pair(rt, pair))
        for a, b in seen:
            if a in degree:
                degree[a] += 1
            if b in degree:
                degree[b] += 1
    return degree


def apply_star_reduction(names, degree):
    """Remove the top STAR_REDUCTION_FRACTION of `names` by combined degree,
    so the next round's attention goes to whoever is left instead of
    re-asking about characters already well covered.
    Previously gated on a fixed degree window (>= max-2), which on real data
    almost never caught STAR_MIN_REMOVE people at once — a long-tailed
    degree distribution rarely has several characters tied near the literal
    max — so reduction silently never fired and every round re-asked the
    exact same question (and, since the candidate list never changed, the
    prompt cache made rounds 2/3 verbatim no-ops). A straight top-fraction
    cut always fires once there is a real pool to trim."""
    if len(names) <= STAR_MIN_POOL:
        return list(names), []
    eligible = sorted((n for n in names if degree.get(n, 0) > 0),
                       key=lambda n: degree.get(n, 0), reverse=True)
    max_remove = len(names) - STAR_MIN_POOL
    to_remove = min(max_remove, int(len(names) * STAR_REDUCTION_FRACTION))
    if to_remove < STAR_MIN_REMOVE:
        return list(names), []
    removed = set(eligible[:to_remove])
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
