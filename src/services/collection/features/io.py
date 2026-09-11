"""Logging bootstrap and this run's file I/O — reads stage 1/3's JSON
handoff files, writes stage2_features_{SLUG}.json and the pass CSVs this
stage also reads back from (see cast/output.py's docstring for why these
files exist alongside the database). No DB persistence here yet — a known,
separately-scoped gap; see ARCHITECTURE.md.
"""
import json
import logging
import os

from src.services.collection.features.constants import ARC, LOCATION, SLUG, UNIVERSE_NAME
from src.shared.decorators import announce, report
from src.shared.paths import run_path

log = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")


@announce("loading frozen roster from stage 1's output")
@report(lambda r: f"frozen roster: {len(r)} characters")
def load_roster() -> list[str]:
    with open(run_path(f"stage1_cast_{SLUG}.json"), encoding="utf-8") as f:
        return [r["name"] for r in json.load(f)["roster"]]


def load_low_info_set() -> set[str]:
    # stage3 (relations) now runs before this stage — see run_pipeline.sh.
    # Characters with 0 relations and not a confirmed isolate carry no
    # signal either way; skip the API cost of ranking/flagging them, but
    # keep them in the roster (features: None, low_info: true).
    relations_path = run_path(f"relations_merged_{SLUG}.json")
    if not os.path.exists(relations_path):
        log.warning("%s not found — run stage3 first for low_info exclusion; proceeding without it", relations_path)
        return set()
    with open(relations_path, encoding="utf-8") as f:
        low_info_set = set(json.load(f).get("low_info_characters", []))
    log.info("low_info characters (0 relations, not isolate): %d — excluded from collection", len(low_info_set))
    return low_info_set


def have_pass_csvs(passes) -> bool:
    return all(os.path.exists(run_path(f"pass{p}_{SLUG}.csv")) for p in passes)


def assemble_output(roster, low_info_set, ordinal_names, flag_names, features, null_share, quality) -> dict:
    return {
        "universe": {"universe": UNIVERSE_NAME, "time_period": ARC, "location": LOCATION},
        "roster": [{"name": n, "low_info": n in low_info_set} for n in roster],
        "params": {"ordinals": ordinal_names, "flags": flag_names},
        "features": features,
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


def write_features_file(out: dict) -> None:
    with open(run_path(f"stage2_features_{SLUG}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def log_legacy_comparison(legacy, merged, quality, collect_roster, params) -> None:
    log.info("--legacy-null comparison (old per-cell vote/null rule vs new consensus blocks):")
    for param in params:
        old_null = sum(1 for n in collect_roster if legacy[n][param]["value"] is None)
        new_unplaced = sum(1 for n in collect_roster if merged[n][param] is None)
        log.info(
            "  %-28s old_null=%2d  new_unplaced=%2d  new_min_kappa=%s  new_n_blocks=%s",
            param, old_null, new_unplaced,
            quality[param]["min_kappa"], quality[param]["n_blocks"],
        )


def log_consensus_summary(quality, params) -> None:
    for param in params:
        q = quality[param]
        log.info("%-28s min_kappa=%s  n_blocks=%s  block_sizes=%s", param, q["min_kappa"], q["n_blocks"], q["block_sizes"])
