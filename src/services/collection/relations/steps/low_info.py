"""Characters with too little relation signal to be worth flag/ordinal
collection — kept in the roster/DB/graph, just skipped by stage2.
"""
from collections import Counter, defaultdict

from src.services.collection.relations.steps.constants import LOW_INFO_MIN_DEGREE


def has_small_group(merged):
    holders = set()
    for entry in merged["with"]:
        if len(entry["members"]) >= 3:
            holders.update(entry["members"])
    return sorted(holders)


def compute_low_info(merged, roster, isolate_set):
    """Characters with fewer than LOW_INFO_MIN_DEGREE distinct (pair, type)
    relationships who also weren't positively identified as isolates and
    aren't linked to anyone who does clear the bar — genuinely too little
    signal, not a confirmed loner and not attached to someone significant.
    Consumed by stage2 (run after this stage) to skip flag/ordinal
    collection for them.

    Counts distinct relationships, not raw entries: the same (pair, type)
    relationship found independently at two levels (medium + general_pool)
    is one relationship corroborated twice, not two relationships — a
    character seen only via one such double-counted entry has degree 1,
    not 2, same as if only one level had found it.

    A character below the degree bar is still kept if at least one of
    their relationship partners clears LOW_INFO_MIN_DEGREE on their own —
    one real connection to someone who is themselves well-attested is worth
    more than the same connection to another thin character."""
    seen = set()
    for rel_type, entries in merged.items():
        for e in entries:
            pair = tuple(sorted(e["members"])) if "members" in e else (e["source"], e["target"])
            seen.add((pair, rel_type))
    degree = Counter()
    partners = defaultdict(set)
    for pair, _rel_type in seen:
        for m in pair:
            degree[m] += 1
        for m in pair:
            partners[m].update(p for p in pair if p != m)

    def has_signal(n):
        if degree[n] >= LOW_INFO_MIN_DEGREE or n in isolate_set:
            return True
        return any(degree[p] >= LOW_INFO_MIN_DEGREE for p in partners[n])

    return sorted(n for n in roster if not has_signal(n))
