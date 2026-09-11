"""main.py — the instruction list for stage 2 (ordinal ranks + flags). Read
main() top to bottom, nothing else; every step's own logic lives in its own
file under this package (constants.py, collection.py, merge.py, io.py) — see
ARCHITECTURE.md. No database persistence yet — a known, separately-scoped
gap (see PIPELINE.md / ARCHITECTURE.md).
"""
import os

# Must run before the import below — see cast/main.py's identical comment.
os.environ.setdefault("REDIS_URL_CACHE", "redis://localhost:6379/1")
os.environ.setdefault("REDIS_URL_CELERY", "redis://localhost:6379/0")

from src.domain.parameters import FLAG_PARAMS, ORDINAL_PARAMS, all_param_names
from src.services.collection.features.collection import (
    collect, create_client, load_per_pass_from_csv, write_pass_csvs,
)
from src.services.collection.features.constants import LEGACY_NULL, PASSES, REFETCH
from src.services.collection.features.io import (
    assemble_output, configure_logging, have_pass_csvs, load_low_info_set, load_roster,
    log_consensus_summary, log_legacy_comparison, write_features_file,
)
from src.services.collection.features.merge import (
    apply_low_info_mask, compute_null_share, merge, merge_consensus,
)
from src.services.collection.features.persistence import push_report_to_dcs


def main():
    configure_logging()

    roster = load_roster()
    low_info_set = load_low_info_set()
    collect_roster = [n for n in roster if n not in low_info_set]

    params = all_param_names()

    if have_pass_csvs(PASSES) and not REFETCH:
        per_pass = load_per_pass_from_csv(collect_roster, params)
    else:
        client = create_client()
        per_pass = collect(client, collect_roster)
        write_pass_csvs(per_pass, collect_roster, params)

    merged, quality = merge_consensus(per_pass, collect_roster, params)

    if LEGACY_NULL:
        legacy = merge(per_pass, collect_roster, params)
        log_legacy_comparison(legacy, merged, quality, collect_roster, params)

    null_share = compute_null_share(merged, collect_roster, params)
    features = apply_low_info_mask(merged, roster, low_info_set)

    out = assemble_output(roster, low_info_set, list(ORDINAL_PARAMS), list(FLAG_PARAMS),
                           features, null_share, quality)
    write_features_file(out)
    push_report_to_dcs(quality, roster)
    log_consensus_summary(quality, params)
    return out


if __name__ == "__main__":
    main()
