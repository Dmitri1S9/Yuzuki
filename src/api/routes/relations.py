"""GET-only route for viewing an already-approved universe's relation graph
at any time — not just once, during GraphReview's pending-queue window.
Reuses graph/steps/io.py's prepare_graph_data (the same shaping logic the
pyvis renderer and the original pending-review draft both use) and
graph/steps/draft.py's build_graph_draft/build_group_graph_draft, so the
response is the same node/edge JSON shape DCS's GraphReview already knows
how to render — sourced from the current database state, so it always
reflects any edit made after the original relations stage ran.
"""
from fastapi import APIRouter, HTTPException

from src.repository import RelationRepository, UniverseRepository
from src.services.graph.steps.draft import build_graph_draft, build_group_graph_draft
from src.services.graph.steps.io import group_relations_dict, prepare_graph_data

router = APIRouter(tags=["relations"])

_universe_repo = UniverseRepository()
_relation_repo = RelationRepository()


@router.get("/universes/{universe_id}/relations")
def get_relations(universe_id: int):
    universe = _universe_repo.get_universe_by_id(universe_id)
    if universe is None:
        raise HTTPException(status_code=404, detail=f"universe {universe_id} not found")

    data = prepare_graph_data(universe)
    draft = build_graph_draft(
        data["characters"], data["relation_edges"], data["medium_groups"],
        data["isolate_set"], data["low_info_set"])
    group_relations = group_relations_dict(_relation_repo.get_group_relations(universe_id))
    group_draft = build_group_graph_draft(data["medium_group_dicts"], data["large_group_dicts"], group_relations)

    return {"nodes": draft["nodes"], "edges": draft["edges"], "group_graph": group_draft}
