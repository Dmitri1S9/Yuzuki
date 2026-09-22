"""Reports per-parameter consensus quality (kappa) to DCS for visibility,
and writes the initial ordinal/flag positions to Postgres — the baseline
"algorithmic" ranking the Observe Beauty view reads and can then override
via CharacterRepository.save_feature_positions (the real, human-reviewed
confirm path; this is just what stage 2 hands it to start from).
"""
import logging

from src.infra.dcs_client import push_kappa_report
from src.repository import CharacterRepository, UniverseRepository
from src.services.collection.features.steps.constants import ARC, UNIVERSE_NAME
from src.services.consensus.consensus import positions_from_consensus
from src.shared.decorators import announce

log = logging.getLogger(__name__)

_universe_repo = UniverseRepository()
_character_repo = CharacterRepository()


@announce("pushing kappa quality report to DCS")
def push_report_to_dcs(quality: dict, roster: list[str]) -> None:
    universe_id = _universe_repo.create_universe(UNIVERSE_NAME, roster, ARC)
    push_kappa_report(universe_id, UNIVERSE_NAME, ARC, quality)


@announce("persisting initial ordinal/flag positions to database")
def persist_features_to_database(features: dict, params: list[str], roster: list[str]) -> int:
    # features[name] is None (low_info) or {param: {"consensus_z", ...} | None}.
    # A human hasn't reviewed this yet — it's the algorithm's own placement,
    # exactly what "original vs algorithmic" in Observe Beauty compares
    # against, and what confirm() overwrites once someone actually reviews it.
    universe_id = _universe_repo.create_universe(UNIVERSE_NAME, roster, ARC)
    for param in params:
        per_character = {name: (cells.get(param) if cells else None) for name, cells in features.items()}
        positions = positions_from_consensus(per_character)
        _character_repo.save_feature_positions(universe_id, param, positions)
    return universe_id
