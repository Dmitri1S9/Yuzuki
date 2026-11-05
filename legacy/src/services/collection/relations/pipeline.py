"""The level between main.py's ladder and the real work — same convention
as cast/pipeline.py. Each chapter here is a flat sequence of named calls
into steps/ (character_relations.py, group_relations.py, merge.py,
low_info.py, io.py, persistence.py), where the actual logic lives. No
loop, branch, or try/except belongs in this file — that's the signal
something here should move one level deeper. State carried between
chapters lives in state.py, not here.
"""
from src.services.collection.relations.state import RelationsCollection
from src.services.collection.relations.steps.character_relations import (
    collect_cross_group_relations, collect_general_pool, collect_medium_groups,
)
from src.services.collection.relations.steps.group_relations import (
    collect_group_hierarchy, collect_group_relations,
)
from src.services.collection.relations.steps.io import assemble_output, load_cast_data, log_final_summary
from src.services.collection.relations.steps.low_info import compute_low_info
from src.services.collection.relations.steps.merge import merge_all
from src.services.collection.relations.steps.persistence import persist_to_database, push_draft_to_dcs
from src.shared.decorators import announce


@announce("collecting relations: medium groups, general pool, between-groups")
def collect_relations(client) -> RelationsCollection:
    roster, isolate_set, medium_groups, large_groups, universe_id, alias_map = load_cast_data()
    medium_names = {g["name"] for g in medium_groups}
    all_groups = medium_groups + [g for g in large_groups if g["name"] not in medium_names]

    medium_per_group = collect_medium_groups(client, medium_groups, alias_map)
    general_rounds = collect_general_pool(client, roster, alias_map)
    cross_group = collect_cross_group_relations(client, roster, medium_groups, alias_map)
    group_relations, group_relations_dropped = collect_group_relations(client, all_groups)
    part_of_pairs, part_of_dropped = collect_group_hierarchy(client, all_groups)
    group_relations["part_of"] = part_of_pairs
    group_relations_dropped += part_of_dropped

    return RelationsCollection(
        roster=roster, isolate_set=isolate_set, medium_groups=medium_groups,
        large_groups=large_groups, all_groups=all_groups,
        medium_per_group=medium_per_group, general_rounds=general_rounds, cross_group=cross_group,
        group_relations=group_relations, group_relations_dropped=group_relations_dropped,
        universe_id=universe_id, alias_map=alias_map,
    )


@announce("merging passes and computing low-info characters")
def merge_and_analyze(collection: RelationsCollection) -> RelationsCollection:
    merged, dropped = merge_all(collection.medium_per_group, collection.general_rounds,
                                 collection.cross_group, collection.roster, collection.alias_map)
    low_info = compute_low_info(merged, collection.roster, collection.isolate_set)
    output = assemble_output(merged, dropped, collection.group_relations,
                              collection.group_relations_dropped, low_info, collection.general_rounds)

    collection.merged, collection.dropped = merged, dropped
    collection.low_info = low_info
    collection.output = output
    return collection


@announce("persisting and publishing to DCS")
def persist_and_publish(collection: RelationsCollection) -> RelationsCollection:
    persist_to_database(collection.group_relations, collection.universe_id)
    push_draft_to_dcs(
        collection.merged, collection.roster, collection.medium_groups, collection.large_groups,
        collection.isolate_set, set(collection.low_info), collection.group_relations, collection.universe_id)
    log_final_summary(collection.output, collection.roster)
    return collection
