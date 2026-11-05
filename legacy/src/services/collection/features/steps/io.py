"""Logging bootstrap and this run's I/O. Roster and low_info are read from
Postgres — the DCS-approved state, which may include human edits made after
an earlier stage's own model run finished (a manual relation added in the
Graphs review, a renamed character) — never from a leftover file, which
would silently miss exactly those edits.
"""
import logging

from src.repository import RelationRepository, UniverseRepository
from src.services.collection.features.steps.constants import ARC, LOCATION, UNIVERSE_NAME
from src.services.collection.relations.steps.low_info import compute_low_info
from src.shared.decorators import announce, logged, report

_universe_repo = UniverseRepository()
_relation_repo = RelationRepository()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")


def get_universe():
    universe = _universe_repo.get_universe(UNIVERSE_NAME, ARC)
    if universe is None:
        raise RuntimeError(
            f"universe {UNIVERSE_NAME!r}/{ARC!r} not found — run stage 1 (cast) and approve the "
            "roster in DCS before running stage 2 (features)")
    return universe


@announce("loading approved roster from the database")
@report(lambda r: f"approved roster: {len(r)} characters")
def load_roster() -> list[str]:
    return [c.get_name() for c in get_universe().get_roster()]


def _merged_from_db_relations(relations) -> dict:
    merged: dict[str, list[dict]] = {}
    for rel in relations:
        entry = {"members": rel.get_members()} if not rel.is_directed() \
            else {"source": rel.get_source(), "target": rel.get_target()}
        merged.setdefault(rel.get_type(), []).append(entry)
    return merged


@logged(lambda _, universe_id: f"no approved relations in database for universe {universe_id} — approve the "
        "relations queue item in DCS first; proceeding without low_info exclusion", level=logging.WARNING)
def _log_no_approved_relations(universe_id: int) -> None:
    pass


@logged(lambda _, count: f"low_info characters (recomputed from approved DB relations): {count} — excluded from collection")
def _log_low_info_count(count: int) -> None:
    pass


def load_low_info_set(universe, roster: list[str]) -> set[str]:
    # Recomputed from the database's approved relations — confirm_relations
    # (see api/routes/confirm.py) is the only place relations data is ever
    # written for real, and a human can add/edit relations there (e.g. a
    # manual edge in DCS) after stage3's own model passes ran. Reading a
    # pre-approval snapshot file instead would miss exactly that edit — a
    # character who only clears the degree bar via a manual DCS correction
    # must not still get silently skipped here.
    relations = _relation_repo.get_relations(universe.get_id())
    if not relations:
        _log_no_approved_relations(universe.get_id())
        return set()
    merged = _merged_from_db_relations(relations)
    isolate_set = {c.get_name() for c in universe.get_roster() if c.is_isolated()}
    low_info_set = set(compute_low_info(merged, roster, isolate_set))
    _log_low_info_count(len(low_info_set))
    return low_info_set


def assemble_output(roster, low_info_set, ordinal_names, flag_names, profile_names,
                     features, profile, null_share, quality) -> dict:
    return {
        "universe": {"universe": UNIVERSE_NAME, "time_period": ARC, "location": LOCATION},
        "roster": [{"name": n, "low_info": n in low_info_set} for n in roster],
        "params": {"ordinals": ordinal_names, "flags": flag_names, "profile": profile_names},
        "features": features,
        "profile": profile,
        "quality": {
            # informational only — no threshold nulls the parameter for
            # everyone. A rare-but-real trait for 2-3 characters must survive;
            # nulling stays per-parameter-per-character (consensus_rank's
            # <2-available-passes rule), never for the whole parameter.
            # null_share_per_param is scoped to collect_roster (who was
            # actually queried) — low_info characters aren't in the
            # denominator, features=None for them is exclusion, not a null.
            "null_share_per_param": null_share,
            "consensus": quality,
            "low_info_count": len(low_info_set),
        },
    }


@logged(lambda _, param, old_null, new_unplaced, min_kappa, n_blocks:
        f"  {param:<28} old_null={old_null:2d}  new_unplaced={new_unplaced:2d}  "
        f"new_min_kappa={min_kappa}  new_n_blocks={n_blocks}")
def _log_legacy_comparison_row(param: str, old_null: int, new_unplaced: int, min_kappa, n_blocks) -> None:
    pass


@logged(lambda _: "--legacy-null comparison (old per-cell vote/null rule vs new consensus blocks):")
def _log_legacy_comparison_header() -> None:
    pass


def log_legacy_comparison(legacy, merged, quality, collect_roster, params) -> None:
    _log_legacy_comparison_header()
    for param in params:
        old_null = sum(1 for n in collect_roster if legacy[n][param]["value"] is None)
        new_unplaced = sum(1 for n in collect_roster if merged[n][param] is None)
        _log_legacy_comparison_row(param, old_null, new_unplaced,
                                    quality[param]["min_kappa"], quality[param]["n_blocks"])


@logged(lambda _, param, min_kappa, n_blocks, block_sizes:
        f"{param:<28} min_kappa={min_kappa}  n_blocks={n_blocks}  block_sizes={block_sizes}")
def _log_consensus_row(param: str, min_kappa, n_blocks, block_sizes) -> None:
    pass


def log_consensus_summary(quality, params) -> None:
    for param in params:
        q = quality[param]
        _log_consensus_row(param, q["min_kappa"], q["n_blocks"], q["block_sizes"])
