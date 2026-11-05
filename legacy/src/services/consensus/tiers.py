"""The majority-tier hard floor under consensus_rank's block search. The
kappa objective alone will happily fuse characters from genuinely
different tiers into one block if that raises pairwise agreement (observed
on authority_scope: one 27-member block spanning raw tiers 0, 1 and 2).
Blocks may freely split a shared tier into finer sub-blocks (that can only
help or be neutral to kappa, per the tier-level metric), but must never
merge two characters whose majority tier (>=2-of-N-passes vote) is defined
and differs. A character with no majority tier (a tie, or too few passes)
is unconstrained — it carries no vote to conflict with.
"""
from collections import Counter


def majority_tier(idx: int, tiers_by_idx: dict, passes: tuple) -> int | None:
    values = [tiers_by_idx[p][idx] for p in passes if idx in tiers_by_idx[p]]
    if len(values) < 2:
        return None
    for tier, count in Counter(values).items():
        if count >= 2:
            return tier
    return None


def block_tier(block: list[int], maj_tier: dict) -> int | None:
    tiers_present = {maj_tier[e] for e in block if maj_tier[e] is not None}
    assert len(tiers_present) <= 1, f"tier-consistency invariant broken: {tiers_present}"
    return next(iter(tiers_present), None)


def tiers_compatible(tier_a: int | None, tier_b: int | None) -> bool:
    return tier_a is None or tier_b is None or tier_a == tier_b
