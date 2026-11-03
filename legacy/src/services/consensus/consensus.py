"""Consensus weak-order ranker for a single ordinal parameter — the top
level. The metric (metric.py), the majority-tier floor (tiers.py), and the
block-structure search (search.py) each live in their own file; this file
is just consensus_rank() itself, positions_from_consensus() (used by the
live pipeline), and the self-test.

Takes 3 independent passes (sorted list + tier markers, already reduced to
per-character scores by features/collection.py's scores_from_result) and
produces one weak order: characters grouped into ordered blocks, equal
within a block.

Metric: each pass i is reduced to pairwise labels L_i(a,b) in {>, <, =},
"=" iff a and b share a TIER in pass i (tier level, not raw position).
A candidate weak order R is reduced to the same 3-valued labels via block
index. kappa_i = Cohen's kappa between L_i and L_R over all pairs where pass i
has data for both characters. Objective: maximize (kappa_1, kappa_2, kappa_3)
sorted ascending, compared lexicographically (maximin — pull up the worst
pairwise agreement first).

Missing data: a pass that lacks a tier for one side of a pair contributes no
vote for that pair to that pass's kappa (masked out), same masking the R-side
kappa_analysis.R already uses for NaN scores. This is an unavoidable
extension of the spec to real data, not a metric change.

R generates a 4th, fitted sequence, not collected independently — kappa_i
against it (min_kappa) is closer to a goodness-of-fit score than to
inter-rater reliability, and does not replace real-pass-vs-real-pass
agreement. consensus_rank() therefore also returns kappa_raw_12/13/23 and
kappa_raw_min, computed at the same tier level directly between the 3 real
passes with no R involved — a genuinely different number, kept alongside
min_kappa, not instead of it. (kappa_analysis.R's order_min is a third,
separate signal again — quartile-position categorization rather than tier
level — also unaffected and still computed on every run.)

NOTE: no longer called by the live pipeline (see features/pipeline.py's
own docstring) — both ordinals and flags now go through
consensus.flag_consensus's 2-pass algorithm instead. Left in place, still
tested, since positions_from_consensus (below) is shape-compatible with
flag_consensus's output and stays in real use.
"""
import math
import random

import numpy as np

from src.services.consensus.metric import cohen_kappa_masked, evaluate, maximin_key, sign_matrix
from src.services.consensus.search import borda_init, hill_climb
from src.services.consensus.tiers import majority_tier

PASSES = (1, 2, 3)
RESTARTS = 5


def consensus_rank(per_pass_scores: dict[int, dict[str, float | None]], roster: list[str]) -> tuple[dict, dict]:
    """per_pass_scores[p][name] = tier*10 + within, or None. One parameter.

    Returns (per_character, quality):
      per_character[name] = {"block_index", "block_size", "consensus_z",
                              "pass_range"} or None (fewer than 2 passes had data).
      quality = kappa_vs_pass1/2/3 + min_kappa (real passes vs the generated
      consensus order — goodness-of-fit of the block model), plus
      kappa_raw_12/13/23 + kappa_raw_min (real pass vs real pass, no
      generated data — genuine inter-rater agreement). The two families
      measure different things; neither replaces the other. n_blocks,
      block_sizes describe the consensus order itself.
    """
    tiers = {p: {} for p in PASSES}
    for p in PASSES:
        for name, score in per_pass_scores[p].items():
            if score is not None:
                tiers[p][name] = int(score // 10)

    elig_names = [n for n in roster if sum(1 for p in PASSES if n in tiers[p]) >= 2]
    m = len(elig_names)
    per_character = {n: None for n in roster}

    if m == 0:
        return per_character, {
            "kappa_vs_pass1": None, "kappa_vs_pass2": None, "kappa_vs_pass3": None,
            "min_kappa": None, "n_blocks": 0, "block_sizes": [],
            "kappa_raw_12": None, "kappa_raw_13": None, "kappa_raw_23": None, "kappa_raw_min": None,
        }

    idx_of = {n: i for i, n in enumerate(elig_names)}
    borda_score = {}
    for n in elig_names:
        vals = [per_pass_scores[p][n] for p in PASSES if per_pass_scores[p].get(n) is not None]
        borda_score[idx_of[n]] = sum(vals) / len(vals)
    tiers_by_idx = {p: {idx_of[n]: t for n, t in tiers[p].items() if n in idx_of} for p in PASSES}
    maj_tier = {i: majority_tier(i, tiers_by_idx, PASSES) for i in range(m)}

    pass_codes, pass_valid = {}, {}
    for p in PASSES:
        arr = np.full(m, np.nan)
        for i, val in tiers_by_idx[p].items():
            arr[i] = val
        pass_codes[p], pass_valid[p] = sign_matrix(arr)

    indices = list(range(m))
    best_blocks, best_key = None, None
    for restart in range(RESTARTS):
        rng = random.Random(restart) if restart > 0 else None
        init_blocks = borda_init(indices, borda_score, tiers_by_idx, maj_tier, PASSES, rng)
        final_blocks = hill_climb(init_blocks, pass_codes, pass_valid, m, maj_tier, PASSES)
        key = maximin_key(evaluate(final_blocks, pass_codes, pass_valid, m, PASSES))
        if best_key is None or key > best_key:
            best_blocks, best_key = final_blocks, key

    kappas = evaluate(best_blocks, pass_codes, pass_valid, m, PASSES)
    block_sizes = [len(b) for b in best_blocks]
    std = math.sqrt((m * m - 1) / 12) if m > 1 else 0.0

    cumulative = 0
    for b_idx, block in enumerate(best_blocks):
        size = len(block)
        midrank = cumulative + (size + 1) / 2.0  # 1-indexed
        z = (midrank - (m + 1) / 2.0) / std if std > 0 else 0.0
        for elem in block:
            name = elig_names[elem]
            available_tiers = [tiers[p][name] for p in PASSES if name in tiers[p]]
            # maj_tier[elem] (2-of-3 agreement) when it exists; otherwise the
            # rounded average of whatever tiers are available — a display
            # anchor for "Observe Beauty"'s fixed tier axis, not used by the
            # block search itself (that already ran, see hill_climb above).
            tier = maj_tier[elem]
            if tier is None:
                tier = round(sum(available_tiers) / len(available_tiers))
            per_character[name] = {
                "block_index": b_idx,
                "block_size": size,
                "consensus_z": round(z, 4),
                "pass_range": max(available_tiers) - min(available_tiers),
                "tier": tier,
            }
        cumulative += size

    min_kappa = min((k for k in kappas if not math.isnan(k)), default=None)

    # Raw pairwise kappa — real pass vs real pass, no generated 4th pass
    # involved. This is NOT the same measurement as min_kappa (which scores
    # agreement against a *fitted* consensus, closer to goodness-of-fit than
    # inter-rater reliability) and does not replace it; both are kept.
    raw_pairs = {(1, 2): None, (1, 3): None, (2, 3): None}
    for pa, pb in raw_pairs:
        valid_pair = pass_valid[pa] & pass_valid[pb]
        raw_pairs[(pa, pb)] = cohen_kappa_masked(pass_codes[pa], pass_codes[pb], valid_pair)
    raw_min = min((k for k in raw_pairs.values() if not math.isnan(k)), default=None)

    quality = {
        "kappa_vs_pass1": None if math.isnan(kappas[0]) else round(kappas[0], 4),
        "kappa_vs_pass2": None if math.isnan(kappas[1]) else round(kappas[1], 4),
        "kappa_vs_pass3": None if math.isnan(kappas[2]) else round(kappas[2], 4),
        "min_kappa": None if min_kappa is None else round(min_kappa, 4),
        "n_blocks": len(best_blocks),
        "block_sizes": sorted(block_sizes),
        "kappa_raw_12": None if math.isnan(raw_pairs[(1, 2)]) else round(raw_pairs[(1, 2)], 4),
        "kappa_raw_13": None if math.isnan(raw_pairs[(1, 3)]) else round(raw_pairs[(1, 3)], 4),
        "kappa_raw_23": None if math.isnan(raw_pairs[(2, 3)]) else round(raw_pairs[(2, 3)], 4),
        "kappa_raw_min": None if raw_min is None else round(raw_min, 4),
    }
    return per_character, quality


def positions_from_consensus(per_character: dict[str, dict | None]) -> dict[str, int | None]:
    """Flattens a consensus_rank/flag_consensus per_character result (keyed
    by block_index/consensus_z — both produce the same shape by design)
    into a single 0..N-1 integer position per character — the shape the
    `characters` table's ordinal/flag columns store (see
    CharacterRepository.save_feature_positions), and what a drag-to-reorder
    UI edits directly. None stays None (not placed by consensus — dropped
    for excess disagreement, or too little data). Ties within a block
    (same consensus_z) break by name for a stable, deterministic order —
    the block structure doesn't define a within-block order on its own."""
    ranked = sorted(
        (name for name, cell in per_character.items() if cell is not None),
        key=lambda name: (per_character[name]["consensus_z"], name),
    )
    positions: dict[str, int | None] = {name: None for name in per_character}
    for i, name in enumerate(ranked):
        positions[name] = i
    return positions


# ── self-test ───────────────────────────────────────────────────────────────

def _selftest():
    # 6 characters, tiers with real ties: {a,b} tier0, {c,d} tier1, {e,f} tier2.
    names = ["a", "b", "c", "d", "e", "f"]
    base_tiers = {"a": 0, "b": 0, "c": 1, "d": 1, "e": 2, "f": 2}

    def scores(tier_map):
        return {n: tier_map[n] * 10 + 0.5 for n in names}

    per_pass = {
        1: scores(base_tiers),
        2: scores(base_tiers),
        3: scores({"a": 0, "b": 0, "c": 1, "d": 1, "e": 2, "f": 1}),  # one pass noisy on f
    }

    tiers = {p: {n: int(s // 10) for n, s in per_pass[p].items()} for p in PASSES}
    idx_of = {n: i for i, n in enumerate(names)}
    tiers_by_idx = {p: {idx_of[n]: t for n, t in tiers[p].items()} for p in PASSES}
    m = len(names)
    pass_codes, pass_valid = {}, {}
    for p in PASSES:
        arr = np.array([tiers_by_idx[p][i] for i in range(m)], dtype=np.float64)
        pass_codes[p], pass_valid[p] = sign_matrix(arr)

    # test 1: everything in one block -> kappa == 0 for every pass.
    one_block = [list(range(m))]
    k_one = evaluate(one_block, pass_codes, pass_valid, m, PASSES)
    assert all(abs(k) < 1e-9 for k in k_one), f"one-block kappa should be 0, got {k_one}"
    print(f"test 1 (one block -> kappa 0): PASS  {k_one}")

    # test 2: true block structure beats a strict total order (no ties) on
    # data that actually contains tier-equalities.
    true_blocks = [[idx_of["a"], idx_of["b"]], [idx_of["c"], idx_of["d"]], [idx_of["e"], idx_of["f"]]]
    strict_order = [[i] for i in range(m)]  # every element its own block
    k_true = evaluate(true_blocks, pass_codes, pass_valid, m, PASSES)
    k_strict = evaluate(strict_order, pass_codes, pass_valid, m, PASSES)
    assert maximin_key(k_true) > maximin_key(k_strict), (
        f"true blocks should beat strict order: true={k_true} strict={k_strict}"
    )
    print(f"test 2 (true blocks beat strict order): PASS  true={k_true} strict={k_strict}")

    # sanity: the optimizer itself should recover (or match the quality of) the
    # true block structure from Borda init on this toy example.
    per_character, quality = consensus_rank(per_pass, names)
    print(f"optimizer result: n_blocks={quality['n_blocks']} min_kappa={quality['min_kappa']}")
    assert quality["min_kappa"] is not None and quality["min_kappa"] >= min(k_true), (
        "optimizer should find a solution at least as good as the true structure"
    )
    print("test 3 (optimizer matches/beats true structure): PASS")

    # test 4: no returned block may mix two different, both-defined majority
    # tiers — merging real tiers to chase kappa (seen live on authority_scope:
    # one block spanning raw tiers 0/1/2) must be impossible, not just unlikely.
    maj = {i: majority_tier(i, tiers_by_idx, PASSES) for i in range(m)}
    by_block = {}
    for name, cell in per_character.items():
        if cell is not None:
            by_block.setdefault(cell["block_index"], []).append(idx_of[name])
    for block in by_block.values():
        tiers_present = {maj[i] for i in block if maj[i] is not None}
        assert len(tiers_present) <= 1, f"block mixes majority tiers: {tiers_present}"
    print("test 4 (blocks never mix majority tiers): PASS")


if __name__ == "__main__":
    _selftest()
    print("\nall self-tests passed")
