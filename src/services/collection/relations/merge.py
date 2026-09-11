"""Union merge of relation passes with source_level tracking. count is never
summed across levels — see PIPELINE.md, Этап 3 -> Сведение.
"""
import logging

from src.services.collection.relations.constants import DIRECTED_TYPES, RELATION_TYPES
from src.shared.decorators import announce

log = logging.getLogger(__name__)


def merge_pass_results(by_pass, rt, allowed_set, level_tag, dropped):
    """by_pass: {pass_number_str: response}. Union across passes, count how
    many passes named each relation — this is the pass_count *within this
    one level*, never combined with any other level's count. Symmetric
    relations keep their full member list as given (2 = pair, 3+ = clique) —
    NOT decomposed into pairs (that decomposition is for combined_degree's
    star-reduction counting only, see collection.pairs_from_result)."""
    counts = {}
    for result in by_pass.values():
        seen = set()
        for rel in result["relations"]:
            key = (rel["source"], rel["target"]) if rt in DIRECTED_TYPES else tuple(sorted(rel["members"]))
            bad = [n for n in key if n not in allowed_set]
            if bad:
                dropped.append({"level": level_tag, "relation": rt, "entry": list(key), "not_allowed": bad})
                continue
            seen.add(key)
        for key in seen:
            counts[key] = counts.get(key, 0) + 1
    if rt in DIRECTED_TYPES:
        return [{"source": k[0], "target": k[1], "count": c, "source_level": level_tag} for k, c in counts.items()]
    return [{"members": list(k), "count": c, "source_level": level_tag} for k, c in counts.items()]


def merge_medium(per_group, roster_set, dropped):
    # A medium group's member list can contain someone who survived the
    # group-merge clustering in cast/groups.py without individually clearing
    # the personal roster threshold (known desync, not fixed here) — such a
    # name is a valid query-scope member (it's who the model was asked
    # about) but must never leak into the output, since it isn't a roster
    # character anywhere else in the pipeline. Intersect with the roster.
    merged = {rt: [] for rt in RELATION_TYPES}
    for entry in per_group:
        allowed = set(entry["members"]) & roster_set
        level_tag = f"medium:{entry['group']}"
        for rt in RELATION_TYPES:
            merged[rt].extend(merge_pass_results(entry["results"][rt], rt, allowed, level_tag, dropped))
    return merged


def merge_general_pool(rounds, roster_set, dropped):
    """All GENERAL_POOL_ROUNDS sub-rounds are one level ("general_pool") —
    the candidate list shrinks between rounds (star reduction), but they are
    still passes of the same query, not separate levels. A pair's pass_count
    pools together however many of the (up to 9 = 3 rounds x <=3 passes)
    sub-passes named it."""
    flattened = {rt: {} for rt in RELATION_TYPES}
    for rnd in rounds:
        for rt in RELATION_TYPES:
            for pass_num, result in rnd["results"][rt].items():
                flattened[rt][f"r{rnd['round']}p{pass_num}"] = result
    merged = {}
    for rt in RELATION_TYPES:
        merged[rt] = merge_pass_results(flattened[rt], rt, roster_set, "general_pool", dropped)
    return merged


@announce("merging relation passes (medium groups + general_pool)")
def merge_all(medium_per_group, general_rounds, roster):
    roster_set = set(roster)
    dropped = []
    medium = merge_medium(medium_per_group, roster_set, dropped)
    general = merge_general_pool(general_rounds, roster_set, dropped)
    merged = {rt: medium[rt] + general[rt] for rt in RELATION_TYPES}
    for d in dropped:
        log.warning("DROPPED (not in level's candidate list) %s", d)
    return merged, dropped
