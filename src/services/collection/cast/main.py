"""main.py — the instruction list for stage 1 (cast + groups). Read main()
top to bottom, nothing else; every step's own logic lives in its own file
under this package (constants.py, roster.py, groups.py, output.py,
persistence.py) — see ARCHITECTURE.md.
"""
import os

# Must run before the import below, which pulls in the AI-client stack and
# instantiates Settings() at import time — a local (non-docker) run has no
# REDIS_URL_CACHE/REDIS_URL_CELERY env var otherwise. In docker these are
# already set by docker-compose.yaml and this is a no-op.
os.environ.setdefault("REDIS_URL_CACHE", "redis://localhost:6379/1")
os.environ.setdefault("REDIS_URL_CELERY", "redis://localhost:6379/0")

from src.services.collection.cast.groups import (
    collect_raw_groups, consolidate_groups, create_client, format_groups_for_output,
)
from src.services.collection.cast.output import (
    assemble_output, configure_logging, log_final_summary, write_output_file,
)
from src.services.collection.cast.persistence import persist_to_database, push_draft_to_dcs
from src.services.collection.cast.roster import (
    build_name_resolver, build_roster, extract_candidate_names, flag_ambiguous_matches,
    list_dropped_names, merge_spelling_variants, resolve_aliases,
)


def main():
    configure_logging()

    client = create_client()
    raw_groups = collect_raw_groups(client)

    canon, presence, mentions = extract_candidate_names(raw_groups)
    raw_cluster_count = len(canon)

    canon, presence, mentions, spelling_key_map, spelling_merge_count = merge_spelling_variants(
        canon, presence, mentions)
    ambiguous_matches = flag_ambiguous_matches(canon)
    canon, presence, mentions, alias_key_map, aliases_of, alias_pairs = resolve_aliases(
        client, canon, presence, mentions)

    resolve = build_name_resolver(spelling_key_map, alias_key_map)
    merged_groups = consolidate_groups(raw_groups, resolve)

    roster = build_roster(canon, presence, mentions, aliases_of, merged_groups)
    dropped = list_dropped_names(canon, presence, mentions, aliases_of, roster, resolve)
    groups_out = format_groups_for_output(merged_groups, canon)

    output = assemble_output(roster, groups_out, raw_cluster_count, spelling_merge_count,
                              alias_pairs, canon, dropped, ambiguous_matches, presence)

    universe_id = persist_to_database(output)
    push_draft_to_dcs(output, universe_id)
    write_output_file(output)
    log_final_summary(output)
    return output


if __name__ == "__main__":
    main()
