"""The level between main.py's ladder and the real work — same convention
as the collection stages' pipeline.py files. Each chapter here is a flat
sequence of named calls into steps/, where the actual logic lives. State
carried between chapters lives in state.py, not here.
"""
from src.repository import RelationRepository
from src.services.graph.state import GraphData
from src.services.graph.steps.constants import SLUG
from src.services.graph.steps.io import get_universe, group_relations_dict, prepare_graph_data
from src.services.graph.steps.pyvis_render import maybe_render_group_graph, render_graph
from src.shared.decorators import announce
from src.shared.paths import run_path

_relation_repo = RelationRepository()


@announce("loading the approved roster/groups/relations and preparing them for rendering")
def load_and_prepare() -> GraphData:
    universe = get_universe()
    data = prepare_graph_data(universe)
    return GraphData(
        characters=data["characters"], char_set=data["char_set"], isolate_set=data["isolate_set"],
        low_info_set=data["low_info_set"], relation_edges=data["relation_edges"],
        medium_groups=data["medium_groups"], large_groups=data["large_groups"],
        universe_id=universe.get_id(),
    )


@announce("rendering the character graph and, when there's data for it, the group graph")
def render_graphs(data: GraphData) -> None:
    render_graph(data.characters, data.relation_edges, data.medium_groups, data.large_groups,
                 data.isolate_set, data.low_info_set, run_path(f"character_graph_{SLUG}.html"))

    group_relations = group_relations_dict(_relation_repo.get_group_relations(data.universe_id))
    maybe_render_group_graph(group_relations, data.medium_groups, data.large_groups,
                              run_path(f"group_graph_{SLUG}.html"))
