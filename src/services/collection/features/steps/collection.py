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
from src.shared.decorators import logged
from src.shared.naming import display_name, resolve_alias

_raw_pass_repo = RawPassRepository()

MAX_MISSING_FRACTION = 0.10  # more than this share of the roster (min 1 name)
                             # absent from both lists = a broken response.
MAX_COLLECTION_ATTEMPTS = 3  # 1 real try + up to 2 retries, force_refresh on
                              # every retry so a bad cached response can't
                              # just get handed back unchanged (see
                              # gemini_client.py's __cached).


class CollectionError(Exception):
    """A rank()/flag() response was schema-valid but substantively broken —
    live-caught 2026-09-23 (Bunny Girl Senpai, 14/51 flags): every roster
    member came back "unknown" for traits the SAME character had just been
    confidently placed on elsewhere, and a few more flags silently dropped
    most of the roster from both "sorted" and "unknown" entirely, with
    nothing raising along the way — a bad response was indistinguishable
    from a genuine "the model has no opinion" once it reached the database.
    This is the boundary that used to swallow that silently; raised, never
    caught and downgraded to a log line, so a broken run stops instead of
    quietly becoming data a human has to notice by eye."""


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


def scores_from_result(result, marker_re, roster, alias_map: dict[str, list[str]] | None = None):
    positions, segments = parse_sorted(result["sorted"], marker_re)
    # Defensive: the system prompt tells the model to always answer with
    # the bare canonical name, never an "(aka ...)" alias — confirmed live
    # it doesn't always listen (a real response used the alias instead of
    # the primary name for one character). See naming.resolve_alias(): what
    # actually matters is that ONE known name for a character shows up in
    # "sorted", not which exact variant/casing/whitespace the model picked.
    resolved_positions = {}
    for item, pos in positions.items():
        name = resolve_alias(item, roster, alias_map or {})
        resolved_positions.setdefault(name, pos)
    return {name: compute_score(resolved_positions.get(name), segments) for name in roster}


@logged(lambda _, label, missing:
        f"{label}: {len(missing)} roster member(s) missing from both 'sorted' and 'unknown', left unplaced: {missing}",
        level=logging.WARNING)
def _log_missing_but_not_fatal(label: str, missing: list) -> None:
    pass


def _check_response_complete(result, scores, roster, alias_map, label):
    """Raises CollectionError instead of letting either of these two real,
    live-observed failure shapes pass as ordinary data:

    1. Missing entirely: a roster member appears in neither "sorted" nor
       "unknown" — the model (or something between it and us) silently
       dropped them, not a real judgment about anyone. Confirmed live on
       has_humor/goal_power/is_provocative: only 1 of 16 characters
       survived, the rest simply weren't accounted for anywhere.
    2. Degenerate empty: EVERY roster member came back "unknown" — for a
       roster bigger than a couple of people, a real per-character
       judgment landing at zero placements across the board is far less
       likely than a truncated/malformed response the schema happened to
       still validate. Confirmed live: a character with confident
       placements on 33 other flags came back "unknown" on this one, for
       a trait no harder to judge than the ones it was placed on."""
    unknown_resolved = {resolve_alias(n, roster, alias_map or {}) for n in result.get("unknown", [])}
    missing = [n for n in roster if scores.get(n) is None and n not in unknown_resolved]
    if len(missing) > max(1, int(len(roster) * MAX_MISSING_FRACTION)):
        raise CollectionError(
            f"{label}: {len(missing)}/{len(roster)} roster member(s) missing from both "
            f"'sorted' and 'unknown' — incomplete response: {missing}"
        )
    if missing:
        # A stray name or two is a different thing from the batch-level
        # truncation above: confirmed live on MHA (ordinal 'wealth' pass 2),
        # the model dropped the same 1 of 89 across all 3 fresh attempts
        # (a roster name with a doubled word, "Tetsutetsu Tetsutetsu") —
        # crashing a whole 89-character run over that helps nobody. They
        # stay unplaced (None), same as "unknown", and the warning names them.
        _log_missing_but_not_fatal(label, missing)
    placed = sum(1 for v in scores.values() if v is not None)
    if placed == 0 and len(roster) > 2:
        raise CollectionError(
            f"{label}: all {len(roster)} roster member(s) came back 'unknown' — "
            f"treating as a broken response, not a real judgment"
        )


@logged(lambda _, kind, param, p, attempt: f"{kind} {param:<18} pass={p} attempt={attempt}")
def _log_collection_attempt(kind: str, param: str, p: int, attempt: int) -> None:
    pass


@logged(lambda _, label, attempt, max_attempts, error: f"{label} (attempt {attempt}/{max_attempts}, retrying fresh) — {error}",
        level=logging.WARNING)
def _log_collection_retry(label: str, attempt: int, max_attempts: int, error: Exception) -> None:
    pass


def collect(client, roster, alias_map: dict[str, list[str]] | None = None):
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
    # The model only ever gets to answer with the bare name (system_prompt_
    # ranker.j2/system_prompt_flag_rank.j2's own rule on this) — display_
    # roster is what goes INTO the prompt (aliases appended for recognition,
    # 2026-09-23), but scores_from_result still matches against the plain
    # `roster` below, since that's what comes back out.
    alias_map = alias_map or {}
    display_roster = [display_name(n, alias_map) for n in roster]
    per_pass = {p: {} for p in PASSES}  # PASSES=(1,2) for ordinals, FLAG_PASSES=(1,) for flags
    for param, prompt in ORDINAL_PARAMS.items():
        for p in PASSES:
            label = f"ordinal {param!r} pass={p}"
            for attempt in range(1, MAX_COLLECTION_ATTEMPTS + 1):
                _log_collection_attempt("rank", param, p, attempt)
                result = client.rank(prompt, display_roster, UNIVERSE_NAME, ARC,
                                      pass_number=p, force_refresh=(attempt > 1))
                scores = scores_from_result(result, rank_re, roster, alias_map)
                try:
                    _check_response_complete(result, scores, roster, alias_map, label)
                    break
                except CollectionError as e:
                    if attempt == MAX_COLLECTION_ATTEMPTS:
                        raise
                    _log_collection_retry(label, attempt, MAX_COLLECTION_ATTEMPTS, e)
            per_pass[p][param] = scores
    for flag in FLAG_PARAMS:
        for p in FLAG_PASSES:
            label = f"flag {flag!r} pass={p}"
            for attempt in range(1, MAX_COLLECTION_ATTEMPTS + 1):
                _log_collection_attempt("flag", flag, p, attempt)
                result = client.flag(flag, display_roster, UNIVERSE_NAME, ARC,
                                      pass_number=p, force_refresh=(attempt > 1))
                # Same sorted+[T1]/[T2]/[T3]-marker shape rank() produces for
                # ordinals (2026-09-23, back from plain list-membership) —
                # scores_from_result/parse_sorted/compute_score are already
                # marker-count-agnostic (built for T1..T10), so the identical
                # parsing applies unchanged at 3 markers.
                scores = scores_from_result(result, rank_re, roster, alias_map)
                try:
                    _check_response_complete(result, scores, roster, alias_map, label)
                    break
                except CollectionError as e:
                    if attempt == MAX_COLLECTION_ATTEMPTS:
                        raise
                    _log_collection_retry(label, attempt, MAX_COLLECTION_ATTEMPTS, e)
            per_pass[p][flag] = scores
    return per_pass


@logged(lambda _, missing: f"profile response omitted {len(missing)} roster names: {missing}" if missing else None,
        level=logging.WARNING)
def _log_profile_missing(missing: list) -> None:
    pass


@logged(lambda _, client, roster: f"profile {'(all fields)':<18} n={len(roster)}")
def collect_profile(client, roster):
    # Single call, single pass — body_age/soul_age/gender/species are direct
    # categorical facts, not a ranking, so there is nothing for a second
    # pass to corroborate against the way ordinals/flags need.
    result = client.profile(roster, UNIVERSE_NAME, ARC)
    by_name = result["characters"]
    missing = [n for n in roster if n not in by_name]
    _log_profile_missing(missing)
    return {name: by_name.get(name) for name in roster}


def write_passes_to_db(universe_id, per_pass):
    for p, scores_by_param in per_pass.items():
        _raw_pass_repo.save_pass(universe_id, p, scores_by_param)


def collect_or_load_passes(client, universe_id, roster, ordinal_names, flag_names,
                            alias_map: dict[str, list[str]] | None = None):
    """Real per-character branch: reuse this universe's own cached raw scores
    when every pass is already saved (and a refetch wasn't asked for) instead
    of re-spending API calls, otherwise collect fresh and save them. Lives
    here, not in main.py's ladder or pipeline.py's chapters — a chapter
    function is pure sequence, this is the one place that decision actually
    belongs.

    Ordinals and flags are checked (and, on a miss, re-collected) together,
    not just by pass_number: ordinals need PASSES=(1,2), flags need only
    FLAG_PASSES=(1,), and a stale cache from before flags moved from 2
    tier-based passes to 1 boolean-membership pass would otherwise still
    "hit" on pass_number alone (pass 1 has real rows either way) while
    silently handing flag_consensus old-shape scores it was never built to
    parse. Requiring both checks to hit, params and all, means any
    collection-scheme change on either side safely falls through to a fresh
    collect instead of a wrong reuse."""
    if not REFETCH:
        cached_ordinals = _raw_pass_repo.get_passes(universe_id, PASSES, set(ordinal_names))
        cached_flags = _raw_pass_repo.get_passes(universe_id, FLAG_PASSES, set(flag_names))
        if cached_ordinals is not None and cached_flags is not None:
            per_pass = {p: dict(cached_ordinals.get(p, {})) for p in PASSES}
            for p in FLAG_PASSES:
                per_pass.setdefault(p, {}).update(cached_flags.get(p, {}))
            return per_pass
    per_pass = collect(client, roster, alias_map)
    write_passes_to_db(universe_id, per_pass)
    return per_pass
