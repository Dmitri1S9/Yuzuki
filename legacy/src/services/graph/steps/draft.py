"""The DCS-facing counterparts to the pyvis renderer — same node/edge
styling (color by medium group, isolate/low_info markers, per-type edge
style, allied/rival group coloring), but as plain JSON for React Flow
instead of a rendered HTML file.
"""
from src.services.graph.steps.constants import GROUP_RELATION_STYLE, RELATION_STYLE
from src.services.graph.steps.io import assign_node_colors, compute_degree


def build_graph_draft(characters: list[str], relation_edges: list[dict],
                       medium_groups: dict[str, set[str]],
                       isolate_set: set[str], low_info_set: set[str]) -> dict:
    node_colors = assign_node_colors(medium_groups)
    degree = compute_degree(characters, relation_edges)
    # Full membership list, not just assign_node_colors' first-group-wins
    # color — DCS needs every group a character belongs to to filter by
    # "only this group" / "only between groups" (a character in >1 group
    # can't be reduced to a single membership for that).
    membership = {
        c: sorted(name for name, members in medium_groups.items() if c in members)
        for c in characters
    }
    nodes = [
        {
            "name": c,
            "color": ("#bdc3c7" if c in isolate_set else
                      "#f4f6f7" if c in low_info_set else
                      node_colors.get(c, "#ffffff")),
            "is_isolate": c in isolate_set,
            "is_low_info": c in low_info_set,
            "degree": degree[c],
            "groups": membership[c],
        }
        for c in characters
    ]
    edges = [
        {
            "source": e["a"], "target": e["b"], "type": e["rel_type"],
            "directed": e["directed"], "levels": e["levels"],
            "color": RELATION_STYLE[e["rel_type"]]["color"],
        }
        for e in relation_edges
    ]
    return {"nodes": nodes, "edges": edges}


def build_group_graph_draft(medium_groups_list: list[dict], large_groups_list: list[dict],
                             group_relations: dict) -> dict:
    medium_names = {g["name"] for g in medium_groups_list}
    large_names = {g["name"] for g in large_groups_list}
    sizes = {g["name"]: len(g["members"]) for g in medium_groups_list + large_groups_list}

    all_groups = medium_names | large_names
    for pairs in group_relations.values():
        for a, b in pairs:
            all_groups.add(a)
            all_groups.add(b)

    nodes = [
        {"name": name, "is_large": name in large_names, "size": sizes.get(name, 1)}
        for name in sorted(all_groups)
    ]
    edges = [
        {"group_a": a, "group_b": b, "kind": kind, "color": GROUP_RELATION_STYLE[kind]["color"]}
        for kind, pairs in group_relations.items()
        for a, b in pairs
        if a in all_groups and b in all_groups
    ]
    return {"nodes": nodes, "edges": edges}
