"""Consensus for a single flag parameter — 2 passes, not 3, and a
deliberately different algorithm from consensus.py's ordinal path, not a
smaller version of it.

Ordinals (consensus.py) search for the best block structure across 3 passes
via maximin-kappa hill-climbing — worth the cost because ordinals keep their
3-pass budget, and they measure agreement on pairwise ORDER (sign_matrix)
since a rank has too many distinct positions for exact-position agreement to
mean much. Flags move to 2 passes specifically to cut cost, so spending a
combinatorial search on top would give away the saving; there is also no
majority (2-of-3) vote possible with only 2 raters. Flags also have very
few tiers (typically 2-3), where exact tier agreement is both meaningful and
simple, unlike a fine-grained rank.

Algorithm: build blocks directly from where the 2 passes already agree —
nobody is excluded from the result for disagreeing. Kappa is reported as a
quality signal, not used to drive removal: an earlier version repeatedly
dropped whichever character's two passes disagreed most until kappa
cleared a target, but that silently deleted real characters from a human
reviewer's view exactly the way the roster's old hard pass-count filter
did (same fix, same reasoning — a human decides who's unreliable, not the
algorithm). A character whose passes land in different tiers still gets a
best-effort placement (tier = round of the average, pass_range = the gap
between the two passes) instead of being erased; pass_range is the
per-character signal a reviewer highlights instead of a silent drop.

The flag prompt itself (user_prompt_flagger.j2) gives the model a third
option beyond the tiered "sorted" list: "unknown", for a character it
can't confidently place at all — every character is required to land in
one of the two, never silently missing. A character marked unknown in
BOTH passes is real agreement ("neither pass could place them"), not
absence of data — it gets its own bottom-most tier (below every real T0
placement) via the _UNKNOWN sentinel, same as any other agreed tier,
rather than being erased. A character is only left out of the result
(None) when the two passes actively contradict each other about it —
one placed it on the real tier scale, the other marked it unknown —
genuine disagreement about whether it's even placeable, which is exactly
the "worst case: recommend dropping this one" scenario a human reviewer
should see flagged, not something to average away.

Why tier agreement, not sign_matrix's pairwise order (tried first, rejected
on real data): sign_matrix only measures relative order, which goes blind
once nobody is left to compare within a pass. Confirmed live on flag
"ruthless" (MHA Sports Festival): after removing the clearest outliers, the
26 remaining characters ended up tier 0 in every pass-1 read and tier 2 in
every pass-2 read — total, glaring disagreement about the whole group — yet
sign_matrix kappa reported NaN ("undefined"), because with everyone tied
within each pass there was no pairwise order left to disagree on. Direct
tier-agreement kappa sees this immediately (0% of characters land in the
same category) and correctly reports a very low kappa instead of hiding the
problem behind "undefined".
"""
import math

import numpy as np

FLAG_PASSES = (1, 2)
FLAG_HIGH_DISAGREEMENT_GAP = 1  # pass_range strictly above this marks a
                                  # character as high-disagreement in the
                                  # quality summary — informational only,
                                  # never excludes anyone from the result.
_UNKNOWN = -1  # a character the prompt's "unknown" bucket caught in a pass —
               # sorts below every real tier (T0's own "clearly does not
               # have it" is tier 0), never collides with a real tier value.


def tier_kappa(tiers_a: list[int], tiers_b: list[int]) -> float:
    """Cohen's kappa for 2 raters classifying the same items into discrete
    tiers — direct category agreement. NaN when the raters never disagree
    AND never see more than one shared category between them (kappa is
    mathematically undefined at zero variance — e.g. every character is
    tier 0 in both passes; genuinely perfect agreement, not a failure)."""
    n = len(tiers_a)
    cats = sorted(set(tiers_a) | set(tiers_b))
    if n == 0 or len(cats) < 2:
        return float("nan")
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    conf = np.zeros((k, k))
    for a, b in zip(tiers_a, tiers_b):
        conf[idx[a], idx[b]] += 1
    po = np.trace(conf) / n
    row, col = conf.sum(axis=1), conf.sum(axis=0)
    pe = np.sum(row * col) / (n * n)
    if abs(1.0 - pe) < 1e-10:
        return float("nan")
    return float((po - pe) / (1.0 - pe))


def _build_blocks(alive: list[str], tiers1: dict, tiers2: dict) -> list[list[str]]:
    """Adjacent survivors (sorted by average tier) share a block only when
    both passes agree on their tier exactly — no hill-climbing to merge
    further, unlike the ordinal path; agreement is already the removal
    criterion, so nothing here needs to chase kappa."""
    order = sorted(alive, key=lambda n: (tiers1[n] + tiers2[n]) / 2)
    blocks = [[order[0]]]
    for a, b in zip(order, order[1:]):
        if tiers1[a] == tiers1[b] and tiers2[a] == tiers2[b]:
            blocks[-1].append(b)
        else:
            blocks.append([b])
    return blocks


def flag_consensus(per_pass_scores: dict[int, dict[str, float | None]], roster: list[str]) -> tuple[dict, dict]:
    """per_pass_scores[p] for p in FLAG_PASSES; p[name] = tier*10 + within, or None.

    Returns (per_character, quality) in the same shape as consensus_rank so
    downstream code (output assembly, DCS's kappa report) needs no
    flag-specific branch:
      per_character[name] = {"block_index", "block_size", "consensus_z",
                              "tier", "sub_position", "pass_range"} for
                              every name present in both passes — None only
                              when a name is missing from one of the 2
                              passes entirely, never for disagreeing.
                              pass_range is the reviewer-facing signal: 0
                              means the passes agreed exactly, >0 means
                              they didn't (see FLAG_HIGH_DISAGREEMENT_GAP).
      quality has min_kappa / kappa_raw_min (identical here — there is no
      fitted 3rd sequence to distinguish them from, unlike the ordinal
      path) reported for awareness only, n_blocks, block_sizes, and
      n_high_disagreement — how many characters' pass_range exceeded the
      threshold, again informational, not an exclusion.
    """
    tiers = {p: {} for p in FLAG_PASSES}
    for p in FLAG_PASSES:
        for name in roster:
            score = per_pass_scores[p].get(name)
            tiers[p][name] = int(score // 10) if score is not None else _UNKNOWN

    # Eligible: both passes agree on placeability — either both gave a real
    # tier, or both marked the character unknown. Excluded only when exactly
    # one pass could place it and the other couldn't — a real contradiction,
    # not just fine-grained tier disagreement (which _build_blocks/the
    # round-average path already handles for two real tiers).
    elig_names = [n for n in roster if (tiers[1][n] == _UNKNOWN) == (tiers[2][n] == _UNKNOWN)]
    m = len(elig_names)
    per_character = {n: None for n in roster}
    empty_quality = {
        "kappa_raw_12": None, "min_kappa": None, "kappa_raw_min": None,
        "n_blocks": 0, "block_sizes": [], "n_high_disagreement": 0,
    }
    if m == 0:
        return per_character, empty_quality

    tiers1, tiers2 = tiers[1], tiers[2]
    alive = elig_names
    kappa = tier_kappa([tiers1[n] for n in alive], [tiers2[n] for n in alive])

    blocks = _build_blocks(alive, tiers1, tiers2)
    survivor_m = len(alive)
    block_sizes = [len(b) for b in blocks]
    std = math.sqrt((survivor_m * survivor_m - 1) / 12) if survivor_m > 1 else 0.0

    # Average raw score (tier*10+within, both passes) breaks ties within a
    # block for display/cross-universe purposes only — it never affects
    # which block a character is in, only their order inside one. 3 people
    # in one block become sub_position tier+0.25/0.50/0.75 (evenly spaced by
    # rank), not all stacked at the same point. The unknown-in-both block has
    # no real score to break ties with — ordered by name instead, just to be
    # deterministic (their relative order within that block carries no
    # meaning either way).
    avg_score = {
        n: (per_pass_scores[1][n] + per_pass_scores[2][n]) / 2.0 if tiers1[n] != _UNKNOWN else n
        for n in alive
    }

    cumulative = 0
    for b_idx, block in enumerate(blocks):
        size = len(block)
        midrank = cumulative + (size + 1) / 2.0
        z = (midrank - (survivor_m + 1) / 2.0) / std if std > 0 else 0.0
        # Every member of one block shares the same (tiers1, tiers2) pair by
        # construction (_build_blocks only merges on exact equality of both)
        # — round(average) when the two passes disagree on this block's own
        # tier, same tie-break _build_blocks' own sort key already uses.
        t1, t2 = tiers1[block[0]], tiers2[block[0]]
        tier = t1 if t1 == t2 else round((t1 + t2) / 2)
        ranked = sorted(block, key=lambda n: avg_score[n])
        for rank, name in enumerate(ranked):
            per_character[name] = {
                "block_index": b_idx,
                "block_size": size,
                "consensus_z": round(z, 4),
                "pass_range": abs(tiers1[name] - tiers2[name]),
                "tier": tier,
                "sub_position": round(tier + (rank + 1) / (size + 1), 4),
            }
        cumulative += size

    kappa_final = None if math.isnan(kappa) else round(kappa, 4)
    quality = {
        "kappa_raw_12": kappa_final,
        "min_kappa": kappa_final,
        "kappa_raw_min": kappa_final,
        "n_blocks": len(blocks),
        "block_sizes": sorted(block_sizes),
        "n_high_disagreement": sum(
            1 for n in alive if abs(tiers1[n] - tiers2[n]) > FLAG_HIGH_DISAGREEMENT_GAP
        ),
    }
    return per_character, quality


def merge_flag_consensus(per_pass, roster, flags) -> tuple[dict, dict]:
    """Drop-in analog of consensus.merge_consensus, scoped to flags only."""
    merged = {name: {} for name in roster}
    quality = {}
    for flag in flags:
        per_pass_scores = {p: per_pass[p][flag] for p in FLAG_PASSES}
        per_character, param_quality = flag_consensus(per_pass_scores, roster)
        quality[flag] = param_quality
        for name in roster:
            merged[name][flag] = per_character[name]
    return merged, quality


# ── self-test ───────────────────────────────────────────────────────────────

def _scores(tier_map):
    return {n: t * 10 + 0.5 for n, t in tier_map.items()}


def _selftest():
    names = [f"c{i}" for i in range(10)]

    # test 1: perfect agreement -> kappa 1.0, everyone placed.
    tiers = {n: i % 3 for i, n in enumerate(names)}
    per_pass = {1: _scores(tiers), 2: _scores(tiers)}
    per_character, quality = flag_consensus(per_pass, names)
    assert quality["min_kappa"] == 1.0, quality
    assert quality["n_high_disagreement"] == 0, quality
    assert all(per_character[n] is not None for n in names), per_character
    print(f"test 1 (perfect agreement -> kappa 1.0, everyone placed): PASS  {quality}")

    # test 2: one shared category only -> kappa undefined (None), not an error.
    tiers_flat = {n: 0 for n in names}
    per_pass = {1: _scores(tiers_flat), 2: _scores(tiers_flat)}
    per_character, quality = flag_consensus(per_pass, names)
    assert quality["min_kappa"] is None, quality
    assert all(per_character[n] is not None for n in names), per_character
    print(f"test 2 (unanimous single category -> kappa None, not 'bad'): PASS  {quality}")

    # test 3: the real bug this file was rewritten to fix. Two outliers
    # aside, pass 1 calls everyone tier 0 and pass 2 calls everyone tier 2 —
    # total disagreement about the whole group. A pairwise-ORDER metric
    # (sign_matrix, as tried first) sees zero variance within each pass and
    # reports kappa as undefined; direct tier agreement must instead report
    # a very low kappa, since po=0 with disjoint marginals.
    tiers1 = {n: 0 for n in names}
    tiers2 = {n: 2 for n in names}
    per_pass = {1: _scores(tiers1), 2: _scores(tiers2)}
    per_character, quality = flag_consensus(per_pass, names)
    assert quality["min_kappa"] is not None, "total disagreement must not report as undefined"
    assert quality["min_kappa"] < 0.5, quality
    assert all(per_character[n] is not None for n in names), per_character
    print(f"test 3 (total absolute disagreement surfaces as low kappa, not None): PASS  {quality}")

    # test 4: nobody gets dropped for disagreeing anymore — a couple of
    # noisy characters lower kappa and get flagged via pass_range/
    # n_high_disagreement, but still receive a best-effort placement, same
    # as everyone else.
    tiers_base = {n: i % 3 for i, n in enumerate(names)}
    tiers_noisy = dict(tiers_base)
    tiers_noisy["c0"] = (tiers_base["c0"] + 1) % 3
    tiers_noisy["c1"] = (tiers_base["c1"] + 1) % 3
    per_pass = {1: _scores(tiers_base), 2: _scores(tiers_noisy)}
    per_character, quality = flag_consensus(per_pass, names)
    assert all(per_character[n] is not None for n in names), per_character
    assert quality["n_high_disagreement"] == 0, quality  # gap is exactly 1, at the threshold, not above it
    assert per_character["c0"]["pass_range"] == 1 and per_character["c1"]["pass_range"] == 1, per_character
    assert all(per_character[n]["pass_range"] == 0 for n in names if n not in ("c0", "c1")), per_character
    print(f"test 4 (disagreeing characters flagged via pass_range, not dropped): PASS  {quality}")

    # test 5: the bug this fix addresses. c0/c1 land in "unknown" in BOTH
    # passes (score None both times, e.g. minor characters the model can't
    # confidently place at all) — real agreement, must get their own
    # placement, not be dropped. c2 is unknown in pass 1 only, a real tier
    # in pass 2 — a genuine contradiction, must still be dropped (None).
    per_pass_scores = {1: _scores({n: i % 3 for i, n in enumerate(names)}),
                        2: _scores({n: i % 3 for i, n in enumerate(names)})}
    per_pass_scores[1]["c0"] = None
    per_pass_scores[2]["c0"] = None
    per_pass_scores[1]["c1"] = None
    per_pass_scores[2]["c1"] = None
    per_pass_scores[1]["c2"] = None  # unknown in pass 1 only -> contradiction
    per_character, quality = flag_consensus(per_pass_scores, names)
    assert per_character["c0"] is not None and per_character["c1"] is not None, per_character
    assert per_character["c0"]["tier"] == per_character["c1"]["tier"] == _UNKNOWN, per_character
    assert per_character["c0"]["block_index"] == per_character["c1"]["block_index"], per_character
    assert per_character["c2"] is None, per_character
    assert all(per_character[n] is not None for n in names if n not in ("c2",)), per_character
    print(f"test 5 (unknown-in-both gets its own block; unknown-in-one stays dropped): PASS  {quality}")


if __name__ == "__main__":
    _selftest()
    print("\nall self-tests passed")
