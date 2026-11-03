"""Single source of truth for the whole character — every one of the 4
profile fields, 6 ordinal ranking parameters, and 51 binary flags, all
defined in parameters.json.

Edit that one file to add, rename, or remove a parameter (profile, ordinal,
or flag) — every consumer derives its name list from here instead of
hand-copying it: Character's dynamically generated getters (character.py),
the repository's filter whitelist, the features collection stage, and the
kappa export tool.
"""
import json
from pathlib import Path

_PARAMETERS_PATH = Path(__file__).parent / "parameters.json"


def _load_parameters() -> tuple[dict[str, dict], dict[str, str], dict[str, dict], dict[str, dict]]:
    with open(_PARAMETERS_PATH, encoding="utf-8") as f:
        categories = json.load(f)

    profile_params = categories.pop("profile")

    ordinals_raw = categories.pop("ordinals")
    ordinal_params = {name: meta["prompt_template"] for name, meta in ordinals_raw.items()}
    ordinal_meta = {
        name: {
            "definition": meta["definition"],
            "tier_count": meta["tier_count"],
            "normal_tier_index": meta["normal_tier_index"],
        }
        for name, meta in ordinals_raw.items()
    }

    flag_params: dict[str, dict] = {}
    for category in categories.values():
        flag_params.update(category)

    return profile_params, ordinal_params, flag_params, ordinal_meta


# profile field name -> {"definition": ..., "values": [...] | None} — collected
# via a different call (BaseAIClient.profile()) than ordinals/flags, kept as
# its own registry rather than folded into all_param_names().
PROFILE_PARAMS: dict[str, dict]
# ordinal name -> its user-prompt template name. The "_potential" suffix
# mismatch between the intellect column name and its template filename is a
# pre-existing naming quirk; this mapping is now the one place it lives.
ORDINAL_PARAMS: dict[str, str]
# flag name -> {"definition": ..., "sort_axis": ...}
FLAG_PARAMS: dict[str, dict]
# ordinal name -> {"definition": ..., "tier_count": ..., "normal_tier_index":
# ...} — the fixed tier scale's size and where its "ordinary person" anchor
# tier sits (0-indexed). Kept separate from ORDINAL_PARAMS since that one's
# value type (the prompt template name) is already relied on as a plain
# string by every existing caller (features/collection.py's
# client.rank(prompt, ...)).
ORDINAL_META: dict[str, dict]
PROFILE_PARAMS, ORDINAL_PARAMS, FLAG_PARAMS, ORDINAL_META = _load_parameters()

# Every flag shares the same fixed 3-tier scale now (T1=doesn't have it,
# T2=unsure, T3=clearly has it — see system_prompt_flag_rank.j2), unlike
# ordinals where tier_count/normal_tier_index vary per parameter — so this
# is one shared constant, not a per-flag dict like ORDINAL_META.
# normal_tier_index=1 (T2, "unsure") is the closest a flag has to ordinals'
# "ordinary person" mid-scale anchor.
FLAG_META = {"tier_count": 3, "normal_tier_index": 1}


def all_param_names() -> list[str]:
    """Ordinals + flags — the parameters stage2 (rank/flag collection) loops
    over. Profile fields are collected separately (BaseAIClient.profile()
    is one call for all 4 at once, not one call per field) and aren't part
    of this list."""
    return list(ORDINAL_PARAMS) + list(FLAG_PARAMS)


def is_profile(name: str) -> bool:
    return name in PROFILE_PARAMS


def is_ordinal(name: str) -> bool:
    return name in ORDINAL_PARAMS


def is_flag(name: str) -> bool:
    return name in FLAG_PARAMS
