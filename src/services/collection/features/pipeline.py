"""The level between main.py's ladder and the real work — same convention
as cast/pipeline.py and relations/pipeline.py. Each chapter here is a flat
sequence of named calls into steps/ (collection.py, merge.py, io.py,
persistence.py), where the actual logic (loops, branching, API calls)
lives. No loop, branch, or try/except belongs in this file. State carried
between chapters lives in state.py, not here.
"""
from src.domain.parameters import FLAG_PARAMS, ORDINAL_PARAMS, PROFILE_PARAMS, all_param_names
from src.services.collection.features.state import FeatureCollection
from src.services.collection.features.steps.collection import collect_or_load_passes, collect_profile
from src.services.collection.features.steps.io import (
    assemble_output, get_universe, load_low_info_set, log_consensus_summary,
)
from src.services.collection.features.steps.merge import (
    apply_low_info_mask, compute_null_share, maybe_log_legacy_comparison,
)
from src.services.collection.features.steps.persistence import (
    persist_features_to_database, push_report_to_dcs,
)
from src.services.consensus.flag_consensus import merge_flag_consensus
from src.services.consensus.ordinal_consensus import merge_ordinal_consensus
from src.shared.decorators import announce


@announce("preparing roster and collecting (or reusing) ordinal/flag passes")
def prepare_and_collect(client) -> FeatureCollection:
    universe = get_universe()
    roster = [c.get_name() for c in universe.get_roster()]
    # A well-known character can go unrecognized by bare name alone (a
    # civilian identity vs. a codename, a native-language name) — collected
    # here from the same aliases cast/steps/aliases.py already populates
    # for free from AniList, and fed into rank()/flag()'s "characters" list
    # as "Name (aka Alias)" so the model has a real shot at placing them
    # correctly instead of guessing blind. See naming.display_name().
    alias_map = {c.get_name(): c.get_aliases() for c in universe.get_roster()}
    low_info_set = load_low_info_set(universe, roster)
    collect_roster = [n for n in roster if n not in low_info_set]
    ordinal_names, flag_names = list(ORDINAL_PARAMS), list(FLAG_PARAMS)

    per_pass = collect_or_load_passes(client, universe.get_id(), collect_roster, ordinal_names, flag_names, alias_map)

    return FeatureCollection(
        roster=roster, low_info_set=low_info_set, collect_roster=collect_roster,
        ordinal_names=ordinal_names, flag_names=flag_names, params=all_param_names(),
        per_pass=per_pass, universe_id=universe.get_id(),
    )


@announce("building consensus, features, and profile")
def build_consensus_and_features(client, collection: FeatureCollection) -> FeatureCollection:
    # Both ordinals and flags are 2 passes now, but go through different
    # consensus algorithms: flags (2-3 tiers) use flag_consensus's cheap
    # exact-match blocks; ordinals (8-10 tiers) need real reconciliation
    # when two passes land a character one tier apart, not just
    # exact-match-or-nothing — see ordinal_consensus.py's own docstring for
    # why (confirmed live: the exact-match rule collapsed most ordinals for
    # Bunny Girl Senpai into one undifferentiated block).
    ordinal_merged, ordinal_quality = merge_ordinal_consensus(
        collection.per_pass, collection.collect_roster, collection.ordinal_names)
    flag_merged, flag_quality = merge_flag_consensus(
        collection.per_pass, collection.collect_roster, collection.flag_names)
    merged = {name: {**ordinal_merged[name], **flag_merged[name]} for name in collection.collect_roster}
    quality = {**ordinal_quality, **flag_quality}
    maybe_log_legacy_comparison(collection.per_pass, collection.collect_roster, collection.params,
                                 merged, quality)

    null_share = compute_null_share(merged, collection.collect_roster, collection.params)
    features = apply_low_info_mask(merged, collection.roster, collection.low_info_set)

    profile_raw = collect_profile(client, collection.collect_roster)
    profile = apply_low_info_mask(profile_raw, collection.roster, collection.low_info_set)

    collection.merged, collection.quality = merged, quality
    collection.null_share = null_share
    collection.features = features
    collection.profile = profile
    return collection


@announce("assembling output, persisting, and publishing to DCS")
def assemble_and_publish(collection: FeatureCollection) -> FeatureCollection:
    output = assemble_output(
        collection.roster, collection.low_info_set, collection.ordinal_names, collection.flag_names,
        list(PROFILE_PARAMS), collection.features, collection.profile, collection.null_share,
        collection.quality)
    persist_features_to_database(
        collection.features, collection.ordinal_names + collection.flag_names, collection.roster)
    push_report_to_dcs(collection.quality, collection.roster)
    log_consensus_summary(collection.quality, collection.params)

    collection.output = output
    return collection
