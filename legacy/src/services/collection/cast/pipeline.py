"""The level between main.py's ladder and the real work. main.py names the
4 chapters of stage 1; each chapter here is itself nothing but a named
sequence of calls into steps/ (roster.py/groups.py/images.py/output.py/
persistence.py), where the actual logic (loops, branching, API calls)
lives. Reading top to bottom: main.py says WHAT happens, this file says
WHAT each part of that consists of, and the functions it calls say HOW.
No function in this file contains a loop, a branch, or a try/except —
that's the signal something here has stopped being pure orchestration and
belongs one level deeper instead. State carried between chapters lives in
state.py, not here.
"""
from src.services.collection.cast.state import CastCollection
from src.services.collection.cast.steps.aliases import merge_anilist_aliases
from src.services.collection.cast.steps.anime_db import fetch_cast_aliases, fetch_cast_names
from src.services.collection.cast.steps.constants import ANILIST_TITLE
from src.services.collection.cast.steps.groups import (
    collect_raw_groups, consolidate_groups, format_groups_for_output,
    synthesize_large_group_from_cast,
)
from src.services.collection.cast.steps.images import collect_character_images, persist_character_images
from src.services.collection.cast.steps.name_matching import (
    build_name_resolver, extract_candidate_names, flag_ambiguous_matches, merge_spelling_variants,
)
from src.services.collection.cast.steps.output import assemble_output, log_final_summary
from src.services.collection.cast.steps.persistence import persist_to_database, push_draft_to_dcs
from src.services.collection.cast.steps.roster import build_roster, merge_anilist_names
from src.shared.decorators import announce


@announce("collecting candidates: AniList's cast list, then the model's own blind passes")
def collect_candidates(client) -> CastCollection:
    anilist_names = fetch_cast_names(ANILIST_TITLE)
    raw_groups = collect_raw_groups(client, anilist_names)
    canon, presence, mentions = extract_candidate_names(raw_groups)

    return CastCollection(
        canon=canon, presence=presence, mentions=mentions,
        raw_groups=raw_groups, raw_cluster_count=len(canon),
        anilist_names=anilist_names,
    )


@announce("reconciling names: spelling, ambiguity, aliases, AniList backstop")
def reconcile_names(collection: CastCollection) -> CastCollection:
    canon, presence, mentions, spelling_key_map, spelling_merge_count = merge_spelling_variants(
        collection.canon, collection.presence, collection.mentions)
    ambiguous_matches = flag_ambiguous_matches(canon)
    resolve = build_name_resolver(spelling_key_map, {})
    aliases_of = merge_anilist_aliases(canon, resolve, fetch_cast_aliases(ANILIST_TITLE))
    canon, presence, mentions, anilist_added = merge_anilist_names(
        canon, presence, mentions, collection.anilist_names)

    collection.canon, collection.presence, collection.mentions = canon, presence, mentions
    collection.spelling_merge_count = spelling_merge_count
    collection.ambiguous_matches = ambiguous_matches
    collection.aliases_of = aliases_of
    collection.anilist_added = anilist_added
    collection.resolve = resolve
    return collection


@announce("building the roster and its groups")
def build_roster_and_groups(collection: CastCollection) -> CastCollection:
    merged_groups = consolidate_groups(collection.raw_groups, collection.resolve)
    merged_groups = synthesize_large_group_from_cast(
        merged_groups, collection.anilist_names, collection.canon, collection.resolve)
    roster = build_roster(
        collection.canon, collection.presence, collection.mentions, collection.aliases_of,
        merged_groups, anilist_confirmed=set(collection.anilist_added))
    groups_out = format_groups_for_output(merged_groups, collection.canon)

    collection.merged_groups = merged_groups
    collection.roster = roster
    collection.groups_out = groups_out
    return collection


@announce("assembling output, persisting, and publishing to DCS")
def assemble_and_publish(collection: CastCollection) -> dict:
    output = assemble_output(
        collection.roster, collection.groups_out, collection.raw_cluster_count,
        collection.spelling_merge_count, collection.aliases_of, collection.canon,
        collection.ambiguous_matches, collection.presence)

    universe_id = persist_to_database(output)
    collect_character_images(output["roster"])
    persist_character_images(universe_id, output["roster"])
    push_draft_to_dcs(output, universe_id)
    log_final_summary(output)
    return output
