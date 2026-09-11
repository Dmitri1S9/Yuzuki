"""main.py — the instruction list for stage 3 (relations). Read main() top
to bottom, nothing else; every step's own logic lives in its own file under
this package (constants.py, collection.py, merge.py, low_info.py, io.py,
persistence.py) — see ARCHITECTURE.md.
"""
import os

# Must run before the import below — see cast/main.py's identical comment.
os.environ.setdefault("REDIS_URL_CACHE", "redis://localhost:6379/1")
os.environ.setdefault("REDIS_URL_CELERY", "redis://localhost:6379/0")

from src.services.collection.relations.collection import (
    collect_general_pool, collect_group_relations, collect_medium_groups, create_client,
)
from src.services.collection.relations.io import (
    assemble_output, configure_logging, load_cast_data, log_final_summary,
    write_merged_output_file, write_passes_file,
)
from src.services.collection.relations.low_info import compute_low_info
from src.services.collection.relations.merge import merge_all
from src.services.collection.relations.persistence import persist_to_database, push_draft_to_dcs


def main():
    configure_logging()

    roster, isolate_set, medium_groups, large_groups = load_cast_data()
    all_groups = medium_groups + large_groups

    client = create_client()
    medium_per_group = collect_medium_groups(client, medium_groups)
    general_rounds = collect_general_pool(client, roster)
    group_relations, group_relations_dropped = collect_group_relations(client, all_groups)
    write_passes_file(medium_per_group, general_rounds)

    merged, dropped = merge_all(medium_per_group, general_rounds, roster)
    low_info = compute_low_info(merged, roster, isolate_set)

    out = assemble_output(merged, dropped, group_relations, group_relations_dropped,
                           low_info, general_rounds)
    write_merged_output_file(out)

    universe_id = persist_to_database(group_relations, roster)
    push_draft_to_dcs(merged, roster, medium_groups, isolate_set, set(low_info), universe_id)
    log_final_summary(out, roster)
    return out


if __name__ == "__main__":
    main()
