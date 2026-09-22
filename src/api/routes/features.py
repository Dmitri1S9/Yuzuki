"""Read/write access to ordinal/flag rankings for the "Observe Beauty" view
— DCS reads a parameter's fresh consensus result (block_index/consensus_z,
recomputed from the raw per-pass cache on every request — pure numpy/python
over already-collected data, no new Gemini calls) plus its current
confirmed position, lets a human drag/reorder/drop characters, and posts
the edited order back here. This is the only place ordinal/flag positions
are written for real; stage 2 only writes an initial algorithmic baseline
(see collection/features/persistence.py) for this to start from.

Reads the raw per-pass cache (RawPassRepository — DB-backed, see
services/collection/features/steps/collection.py's collect_or_load_passes,
which writes it) and calls the consensus function directly (not via
services.collection.features — that package parses sys.argv at import time
for the universe/arc CLI args, which would misfire inside this long-running
API process). Both ordinals and flags are 2 passes now (see
features/constants.py), but go through different consensus algorithms —
ordinals through ordinal_consensus (real tier reconciliation, 8-10 tiers),
flags through flag_consensus (cheap exact-match blocks, 2-3 tiers) — same
split the real pipeline now uses, see features/pipeline.py.
"""
import logging
import os
import re

from fastapi import APIRouter, HTTPException

from src.api.schemas import FeatureConfirmRequest, FeatureDetailOut
from src.domain.parameters import FLAG_PARAMS, ORDINAL_META, ORDINAL_PARAMS
from src.repository import CharacterRepository, RawPassRepository, UniverseRepository
from src.services.consensus.flag_consensus import FLAG_PASSES, flag_consensus
from src.services.consensus.ordinal_consensus import ordinal_consensus

_TIER_LINE_RE = re.compile(r"^\[T(\d+)\]\s+(.*)$")
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                               "infra", "prompts", "templates")

log = logging.getLogger(__name__)
router = APIRouter(tags=["features"])

_universe_repo = UniverseRepository()
_character_repo = CharacterRepository()
_raw_pass_repo = RawPassRepository()


def _require_universe(universe_id: int):
    universe = _universe_repo.get_universe_by_id(universe_id)
    if universe is None:
        raise HTTPException(status_code=404, detail=f"universe {universe_id} not found")
    return universe


def _require_param(param_name: str) -> bool:
    """Returns is_ordinal, or 404s — a flag/ordinal name is the only valid
    param_name, same validation CharacterRepository does at the SQL layer."""
    if param_name in ORDINAL_PARAMS:
        return True
    if param_name in FLAG_PARAMS:
        return False
    raise HTTPException(status_code=404, detail=f"unknown parameter {param_name!r}")


def _tier_labels(prompt_template: str) -> list[str]:
    """Reads the "[T1] A person who..." calibration lines straight out of
    the ordinal's own prompt template — that text is the only place these
    descriptions exist, never duplicated into parameters.json. Static text,
    no Jinja variables in these lines, so no rendering needed."""
    path = os.path.join(_TEMPLATES_DIR, f"{prompt_template}.j2")
    if not os.path.exists(path):
        return []
    labels: dict[int, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = _TIER_LINE_RE.match(line.strip())
            if m:
                labels[int(m.group(1)) - 1] = m.group(2)
    return [labels[i] for i in sorted(labels)]


def _read_pass_scores(universe_id: int, param_name: str) -> dict[int, dict[str, float | None]]:
    all_passes = _raw_pass_repo.get_passes(universe_id, FLAG_PASSES)
    if all_passes is None:
        return {p: {} for p in FLAG_PASSES}
    return {p: all_passes[p].get(param_name, {}) for p in FLAG_PASSES}


@router.get("/features/params")
def list_feature_params():
    return {"ordinals": list(ORDINAL_PARAMS), "flags": list(FLAG_PARAMS)}


@router.get("/universes/{universe_id}/features/{param_name}", response_model=FeatureDetailOut)
def get_feature(universe_id: int, param_name: str):
    _require_universe(universe_id)
    is_ordinal = _require_param(param_name)

    positions = _character_repo.get_feature_positions(universe_id, param_name)
    roster = sorted(positions)

    per_pass_scores = _read_pass_scores(universe_id, param_name)
    have_data = any(per_pass_scores[p] for p in FLAG_PASSES)

    if have_data:
        consensus_fn = ordinal_consensus if is_ordinal else flag_consensus
        per_character, _quality = consensus_fn(per_pass_scores, roster)
    else:
        per_character = {name: None for name in roster}

    characters = [
        {
            "name": name,
            "block_index": (cell or {}).get("block_index"),
            "consensus_z": (cell or {}).get("consensus_z"),
            "tier": (cell or {}).get("tier"),
            "sub_position": (cell or {}).get("sub_position"),
        }
        for name, cell in per_character.items()
    ]
    if is_ordinal:
        meta = ORDINAL_META[param_name]
        definition = meta["definition"]
        scale = {"tier_count": meta["tier_count"], "normal_tier_index": meta["normal_tier_index"]}
        tier_labels = _tier_labels(ORDINAL_PARAMS[param_name])
    else:
        definition = FLAG_PARAMS[param_name]["definition"]
        scale = None
        tier_labels = []

    return {
        "param_name": param_name,
        "is_ordinal": is_ordinal,
        "definition": definition,
        "tier_labels": tier_labels,
        "characters": characters,
        "positions": positions,
        "scale": scale,
    }


@router.post("/universes/{universe_id}/features/{param_name}/confirm")
def confirm_feature(universe_id: int, param_name: str, body: FeatureConfirmRequest):
    _require_universe(universe_id)
    _require_param(param_name)

    _character_repo.save_feature_positions(universe_id, param_name, body.positions)
    log.info("confirmed %s positions for universe %d: %d character(s)",
              param_name, universe_id, len(body.positions))
    return {"status": "confirmed", "universe_id": universe_id, "param_name": param_name,
            "positions_saved": len(body.positions)}
