"""Registers the universe in Postgres and writes group_relations directly
(unreliable, handled by hand outside this codebase — not part of the DCS
review flow). Character relations are NOT written here anymore: a styled
graph draft goes to DCS for review instead, and the actual relations write
only happens once DCS confirms — see src/api/routes/confirm.py.
"""
import logging

from src.infra.dcs_client import push_graph_draft
from src.repository import RelationRepository, UniverseRepository
from src.services.collection.relations.constants import ARC, UNIVERSE_NAME
from src.services.graph.render import build_graph_draft, build_medium_groups, merge_relation_edges
from src.shared.decorators import announce

log = logging.getLogger(__name__)

_universe_repo = UniverseRepository()
_relation_repo = RelationRepository()


@announce("registering universe + group_relations in database")
def persist_to_database(group_relations, roster) -> int:
    # No universe_id available here (this stage runs independently of the
    # cast stage) — create_universe upserts on (name, arc), so calling it
    # again just returns the existing id, safe and idempotent. Character
    # relations are deliberately NOT written here anymore — see module
    # docstring.
    universe_id = _universe_repo.create_universe(UNIVERSE_NAME, roster, ARC)
    _relation_repo.save_group_relations(group_relations, universe_id)
    log.info("universe_id=%d", universe_id)
    return universe_id


@announce("pushing relation graph draft to DCS for review")
def push_draft_to_dcs(merged, roster, medium_groups, isolate_set, low_info_set, universe_id) -> None:
    characters = set(roster)
    excluded = isolate_set | low_info_set
    medium_group_shapes = build_medium_groups(medium_groups, characters, excluded)
    relation_edges = merge_relation_edges(merged, characters, isolate_set)
    draft = build_graph_draft(roster, relation_edges, medium_group_shapes, isolate_set, low_info_set)
    push_graph_draft(universe_id, UNIVERSE_NAME, ARC, draft["nodes"], draft["edges"])
