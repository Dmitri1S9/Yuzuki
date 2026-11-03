"""Per-parameter merge: the current consensus_rank path, plus the legacy
per-cell vote kept only for --legacy-null comparison.
"""
from collections import Counter

from src.domain.parameters import is_flag
from src.services.collection.features.steps.constants import FLAG_PASSES, LEGACY_NULL, PASSES
from src.services.collection.features.steps.io import log_legacy_comparison
from src.services.consensus.consensus import consensus_rank


def merge_cell(scores):
    # Legacy per-cell vote, superseded by consensus_rank for every param
    # (ordinals and flags alike). Kept only for --legacy-null comparison.
    available = [s for s in scores if s is not None]
    if len(available) < 2:
        return {"value": None, "confidence": 0, "mean_within": None}
    tiers = [int(s // 10) for s in available]
    voted = [t for t, c in Counter(tiers).items() if c >= 2]
    if not voted:
        return {"value": None, "confidence": 0, "mean_within": None}
    tier = voted[0]
    spread = max(tiers) - min(tiers)
    if spread >= 2:
        return {"value": None, "confidence": 0, "mean_within": None}
    agreeing = [s for s in available if int(s // 10) == tier]
    return {
        "value": tier,
        "confidence": 2 if spread == 0 else 1,
        "mean_within": round(sum(s - tier * 10 for s in agreeing) / len(agreeing), 4),
    }


def merge(per_pass, roster, params):
    merged = {name: {} for name in roster}
    for param in params:
        passes = FLAG_PASSES if is_flag(param) else PASSES
        for name in roster:
            merged[name][param] = merge_cell([per_pass[p][param][name] for p in passes])
    return merged


def merge_consensus(per_pass, roster, params):
    merged = {name: {} for name in roster}
    quality = {}
    for param in params:
        per_pass_scores = {p: per_pass[p][param] for p in PASSES}
        per_character, param_quality = consensus_rank(per_pass_scores, roster)
        quality[param] = param_quality
        for name in roster:
            merged[name][param] = per_character[name]
    return merged, quality


def compute_null_share(merged, collect_roster, params):
    if not collect_roster:
        return {param: None for param in params}
    return {
        param: round(sum(1 for n in collect_roster if merged[n][param] is None) / len(collect_roster), 3)
        for param in params
    }


def apply_low_info_mask(merged, roster, low_info_set):
    return {name: (None if name in low_info_set else merged[name]) for name in roster}


def maybe_log_legacy_comparison(per_pass, roster, params, merged, quality) -> None:
    """Real branch: only runs the old per-cell-vote path (superseded by
    flag_consensus for everyone, see main.py's docstring) when explicitly
    asked for via --legacy-null, purely to log a side-by-side comparison.
    Lives here, not in a pure-sequence chapter."""
    if not LEGACY_NULL:
        return
    legacy = merge(per_pass, roster, params)
    log_legacy_comparison(legacy, merged, quality, roster, params)
