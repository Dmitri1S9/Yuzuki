"""Push-only: reports per-parameter consensus quality (kappa) to DCS for
visibility. No edit/confirm loop here — the numbers are already computed by
consensus_rank(); DCS just renders them, color-coded by quality. Ordinal/
flag values themselves still aren't written to Postgres at all — a known,
separately-scoped gap (see ARCHITECTURE.md).
"""
import logging

from src.infra.dcs_client import push_kappa_report
from src.repository import UniverseRepository
from src.services.collection.features.constants import ARC, UNIVERSE_NAME
from src.shared.decorators import announce

log = logging.getLogger(__name__)

_universe_repo = UniverseRepository()


@announce("pushing kappa quality report to DCS")
def push_report_to_dcs(quality: dict, roster: list[str]) -> None:
    universe_id = _universe_repo.create_universe(UNIVERSE_NAME, roster, ARC)
    push_kappa_report(universe_id, UNIVERSE_NAME, ARC, quality)
