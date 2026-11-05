"""Writes group_relations directly (unreliable, handled by hand outside this
codebase — not part of the DCS review flow). Character relations are NOT
written here anymore: a styled graph draft goes to DCS for review instead,
and the actual relations write only happens once DCS confirms — see
src/api/routes/confirm.py. The universe itself is already registered — its id
comes from load_cast_data() (steps/io.py), which requires the roster to
already be approved; re-deriving it here via create_universe(roster) would
re-add any character a human deleted from the roster during DCS review,
sourced from this stage's own (possibly stale) roster snapshot.
"""
import logging

from src.infra.dcs_client import push_graph_draft
from src.repository import RelationRepository
from src.services.collection.relations.steps.constants import ARC, UNIVERSE_NAME
from src.services.graph.steps.draft import build_graph_draft, build_group_graph_draft
from src.services.graph.steps.io import build_medium_groups, merge_relation_edges
from src.shared.decorators import announce

log = logging.getLogger(__name__)

_relation_repo = RelationRepository()


@announce("saving group_relations to database")
def persist_to_database(group_relations, universe_id: int) -> None:
    _relation_repo.save_group_relations(group_relations, universe_id, replace=True)


@announce("pushing relation graph draft to DCS for review")
def push_draft_to_dcs(merged, roster, medium_groups, large_groups, isolate_set, low_info_set,
                       group_relations, universe_id) -> None:
    characters = set(roster)
    excluded = isolate_set | low_info_set
    medium_group_shapes = build_medium_groups(medium_groups, characters, excluded)
    relation_edges = merge_relation_edges(merged, characters, isolate_set)
    draft = build_graph_draft(roster, relation_edges, medium_group_shapes, isolate_set, low_info_set)
    group_draft = build_group_graph_draft(medium_groups, large_groups, group_relations)
    push_graph_draft(universe_id, UNIVERSE_NAME, ARC, draft["nodes"], draft["edges"],
                      group_graph=group_draft)
