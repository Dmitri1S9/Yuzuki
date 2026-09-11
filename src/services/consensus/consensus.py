"""Consensus weak-order ranker for a single ordinal parameter.

Takes 3 independent passes (sorted list + tier markers, already reduced to
per-character scores by stage2_features.scores_from_result) and produces one
weak order: characters grouped into ordered blocks, equal within a block.

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
"""
import math
import random
from collections import Counter

import numpy as np

PASSES = (1, 2, 3)
CATS = (-1, 0, 1)
RESTARTS = 5
WINDOW = 5
NEG_INF = float("-inf")


# ── metric ──────────────────────────────────────────────────────────────────

def sign_matrix(vec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """vec: float array, NaN = missing. Returns (codes in {-1,0,1}, valid mask)."""
    diff = vec[:, None] - vec[None, :]
    valid = ~np.isnan(diff)
    np.fill_diagonal(valid, False)
    codes = np.sign(np.nan_to_num(diff, nan=0.0)).astype(np.int8)
    return codes, valid


def cohen_kappa_masked(codes_a: np.ndarray, codes_b: np.ndarray, valid: np.ndarray) -> float:
    a, b = codes_a[valid], codes_b[valid]
    n = a.size
    if n == 0:
        return float("nan")
    conf = np.zeros((3, 3), dtype=np.float64)
    for i, cv in enumerate(CATS):
        am = a == cv
        if not am.any():
            continue
        for j, dv in enumerate(CATS):
            conf[i, j] = np.sum(am & (b == dv))
    po = np.trace(conf) / n
    row, col = conf.sum(axis=1), conf.sum(axis=0)
    pe = np.sum(row * col) / (n * n)
    if abs(1.0 - pe) < 1e-10:
        return float("nan")
    return float((po - pe) / (1.0 - pe))


def block_vector(blocks: list[list[int]], m: int) -> np.ndarray:
    vec = np.empty(m, dtype=np.int32)
    for b_idx, block in enumerate(blocks):
        for i in block:
            vec[i] = b_idx
    return vec


def evaluate(blocks: list[list[int]], pass_codes: dict, pass_valid: dict, m: int) -> tuple[float, float, float]:
    bvec = block_vector(blocks, m)
    codes_r, _ = sign_matrix(bvec.astype(np.float64))
    return tuple(cohen_kappa_masked(pass_codes[p], codes_r, pass_valid[p]) for p in PASSES)


def maximin_key(kappas: tuple[float, float, float]) -> tuple[float, float, float]:
    vals = [NEG_INF if math.isnan(k) else k for k in kappas]
    return tuple(sorted(vals))


# ── majority tier — hard floor under the block search ───────────────────────
# The kappa objective alone will happily fuse characters from genuinely
# different tiers into one block if that raises pairwise agreement (observed
# on authority_scope: one 27-member block spanning raw tiers 0, 1 and 2).
# Blocks may freely split a shared tier into finer sub-blocks (that can only
# help or be neutral to kappa, per the tier-level metric), but must never
# merge two characters whose majority tier (>=2-of-3-passes vote, same rule
# merge_cell used) is defined and differs. A character with no majority tier
# (1/1/1 disagreement, or <2 passes) is unconstrained — it carries no vote to
# conflict with.

def majority_tier(idx: int, tiers_by_idx: dict) -> int | None:
    values = [tiers_by_idx[p][idx] for p in PASSES if idx in tiers_by_idx[p]]
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


# ── init ────────────────────────────────────────────────────────────────────

def borda_init(names: list[int], borda_score: dict, tiers: dict, maj_tier: dict,
                rng: random.Random | None = None) -> list[list[int]]:
    if rng is not None:
        noisy = {n: borda_score[n] + rng.gauss(0, 0.5) for n in names}
        order = sorted(names, key=lambda n: noisy[n])
    else:
        order = sorted(names, key=lambda n: borda_score[n])

    blocks: list[list[int]] = [[order[0]]]
    current_tier = maj_tier[order[0]]
    for a, b in zip(order, order[1:]):
        distinct_votes = sum(
            1 for p in PASSES
            if tiers[p].get(a) is not None and tiers[p].get(b) is not None and tiers[p][a] != tiers[p][b]
        )
        b_tier = maj_tier[b]
        if distinct_votes >= 2 or not tiers_compatible(current_tier, b_tier):
            blocks.append([b])
            current_tier = b_tier
        else:
            blocks[-1].append(b)
            if current_tier is None:
                current_tier = b_tier
    return blocks


# ── moves ───────────────────────────────────────────────────────────────────

def gen_moves(blocks: list[list[int]], positions: dict):
    k = len(blocks)
    for i in range(k - 1):
        yield ("merge", i)
    for i, block in enumerate(blocks):
        for split_at in range(1, len(block)):
            yield ("split", i, split_at)
    for i, block in enumerate(blocks):
        for elem in block:
            if i > 0:
                yield ("transfer_neighbor", i, elem, i - 1)
            if i < k - 1:
                yield ("transfer_neighbor", i, elem, i + 1)
    for i in range(k - 1):
        yield ("swap", i)
    for i, block in enumerate(blocks):
        for elem in block:
            p = positions[elem]
            targets = {
                j for j, other in enumerate(blocks)
                if j != i and any(abs(positions[o] - p) <= WINDOW for o in other)
            }
            for j in targets:
                yield ("window_transfer", i, elem, j)


def apply_move(blocks: list[list[int]], move, maj_tier: dict) -> list[list[int]] | None:
    blocks = [list(b) for b in blocks]
    kind = move[0]

    if kind == "merge":
        i = move[1]
        if not tiers_compatible(block_tier(blocks[i], maj_tier), block_tier(blocks[i + 1], maj_tier)):
            return None
        blocks[i] = blocks[i] + blocks[i + 1]
        del blocks[i + 1]

    elif kind == "split":
        _, i, at = move
        block = blocks[i]
        blocks[i:i + 1] = [block[:at], block[at:]]

    elif kind in ("transfer_neighbor", "window_transfer"):
        _, i, elem, j = move
        if len(blocks[i]) <= 1:
            return None  # would empty the source block — not a valid move
        if not tiers_compatible(maj_tier[elem], block_tier(blocks[j], maj_tier)):
            return None
        blocks[i].remove(elem)
        blocks[j].append(elem)
        if not blocks[i]:
            return None

    elif kind == "swap":
        i = move[1]
        blocks[i], blocks[i + 1] = blocks[i + 1], blocks[i]

    return [b for b in blocks if b]


def hill_climb(blocks: list[list[int]], pass_codes: dict, pass_valid: dict, m: int, maj_tier: dict) -> list[list[int]]:
    current_key = maximin_key(evaluate(blocks, pass_codes, pass_valid, m))
    improved = True
    while improved:
        improved = False
        positions = {elem: pos for pos, elem in enumerate(e for b in blocks for e in b)}
        for move in gen_moves(blocks, positions):
            candidate = apply_move(blocks, move, maj_tier)
            if candidate is None or len(candidate) < 1:
                continue
            cand_key = maximin_key(evaluate(candidate, pass_codes, pass_valid, m))
            if cand_key > current_key:
                blocks, current_key = candidate, cand_key
                improved = True
                break
    return blocks


# ── top level ─────────────────────────────────────────────────────────────

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
    maj_tier = {i: majority_tier(i, tiers_by_idx) for i in range(m)}

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
        init_blocks = borda_init(indices, borda_score, tiers_by_idx, maj_tier, rng)
        final_blocks = hill_climb(init_blocks, pass_codes, pass_valid, m, maj_tier)
        key = maximin_key(evaluate(final_blocks, pass_codes, pass_valid, m))
        if best_key is None or key > best_key:
            best_blocks, best_key = final_blocks, key

    kappas = evaluate(best_blocks, pass_codes, pass_valid, m)
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
            per_character[name] = {
                "block_index": b_idx,
                "block_size": size,
                "consensus_z": round(z, 4),
                "pass_range": max(available_tiers) - min(available_tiers),
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
    k_one = evaluate(one_block, pass_codes, pass_valid, m)
    assert all(abs(k) < 1e-9 for k in k_one), f"one-block kappa should be 0, got {k_one}"
    print(f"test 1 (one block -> kappa 0): PASS  {k_one}")

    # test 2: true block structure beats a strict total order (no ties) on
    # data that actually contains tier-equalities.
    true_blocks = [[idx_of["a"], idx_of["b"]], [idx_of["c"], idx_of["d"]], [idx_of["e"], idx_of["f"]]]
    strict_order = [[i] for i in range(m)]  # every element its own block
    k_true = evaluate(true_blocks, pass_codes, pass_valid, m)
    k_strict = evaluate(strict_order, pass_codes, pass_valid, m)
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
    maj = {i: majority_tier(i, tiers_by_idx) for i in range(m)}
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
