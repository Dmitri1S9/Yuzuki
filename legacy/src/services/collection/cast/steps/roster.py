"""Turning reconciled candidate names into the actual roster — corroboration
strength becomes a `low_confidence` flag, never a silent drop (see
build_roster's own docstring below), plus the AniList backstop that adds
names the model's own passes never mentioned at all.
"""
from collections import Counter

from src.services.collection.cast.steps.constants import CAST_PASSES, ROSTER_MIN_PASSES
from src.services.collection.cast.steps.name_matching import name_key
from src.shared.decorators import announce, report


@announce("building roster (found_medium/large/isolate >= threshold in at least one type "
          "flags low_confidence instead of dropping — a human decides in DCS, not the algorithm)")
@report(lambda r: f"roster_size={len(r)} low_confidence={sum(1 for c in r if c['low_confidence'])} "
                   f"confirmed_by_database={sum(1 for c in r if c['confirmed_by_database'])}")
def build_roster(canon: dict, presence: dict, mentions: Counter, aliases_of: dict, merged_groups: dict,
                  anilist_confirmed: set | None = None) -> list[dict]:
    # Every candidate name makes the roster now — the corroboration
    # threshold used to silently delete anyone below it, which meant a
    # human reviewing DCS never even saw them to overrule a bad call
    # (confirmed real: half a real roster disappeared this way with no
    # trace in the UI). low_confidence just marks the same signal for a
    # human to act on instead.
    #
    # anilist_confirmed: keys merge_anilist_names() added from AniList's
    # own cast list for this title — these never got a chance to appear
    # in any collection pass (that's the whole point of backstopping with
    # them), so the pass-count check alone would always mark them
    # low_confidence. A name from an authoritative database isn't the
    # same kind of uncertain as a name the model only mentioned once.
    anilist_confirmed = anilist_confirmed or set()
    roster = []
    for key, name in canon.items():
        found = {ct: len(presence[key].get(ct, set())) for ct in CAST_PASSES}
        group_count = sum(1 for gt in merged_groups for cl in merged_groups[gt] if key in cl["members"])
        confirmed = key in anilist_confirmed
        roster.append({
            "name": name,
            "aliases": aliases_of.get(key, []),
            "found_medium": found["medium"],
            "found_large": found["large"],
            "found_isolate": found["isolates"],
            "group_count": group_count,
            "mention_count": mentions[key],
            "is_isolated": found["isolates"] >= ROSTER_MIN_PASSES,
            "low_confidence": not confirmed and not any(v >= ROSTER_MIN_PASSES for v in found.values()),
            "confirmed_by_database": confirmed,
        })
    roster.sort(key=lambda r: r["name"])
    return roster


@announce("backstopping roster with AniList's own cast list for this title")
@report(lambda r: f"anilist_names_added={len(r[3])}")
def merge_anilist_names(canon: dict, presence: dict, mentions: Counter,
                         anilist_names: list[str]) -> tuple[dict, dict, Counter, list]:
    """A name from AniList's cast list the model's own passes never
    mentioned at all gets its own new roster candidate (no pass presence
    — build_roster() marks these confirmed_by_database instead of
    low_confidence, see there). A name already present under any spelling
    is skipped, not duplicated — checked both by exact display-name match
    and by the same name_key() normalization everything else uses, so a
    near-miss the LLM already found isn't doubled."""
    existing_lower = {name.lower() for name in canon.values()}
    added_keys = []
    for raw_name in anilist_names:
        if raw_name.lower() in existing_lower:
            continue
        key = name_key(raw_name)
        if key in canon:
            continue
        canon[key] = raw_name
        presence[key] = {}
        mentions[key] = 0
        added_keys.append(key)
    return canon, presence, mentions, added_keys
