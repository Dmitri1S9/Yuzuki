"""Consensus for a single flag parameter — 1 pass, fixed 3-tier ranking
(T1=doesn't have it, T2=unsure, T3=clearly has it; see
system_prompt_flag_rank.j2). Back from a brief plain-list-membership design
(2026-09-23, user's call after live review): a flat yes/no list gave no way
to tell a borderline match from a strong one, so a flag with only ~1% real
matches looked the same as a cast full of near-identical entries — no
texture, no way to tell "barely qualifies" from "obviously qualifies."
Reuses collection.py's scores_from_result/parse_sorted/compute_score
unchanged (the same T1..Tn marker parsing rank() already does for
ordinals) — a flag's raw score is `tier*10 + within_tier_fraction`, same
encoding, just always exactly 3 possible tiers. Single rater (1 pass), so
still no kappa to compute — this module just reshapes the one ranking into
the block/tier output shape everything downstream (output assembly, DCS's
report, Observe Beauty) already expects.
"""
import math

FLAG_PASSES = (1,)


def flag_consensus(per_pass_scores: dict[int, dict[str, float | None]], roster: list[str]) -> tuple[dict, dict]:
    """per_pass_scores[p] for p in FLAG_PASSES (just pass 1); p[name] =
    tier*10+within (real placement) or absent/None (either collection.py's
    "unknown" list — the model didn't recognize the character at all — or
    a defensive missing-data case like a stale raw_passes cache entry).
    Both read the same way here: not placed.

    Returns (per_character, quality), same shape flag_consensus always
    produced so downstream code needs no branch:
      per_character[name] = {"block_index", "block_size", "consensus_z",
                              "tier" (0, 1, or 2), "sub_position",
                              "pass_range"} for every name with a real
                              placement; None for unknown/missing.
      quality: no kappa fields (one rater, nothing to measure agreement
      against) — n_blocks, block_sizes only, kept alongside null kappa
      fields for schema stability.
    """
    p = FLAG_PASSES[0]
    scores = per_pass_scores[p]
    # compute_score's raw segment index is 1-based in practice, not 0-based:
    # with 3 markers (T1/T2/T3) the model always opens "sorted" with T1
    # (system_prompt_flag_rank.j2's own format example puts it first, and
    # nothing meaningfully belongs "before" T1 = "doesn't have it" at all),
    # so parse_sorted's segment 0 (before the first marker) stays empty and
    # every real name lands in segment 1 (T1) through segment 3 (after T3,
    # i.e. T3 itself). Confirmed live: a real response placed T1-tier names
    # at raw index 1, not 0. Shifted down by 1 and clamped to [0, 2] so the
    # output "tier" is what the rest of this module (and the frontend's
    # T${tier+1} labeling) actually expects: 0=T1, 1=T2, 2=T3. The clamp
    # also folds the rare "before T1"/"after T3" edge cases into T1/T3
    # respectively, matching the prompt's own rule 2 ("placed before T1 is
    # treated the same as T1").
    tiers = {name: min(2, max(0, int(scores[name] // 10) - 1)) for name in roster if scores.get(name) is not None}
    per_character: dict[str, dict | None] = {name: None for name in roster}

    empty_quality = {
        "kappa_raw_12": None, "min_kappa": None, "kappa_raw_min": None,
        "n_blocks": 0, "block_sizes": [], "n_high_disagreement": 0,
    }
    if not tiers:
        return per_character, empty_quality

    # Up to 3 blocks (T1/T2/T3 -> tier 0/1/2) — not every tier necessarily
    # has a member (e.g. nobody landed on "unsure"), so this builds however
    # many are actually present, same pattern ordinal_consensus.py uses.
    # Within a tier, ordered by the real score (the model's own within-tier
    # sorting-axis placement), not alphabetically — this is the "хоть
    # какое-то сравнение" the plain list-membership design lost entirely.
    placed = sorted(tiers, key=lambda n: scores[n])
    blocks: list[list[str]] = [[placed[0]]]
    for a, b in zip(placed, placed[1:]):
        if tiers[a] == tiers[b]:
            blocks[-1].append(b)
        else:
            blocks.append([b])

    m = len(placed)
    # Normalized-rank z-score, same formula ordinal_consensus.py uses (std
    # = stdev of a discrete uniform 1..m rank distribution) — without this,
    # z blows out to roughly +-m/2 instead of a bounded ~+-1.7 scale, which
    # broke Observe Beauty's bell-curve display (fixed 2026-09-23, confirmed
    # live on MHA's is_strategist collection).
    std = math.sqrt((m * m - 1) / 12) if m > 1 else 0.0
    cumulative = 0
    for b_idx, block in enumerate(blocks):
        size = len(block)
        midrank = cumulative + (size + 1) / 2.0
        z = round((midrank - (m + 1) / 2.0) / std, 4) if std > 0 else 0.0
        tier = tiers[block[0]]
        for rank, name in enumerate(block):
            per_character[name] = {
                "block_index": b_idx,
                "block_size": size,
                "consensus_z": z,
                "pass_range": 0,
                "tier": tier,
                "sub_position": round(tier + (rank + 1) / (size + 1), 4),
            }
        cumulative += size

    quality = {
        "kappa_raw_12": None, "min_kappa": None, "kappa_raw_min": None,
        "n_blocks": len(blocks), "block_sizes": sorted(len(b) for b in blocks),
        "n_high_disagreement": 0,
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
    """tier_map: {name: intended output tier (0/1/2)} -> {name: raw_segment
    *10 + within}, matching what compute_score() actually produces from a
    real "sorted" response — raw_segment = tier+1 (parse_sorted's segment 0
    stays empty in practice since T1 is always the first token; see
    flag_consensus's own comment on the -1 shift this exercises end to
    end, not just the already-shifted output)."""
    by_tier: dict[int, list[str]] = {}
    for n, t in tier_map.items():
        by_tier.setdefault(t, []).append(n)
    out = {}
    for t, names in by_tier.items():
        raw_segment = t + 1
        for i, n in enumerate(names):
            out[n] = round(raw_segment * 10 + (i + 1) / (len(names) + 1), 4)
    return out


def _selftest():
    names = [f"c{i}" for i in range(10)]

    # test 1: a real 3-way split -> three blocks, correct tiers, within-tier
    # order follows the given score (not alphabetical).
    tier_map = {n: (i % 3) for i, n in enumerate(names)}
    per_pass = {1: _scores(tier_map)}
    per_character, quality = flag_consensus(per_pass, names)
    assert all(per_character[n] is not None for n in names), per_character
    assert quality["n_blocks"] == 3, quality
    for n in names:
        assert per_character[n]["tier"] == tier_map[n], (n, per_character[n], tier_map[n])
    print(f"test 1 (3-way split -> three blocks, correct tiers): PASS  {quality}")

    # test 2: nobody matches (everyone T1) -> one block, tier 0.
    per_pass = {1: _scores({n: 0 for n in names})}
    per_character, quality = flag_consensus(per_pass, names)
    assert quality["n_blocks"] == 1 and quality["block_sizes"] == [10], quality
    assert all(per_character[n]["tier"] == 0 for n in names), per_character
    print(f"test 2 (everyone T1 -> one block, tier 0): PASS  {quality}")

    # test 3: everybody clearly has it (T3) -> one block, tier 2.
    per_pass = {1: _scores({n: 2 for n in names})}
    per_character, quality = flag_consensus(per_pass, names)
    assert quality["n_blocks"] == 1 and quality["block_sizes"] == [10], quality
    assert all(per_character[n]["tier"] == 2 for n in names), per_character
    print(f"test 3 (everyone T3 -> one block, tier 2): PASS  {quality}")

    # test 4: missing from the response entirely (client.flag()'s "unknown"
    # list, or a defensive stale-cache gap) -> not placed, everyone else
    # unaffected.
    tier_map4 = dict(tier_map)
    per_pass = {1: _scores(tier_map4)}
    del per_pass[1]["c0"]
    per_character, quality = flag_consensus(per_pass, names)
    assert per_character["c0"] is None, per_character
    assert all(per_character[n] is not None for n in names if n != "c0"), per_character
    print(f"test 4 (unknown/missing -> not placed, everyone else unaffected): PASS  {quality}")

    # test 5: nobody has any data at all -> empty result, not an error.
    per_pass = {1: {}}
    per_character, quality = flag_consensus(per_pass, names)
    assert all(per_character[n] is None for n in names), per_character
    assert quality["n_blocks"] == 0, quality
    print(f"test 5 (no data at all -> empty result, no crash): PASS  {quality}")


if __name__ == "__main__":
    _selftest()
    print("\nall self-tests passed")
