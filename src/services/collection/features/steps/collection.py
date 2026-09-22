"""Ordinal/flag pass collection and the raw-score cache round-trip.
Parameter names come from src.domain.parameters (the single source of
truth) — not hardcoded here.
"""
import logging
import re

from scipy.stats import norm

from src.domain.parameters import FLAG_PARAMS, ORDINAL_PARAMS
from src.infra.ai_clients.gemini_client import GeminiClient
from src.repository import RawPassRepository
from src.services.collection.features.steps.constants import ARC, FLAG_PASSES, PASSES, REFETCH, UNIVERSE_NAME

log = logging.getLogger(__name__)
_raw_pass_repo = RawPassRepository()


def create_client() -> GeminiClient:
    return GeminiClient()


def within_normal(i: int, n: int) -> float:
    if n <= 1:
        return 0.5
    z = (i - (n + 1) / 2) / ((n - 1) / 6)
    return float(norm.cdf(z))


def compute_score(position, segment_counts):
    if position is None or not segment_counts:
        return None
    cumulative = 0
    for tier_idx, count in enumerate(segment_counts):
        if position < cumulative + count:
            return round(tier_idx * 10 + within_normal(position - cumulative + 1, count), 4)
        cumulative += count
    return None


def parse_sorted(sorted_list, marker_re):
    positions, segments = {}, []
    current = position = 0
    for item in sorted_list:
        item = item.strip()
        if not item:
            continue
        if marker_re.match(item):
            segments.append(current)
            current = 0
        else:
            positions[item] = position
            position += 1
            current += 1
    segments.append(current)
    return positions, segments


def scores_from_result(result, marker_re, roster):
    positions, segments = parse_sorted(result["sorted"], marker_re)
    return {name: compute_score(positions.get(name), segments) for name in roster}


def collect(client, roster):
    # Optional [brackets]: the tier calibration text in every rank prompt
    # shows markers as "[T1]  A person who..." (see e.g.
    # user_prompt_intellect_potential.j2) even though the schema instruction
    # asks for bare "T1" in the output — the model sometimes echoes the
    # calibration section's bracketed style into "sorted" instead. Confirmed
    # live: a fresh intellect call returned "[T1]".."[T9]", which the
    # unbracketed-only regex didn't recognize as markers at all, so every
    # name fell into one segment (tier_idx=0) — this is exactly what
    # happened to this universe's original 3-pass intellect collection.
    rank_re = re.compile(r"^\[?T\d+\]?$")
    per_pass = {p: {} for p in PASSES}  # PASSES == FLAG_PASSES == (1, 2) now
    for param, prompt in ORDINAL_PARAMS.items():
        for p in PASSES:
            log.info("rank %-18s pass=%d", param, p)
            result = client.rank(prompt, roster, UNIVERSE_NAME, ARC, pass_number=p)
            per_pass[p][param] = scores_from_result(result, rank_re, roster)
    for flag in FLAG_PARAMS:
        for p in FLAG_PASSES:
            log.info("flag %-18s pass=%d", flag, p)
            result = client.flag(flag, roster, UNIVERSE_NAME, ARC, pass_number=p)
            per_pass[p][flag] = scores_from_result(result, rank_re, roster)
    return per_pass


def collect_profile(client, roster):
    # Single call, single pass — body_age/soul_age/gender/species are direct
    # categorical facts, not a ranking, so there is nothing for a second
    # pass to corroborate against the way ordinals/flags need.
    log.info("profile %-18s n=%d", "(all fields)", len(roster))
    result = client.profile(roster, UNIVERSE_NAME, ARC)
    by_name = result["characters"]
    missing = [n for n in roster if n not in by_name]
    if missing:
        log.warning("profile response omitted %d roster names: %s", len(missing), missing)
    return {name: by_name.get(name) for name in roster}


def write_passes_to_db(universe_id, per_pass):
    for p, scores_by_param in per_pass.items():
        _raw_pass_repo.save_pass(universe_id, p, scores_by_param)


def collect_or_load_passes(client, universe_id, roster, ordinal_names, flag_names):
    """Real per-character branch: reuse this universe's own cached raw scores
    when every pass is already saved (and a refetch wasn't asked for) instead
    of re-spending API calls, otherwise collect fresh and save them. Lives
    here, not in main.py's ladder or pipeline.py's chapters — a chapter
    function is pure sequence, this is the one place that decision actually
    belongs."""
    if not REFETCH:
        cached = _raw_pass_repo.get_passes(universe_id, PASSES)
        if cached is not None:
            return cached
    per_pass = collect(client, roster)
    write_passes_to_db(universe_id, per_pass)
    return per_pass
