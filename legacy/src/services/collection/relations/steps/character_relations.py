"""Character-to-character relation collection: medium-group-scoped queries
and the general pool with star reduction between rounds. Group-to-group
relations (allied/rival/part_of) live in group_relations.py instead.
"""
from itertools import combinations

from src.infra.ai_clients.gemini_client import GeminiClient
from src.services.collection.relations.steps.constants import (
    ARC, DIRECTED_TYPES, GENERAL_POOL_ROUNDS, MEDIUM_STAR_REDUCTION_FRACTION,
    MIN_NEW_PAIRS_FOR_THIRD_PASS, RELATION_TYPES, SINGLE_PASS_MAX_N, STAR_MIN_POOL,
    STAR_MIN_REMOVE, STAR_REDUCTION_FRACTION, UNIVERSE_NAME,
)
from src.shared.decorators import announce, logged
from src.shared.naming import display_name


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


@logged(lambda _, client, characters, level_tag, rt, p, temp, context=None, alias_map=None:
        f"  {level_tag:<24} relation={rt:<8} pass={p} temp={temp:.1f}")
def run_relation_pass(client, characters, level_tag, rt, p, temp, context=None, alias_map=None):
    """One relation-type call, one pass — the primitive every collection
    shape (adaptive per-type budget, a group's own controlled 2-step flow,
    a single cross-group pass) is built from. alias_map: same recognition
    aid rank()/flag() get (2026-09-23) — appended in parentheses to each
    name sent in; merge.py's merge_pass_results resolves it back out of
    the response, same as features/steps/collection.py does for rank/flag."""
    display_characters = [display_name(n, alias_map or {}) for n in characters]
    return client.relations(rt, display_characters, UNIVERSE_NAME, ARC, context=context,
                             pass_number=p, temperature=temp)


@logged(lambda _, level_tag, rt, new_count, min_needed:
        f"  {level_tag:<24} relation={rt:<8} stopping at 2 passes (pass 2 added {new_count} new pair(s), "
        f"need >={min_needed} for a 3rd)")
def _log_stopping_at_2_passes(level_tag: str, rt: str, new_count: int, min_needed: int) -> None:
    pass


def collect_relation_type(client, characters, level_tag, rt, alias_map=None):
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
        result = run_relation_pass(client, characters, level_tag, rt, p, temp, alias_map=alias_map)
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
        _log_stopping_at_2_passes(level_tag, rt, len(new_in_pass2), MIN_NEW_PAIRS_FOR_THIRD_PASS)
        return results

    run_pass(3, 0.4)
    return results


@logged(lambda _, client, characters, level_tag, alias_map=None: f"{level_tag:<24} n={len(characters):<3}")
def collect_for_list(client, characters, level_tag, alias_map=None):
    """Run all 4 relation types over `characters`, each with its own
    adaptive pass budget (see collect_relation_type) — some types are
    consistently sparser than others and should not pay for passes a richer
    type earns."""
    return {rt: collect_relation_type(client, characters, level_tag, rt, alias_map) for rt in RELATION_TYPES}


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


def apply_star_reduction(names, degree, fraction=STAR_REDUCTION_FRACTION):
    """Remove the top `fraction` of `names` by combined degree, so the next
    round's attention goes to whoever is left instead of re-asking about
    characters already well covered. `fraction` is caller-supplied (round 1's
    general_pool uses STAR_REDUCTION_FRACTION; round 2's within-group
    reduction uses its own, larger MEDIUM_STAR_REDUCTION_FRACTION) — this
    function itself doesn't care which level is calling it.
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
    to_remove = min(max_remove, int(len(names) * fraction))
    if to_remove < STAR_MIN_REMOVE:
        return list(names), []
    removed = set(eligible[:to_remove])
    return [n for n in names if n not in removed], sorted(removed)


@logged(lambda _, round_idx, removed: f"general_pool r{round_idx} -> removed {len(removed)} star(s): {removed}")
def _log_general_pool_reduction(round_idx: int, removed: list) -> None:
    pass


@announce("collecting general_pool relations (up to 3 rounds, star reduction between rounds)")
def collect_general_pool(client, roster, alias_map=None):
    current = list(roster)
    rounds = []
    for round_idx in range(1, GENERAL_POOL_ROUNDS + 1):
        results = collect_for_list(client, current, f"general_pool r{round_idx}", alias_map)
        rounds.append({"round": round_idx, "candidates": list(current), "results": results})
        if round_idx < GENERAL_POOL_ROUNDS:
            degree = combined_degree(results, current)
            current, removed = apply_star_reduction(current, degree)
            _log_general_pool_reduction(round_idx, removed)
    return rounds


@logged(lambda _, level_tag, removed: f"  {level_tag:<24} -> removed {len(removed)} star(s) before pass 2: {removed}")
def _log_medium_group_reduction(level_tag: str, removed: list) -> None:
    pass


def collect_medium_group_relations(client, group_name, members, alias_map=None):
    """Round 2: relations within one medium group. 1 pass per type normally;
    if the group is bigger than SINGLE_PASS_MAX_N, star-reduce this group's
    own member list by MEDIUM_STAR_REDUCTION_FRACTION (by pass-1 combined
    degree) before asking pass 2 — a smaller, more focused list, not a
    verbatim re-ask of the same full group."""
    level_tag = f"medium:{group_name}"
    results = {rt: {"1": run_relation_pass(client, members, level_tag, rt, 1, 0.0, alias_map=alias_map)}
               for rt in RELATION_TYPES}
    if len(members) <= SINGLE_PASS_MAX_N:
        return results

    degree = combined_degree(results, members)
    reduced, removed = apply_star_reduction(members, degree, MEDIUM_STAR_REDUCTION_FRACTION)
    _log_medium_group_reduction(level_tag, removed)
    for rt in RELATION_TYPES:
        results[rt]["2"] = run_relation_pass(client, reduced, level_tag, rt, 2, 0.4, alias_map=alias_map)
    return results


@logged(lambda _, name, count: f"medium:{name:<20} n={count:<3}")
def _log_medium_group(name: str, count: int) -> None:
    pass


@announce("collecting medium-group-scoped relations")
def collect_medium_groups(client, medium_groups, alias_map=None):
    per_group = []
    for g in medium_groups:
        members = g["members"]
        if len(members) < 2:
            continue
        _log_medium_group(g["name"], len(members))
        results = collect_medium_group_relations(client, g["name"], members, alias_map)
        per_group.append({"group": g["name"], "members": members, "results": results})
    return per_group


def _group_context_block(medium_groups) -> str:
    lines = ["Established groups in this universe (name: members):"]
    for g in medium_groups:
        lines.append(f"- {g['name']}: {', '.join(g['members'])}")
    lines.append(
        "\nOnly report a pair when the two characters belong to DIFFERENT groups from this "
        "list above (or at least one of them belongs to none of these groups). Skip any pair "
        "who are both members of the exact same group — those relations are already collected "
        "separately and are not the question here."
    )
    return "\n".join(lines)


@announce("collecting cross-group relations")
def collect_cross_group_relations(client, roster, medium_groups, alias_map=None):
    """Round 3: relations between characters in different medium groups —
    the gap general_pool (flat, group-blind) and collect_medium_groups
    (within one group only) both leave uncovered. One combined call per
    relation type (not per group-pair — avoids an N-groups -> N*(N-1)/2
    blowup for a cast with many groups), fed the full group structure as
    context so the model can reason about who's in a different group from
    whom. A single pass per type — this is a targeted supplementary pass,
    not meant to exhaustively search the whole roster the way general_pool
    does."""
    if len(medium_groups) < 2:
        return {rt: {} for rt in RELATION_TYPES}
    context = _group_context_block(medium_groups)
    return {
        rt: {"1": run_relation_pass(client, roster, "cross_group", rt, 1, 0.0, context=context, alias_map=alias_map)}
        for rt in RELATION_TYPES
    }
