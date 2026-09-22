"""2-pass consensus for a single ORDINAL parameter — sequence reconciliation
via the same Borda-init + hill-climbing search consensus.py/search.py built
(originally for 3 passes, now adapted to 2), not flag_consensus.py's simpler
exact-match-only blocks. flag_consensus.py was deliberately built cheap for
flags (2-3 tiers, blocks only on exact agreement, no search) and stayed
correct there — but got reused for ordinals too when the pipeline moved to 2
passes, and ordinals have 8-10 tiers: two passes landing a character one
tier apart is normal and needs real reconciliation, not "exact match or
nothing." Confirmed live on Bunny Girl Senpai: authority_scope/
loyalty_command collapsed almost everyone into one giant undifferentiated
group under the exact-match rule.

search.py/tiers.py/metric.py are already N-pass-agnostic (majority_tier's
"≥2 votes" already degrades correctly to "both passes agree" at N=2) — only
the things consensus.py itself hardcoded to 3 get redone here for 2. Reused,
not duplicated.

Algorithm:
1. Pre-filter (no search, no confirmation needed): pass_range (tier gap
   between the 2 passes) > 1, or "unknown" in exactly one pass -> excluded
   (None) — genuinely too little info to reconcile, fixable only by a human
   placing them by hand in Observe Beauty (same confirm() path that already
   overrides any algorithmic baseline). "unknown" in BOTH passes is real
   agreement, not absence of data — it gets the same _UNKNOWN sentinel
   flag_consensus.py established, and flows through the search exactly like
   any other agreed tier (see below).
2. Everyone else (pass_range 0 or 1, or agreed-unknown) goes through
   borda_init/hill_climb maximizing 2-pass maximin kappa. tiers.py's
   majority-tier floor only hard-anchors characters both passes agree on
   exactly (gap 0, or agreed-unknown, via _UNKNOWN acting as an ordinary
   tier value that sorts below every real tier) — gap-1 characters have no
   majority tier and are left free for the search to place at whichever
   tier boundary fits best. That's the actual fix: the existing floor
   already does exactly the reconciliation the exact-match rule couldn't.
3. Post-search, a separate greedy pass considers *actually* excluding
   pass_range==1 characters (never gap-0/agreed-unknown ones) — tried
   strictly after the search has already converged, and only excluded if
   doing so measurably improves the maximin kappa key, worst-offender-
   first, capped at _MAX_REMOVAL_FRACTION of the eligible population.
   Excluded means the same thing the pre-filter's None already means: gone
   from this parameter's placement, landing in Observe Beauty's existing
   "removed" zone exactly like any other unplaced character, restorable by
   dragging back in by hand — not a soft "flagged but still placed"
   in-between state requiring its own separate confirm step. The user's
   own call on this: reviewing a per-character removal recommendation one
   at a time across every parameter doesn't scale ("вечно датасет собирать
   буду") — auto-exclude and let recovery be the manual step instead. The
   cap and the "only after every placement already failed" ordering stay
   deliberate regardless: an unconstrained kappa-maximizing search would
   happily exclude everyone it can, since dropping a disagreement is
   always at least as good for kappa as keeping it — that must never be
   the algorithm's own free win, and the final reported kappa is computed
   on the *post-exclusion* population so it actually reflects what got
   kept, not a number that silently ignores its own removals.
"""
import math
import random

import numpy as np

from src.services.consensus.metric import evaluate, maximin_key, sign_matrix
from src.services.consensus.search import borda_init, hill_climb
from src.services.consensus.tiers import majority_tier

PASSES = (1, 2)
RESTARTS = 5
_UNKNOWN = -1  # same sentinel/meaning as flag_consensus.py's — sorts below
               # every real tier, both passes agreeing on it is real signal.
_MAX_REMOVAL_FRACTION = 0.15  # a single run can never recommend removing
                                # more than this share of the eligible pool —
                                # the hard cap against "delete everyone."


def _tier_or_unknown(score: float | None) -> int:
    return int(score // 10) if score is not None else _UNKNOWN


def _greedy_exclude(blocks, pass_codes, pass_valid, m, passes, candidates: set[int]) -> tuple[set[int], dict]:
    """Greedy, worst-offender-first: repeatedly excludes whichever remaining
    candidate's pairs improve the maximin kappa key the most, until none do
    or the cap is hit. Reuses evaluate/maximin_key unmodified by masking the
    excluded index's row/column out of pass_valid — its block placement
    becomes irrelevant to kappa without needing to touch `blocks` itself.
    Returns (excluded_indices, final_valid) — final_valid is what the caller
    must use for the final reported kappa, so it reflects the post-exclusion
    population instead of silently ignoring its own removals."""
    cap = max(0, round(len(candidates) * _MAX_REMOVAL_FRACTION))
    excluded: set[int] = set()
    valid = {p: pass_valid[p].copy() for p in passes}
    current_key = maximin_key(evaluate(blocks, pass_codes, valid, m, passes))
    remaining = set(candidates)

    while remaining and len(excluded) < cap:
        best_i, best_key = None, current_key
        for i in remaining:
            trial = {p: valid[p].copy() for p in passes}
            for p in passes:
                trial[p][i, :] = False
                trial[p][:, i] = False
            key = maximin_key(evaluate(blocks, pass_codes, trial, m, passes))
            if key > best_key:
                best_key, best_i = key, i
        if best_i is None:
            break
        for p in passes:
            valid[p][best_i, :] = False
            valid[p][:, best_i] = False
        excluded.add(best_i)
        remaining.discard(best_i)
        current_key = best_key
    return excluded, valid


def ordinal_consensus(per_pass_scores: dict[int, dict[str, float | None]], roster: list[str]) -> tuple[dict, dict]:
    """per_pass_scores[p] for p in PASSES; p[name] = tier*10 + within, or
    None (the flagger/ranker prompt's "unknown" bucket caught them that
    pass — see system_prompt_ranker.j2's HARD RULE).

    Returns (per_character, quality), same shape as flag_consensus():
      per_character[name] = {"block_index", "block_size", "consensus_z",
                              "tier", "sub_position", "pass_range"} for
                              every name that survived both the pre-filter
                              and the post-search greedy exclusion pass;
                              None for anyone excluded either way — gap>1,
                              one-sided-unknown, or a gap-1 character the
                              search couldn't reconcile without hurting the
                              block structure. All three land in the same
                              place a human already knows how to recover
                              from: Observe Beauty's "removed" zone.
      quality: kappa_raw_12 (== min_kappa here, no fitted 3rd pass to
      distinguish them from, matching flag_consensus's convention) —
      computed on the surviving population, so it reflects what was
      actually kept, not a number that ignores its own exclusions. n_blocks,
      block_sizes, n_high_disagreement (pre-filter drop count),
      n_auto_removed (post-search greedy exclusion count).
    """
    tiers = {p: {name: _tier_or_unknown(per_pass_scores[p].get(name)) for name in roster} for p in PASSES}

    search_names: list[str] = []
    per_character: dict[str, dict | None] = {}
    n_dropped = 0
    for name in roster:
        t1, t2 = tiers[1][name], tiers[2][name]
        if (t1 == _UNKNOWN) != (t2 == _UNKNOWN):  # exactly one side unknown -> real contradiction
            per_character[name] = None
            n_dropped += 1
        elif t1 != _UNKNOWN and abs(t1 - t2) > 1:  # both real, too far apart to reconcile
            per_character[name] = None
            n_dropped += 1
        else:
            search_names.append(name)

    empty_quality = {
        "kappa_raw_12": None, "min_kappa": None, "n_blocks": 0, "block_sizes": [],
        "n_high_disagreement": n_dropped, "n_auto_removed": 0,
    }
    if not search_names:
        return per_character, empty_quality

    idx_of = {n: i for i, n in enumerate(search_names)}
    m = len(search_names)
    tiers_by_idx = {p: {idx_of[n]: tiers[p][n] for n in search_names} for p in PASSES}
    maj_tier = {i: majority_tier(i, tiers_by_idx, PASSES) for i in range(m)}

    # Borda score: average raw score across passes when both real; the
    # agreed-unknown group needs its own numeric anchor to sort by (there's
    # no raw score to average) — a fixed value below every real score
    # (tier*10+within >= 0) puts them at the very bottom deterministically.
    borda_score = {}
    for n in search_names:
        i = idx_of[n]
        if tiers_by_idx[1][i] == _UNKNOWN:
            borda_score[i] = _UNKNOWN * 10
        else:
            borda_score[i] = (per_pass_scores[1][n] + per_pass_scores[2][n]) / 2.0

    pass_codes, pass_valid = {}, {}
    for p in PASSES:
        arr = np.array([tiers_by_idx[p][i] for i in range(m)], dtype=np.float64)
        pass_codes[p], pass_valid[p] = sign_matrix(arr)

    best_blocks, best_key = None, None
    for restart in range(RESTARTS):
        rng = random.Random(restart) if restart > 0 else None
        init_blocks = borda_init(list(range(m)), borda_score, tiers_by_idx, maj_tier, PASSES, rng)
        final_blocks = hill_climb(init_blocks, pass_codes, pass_valid, m, maj_tier, PASSES)
        key = maximin_key(evaluate(final_blocks, pass_codes, pass_valid, m, PASSES))
        if best_key is None or key > best_key:
            best_blocks, best_key = final_blocks, key

    # Exclusion candidates: only pass_range==1 (real tiers, one apart) —
    # never gap-0 confident placements, never the agreed-unknown block.
    exclusion_candidates = {
        idx_of[n] for n in search_names
        if tiers[1][n] != _UNKNOWN and abs(tiers[1][n] - tiers[2][n]) == 1
    }
    excluded, final_valid = _greedy_exclude(best_blocks, pass_codes, pass_valid, m, PASSES, exclusion_candidates)
    for i in excluded:
        per_character[search_names[i]] = None
    best_blocks = [[e for e in block if e not in excluded] for block in best_blocks]
    best_blocks = [block for block in best_blocks if block]

    kappas = evaluate(best_blocks, pass_codes, final_valid, m, PASSES)
    min_kappa = min((k for k in kappas if not math.isnan(k)), default=None)
    block_sizes = [len(b) for b in best_blocks]
    survivor_m = m - len(excluded)
    std = math.sqrt((survivor_m * survivor_m - 1) / 12) if survivor_m > 1 else 0.0

    avg_score = {
        n: (per_pass_scores[1][n] + per_pass_scores[2][n]) / 2.0 if tiers[1][n] != _UNKNOWN else n
        for n in search_names
    }

    cumulative = 0
    for b_idx, block in enumerate(best_blocks):
        size = len(block)
        midrank = cumulative + (size + 1) / 2.0
        z = (midrank - (survivor_m + 1) / 2.0) / std if std > 0 else 0.0
        tier = maj_tier[block[0]]
        if tier is None:  # no majority (gap-1 members of this block) -> best-effort rounded compromise
            vals = [tiers_by_idx[p][block[0]] for p in PASSES]
            tier = round(sum(vals) / len(vals))
        ranked = sorted((search_names[e] for e in block), key=lambda n: avg_score[n])
        for rank, name in enumerate(ranked):
            i = idx_of[name]
            per_character[name] = {
                "block_index": b_idx,
                "block_size": size,
                "consensus_z": round(z, 4),
                "pass_range": abs(tiers_by_idx[1][i] - tiers_by_idx[2][i]) if tiers_by_idx[1][i] != _UNKNOWN else 0,
                "tier": tier,
                "sub_position": round(tier + (rank + 1) / (size + 1), 4),
            }
        cumulative += size

    quality = {
        "kappa_raw_12": None if min_kappa is None else round(min_kappa, 4),
        "min_kappa": None if min_kappa is None else round(min_kappa, 4),
        "n_blocks": len(best_blocks),
        "block_sizes": sorted(block_sizes),
        "n_high_disagreement": n_dropped,
        "n_auto_removed": len(excluded),
    }
    return per_character, quality


def merge_ordinal_consensus(per_pass, roster, ordinals) -> tuple[dict, dict]:
    """Drop-in analog of flag_consensus.merge_flag_consensus, scoped to ordinals."""
    merged = {name: {} for name in roster}
    quality = {}
    for param in ordinals:
        per_pass_scores = {p: per_pass[p][param] for p in PASSES}
        per_character, param_quality = ordinal_consensus(per_pass_scores, roster)
        quality[param] = param_quality
        for name in roster:
            merged[name][param] = per_character[name]
    return merged, quality


# ── self-test ───────────────────────────────────────────────────────────────

def _scores(tier_map):
    return {n: (t * 10 + 0.5 if t is not None else None) for n, t in tier_map.items()}


def _selftest():
    names = [f"c{i}" for i in range(20)]

    # test 1: perfect agreement across a real tier spread -> everyone placed,
    # nobody dropped, nobody auto-removed.
    tiers = {n: i % 5 for i, n in enumerate(names)}
    per_pass = {1: _scores(tiers), 2: _scores(tiers)}
    per_character, quality = ordinal_consensus(per_pass, names)
    assert all(per_character[n] is not None for n in names), per_character
    assert quality["n_high_disagreement"] == 0 and quality["n_auto_removed"] == 0, quality
    print(f"test 1 (perfect agreement -> everyone placed, nothing removed): PASS  {quality}")

    # test 2: a character 3 tiers apart between passes -> auto-excluded
    # (None), no search, no confirmation needed.
    tiers2 = dict(tiers)
    per_pass2 = {1: _scores(tiers2), 2: _scores(tiers2)}
    per_pass2[1]["c0"] = 0 * 10 + 0.5
    per_pass2[2]["c0"] = 3 * 10 + 0.5  # gap = 3
    per_character, quality = ordinal_consensus(per_pass2, names)
    assert per_character["c0"] is None, per_character
    assert quality["n_high_disagreement"] == 1, quality
    print(f"test 2 (gap>1 -> auto-excluded, not sent to search): PASS  {quality}")

    # test 3: agreed-unknown (both passes say "unknown") gets its own
    # bottom-tier placement, not dropped; one-sided-unknown (real contradiction)
    # stays dropped.
    tiers3 = dict(tiers)
    per_pass3 = {1: _scores(tiers3), 2: _scores(tiers3)}
    per_pass3[1]["c0"] = None
    per_pass3[2]["c0"] = None  # agreed-unknown
    per_pass3[1]["c1"] = None  # one-sided-unknown vs c1's real tier in pass 2
    per_character, quality = ordinal_consensus(per_pass3, names)
    assert per_character["c0"] is not None and per_character["c0"]["tier"] == _UNKNOWN, per_character
    assert per_character["c1"] is None, per_character
    print(f"test 3 (agreed-unknown placed at bottom tier; one-sided stays dropped): PASS  {quality}")

    # test 4: a character 1 tier apart, alone at the seam between two large
    # real blocks — confirms the search reconciles this into its own small
    # block when that's better than removal, and the block structure does
    # NOT collapse into one giant block just because a search ran.
    tiers4 = {n: (0 if i < 10 else 1) for i, n in enumerate(names)}
    tiers4_noisy = dict(tiers4)
    tiers4_noisy["c9"] = 1  # only c9 disagrees, by exactly 1 tier, alone
    per_pass4 = {1: _scores(tiers4), 2: _scores(tiers4_noisy)}
    per_character, quality = ordinal_consensus(per_pass4, names)
    assert per_character["c9"] is not None, per_character
    assert quality["n_blocks"] >= 2, quality  # must not collapse to one block
    print(f"test 4 (block structure survives a lone gap-1 outlier, not collapsed): PASS  {quality}")

    # test 5: removal cap — a roster where EVERY character disagrees by
    # exactly 1 tier must not get everyone auto-removed; the 15% cap must
    # hold regardless of how much that would "help" kappa.
    tiers5 = {n: i % 4 for i, n in enumerate(names)}
    tiers5_noisy = {n: t + 1 for n, t in tiers5.items()}
    per_pass5 = {1: _scores(tiers5), 2: _scores(tiers5_noisy)}
    per_character, quality = ordinal_consensus(per_pass5, names)
    assert quality["n_auto_removed"] <= round(len(names) * _MAX_REMOVAL_FRACTION), quality
    n_none = sum(1 for n in names if per_character[n] is None)
    assert n_none == quality["n_auto_removed"], (n_none, quality)
    print(f"test 5 (removal cap holds even when everyone disagrees by 1 tier): PASS  {quality}")


if __name__ == "__main__":
    _selftest()
    print("\nall self-tests passed")
