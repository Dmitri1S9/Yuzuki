"""The actual interactive pyvis HTML rendering. `Network(..., directed=True)`
is required on both networks below — pyvis silently drops any second edge
between an already-connected node pair when directed is left at its False
default, regardless of relation type.
"""
from pyvis.network import Network

from src.services.graph.steps.constants import AREA_PALETTE, GROUP_RELATION_STYLE, RELATION_STYLE
from src.services.graph.steps.io import assign_node_colors, compute_degree
from src.services.graph.steps.overlay import inject_large_group_areas
from src.shared.decorators import logged


@logged(lambda _, characters, relation_edges, medium_groups, large_groups, isolate_set, low_info_set, out_path:
        f"wrote {out_path} ({len(low_info_set)} low-info of {len(characters)} characters)")
def render_graph(characters: list[str], relation_edges: list[dict],
                  medium_groups: dict[str, set[str]], large_groups: dict[str, set[str]],
                  isolate_set: set[str], low_info_set: set[str], out_path: str) -> None:
    node_colors = assign_node_colors(medium_groups)
    degree = compute_degree(characters, relation_edges)

    net = Network(height="900px", width="100%", directed=True, notebook=False, cdn_resources="in_line")
    for c in characters:
        if c in isolate_set:
            color, border, dashes, title = "#bdc3c7", "#555555", [4, 4], "confirmed isolate"
        elif c in low_info_set:
            color, border, dashes, title = "#f4f6f7", "#cccccc", [1, 3], "low information — 0 relations found"
        else:
            color = node_colors.get(c, "#ffffff")
            border = "#555555"
            dashes = [4, 4] if degree[c] == 1 else False
            title = f"{degree[c]} relation(s)"
        net.add_node(
            c, label=c, title=title, color={"background": color, "border": border},
            borderWidth=2, shapeProperties={"borderDashes": dashes},
        )

    for e in relation_edges:
        style = RELATION_STYLE[e["rel_type"]]
        max_count = max(e["levels"].values())
        breakdown = ", ".join(f"{lvl.split(':')[0]}:{c}" for lvl, c in sorted(e["levels"].items()))
        net.add_edge(
            e["a"], e["b"],
            color=style["color"],
            arrows="to" if style["directed"] else "",
            width=1 + min(max_count, 5) * 0.4,  # thin — count can now run up to 9 (general_pool, 3 rounds x 3 passes)
            title=f"{e['rel_type']} ({breakdown})",
            smooth=style["smooth"],
        )

    net.set_options("""
    {
      "physics": {
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {"gravitationalConstant": -100, "springLength": 150, "avoidOverlap": 1},
        "stabilization": {"iterations": 300}
      }
    }
    """)

    net.write_html(out_path)

    area_colors = {name: AREA_PALETTE[i % len(AREA_PALETTE)] for i, name in enumerate(large_groups)}
    inject_large_group_areas(out_path, large_groups, area_colors)


@logged(lambda _, group_relations, medium_groups, large_groups, out_path: f"wrote {out_path}")
def render_group_graph(group_relations: dict, medium_groups: dict[str, set[str]],
                        large_groups: dict[str, set[str]], out_path: str) -> None:
    all_groups = set(medium_groups) | set(large_groups)
    for kind_pairs in group_relations.values():
        for a, b in kind_pairs:
            all_groups.add(a)
            all_groups.add(b)

    net = Network(height="700px", width="100%", directed=True, notebook=False, cdn_resources="in_line")
    for name in sorted(all_groups):
        is_large = name in large_groups
        size = 30 + 2 * len(large_groups.get(name, medium_groups.get(name, [])))
        net.add_node(
            name, label=name,
            color={"background": "#f39c12" if is_large else "#3498db", "border": "#555555"},
            shape="box" if is_large else "dot",
            size=size,
        )

    for kind, pairs in group_relations.items():
        style = GROUP_RELATION_STYLE[kind]
        for a, b in pairs:
            if a not in all_groups or b not in all_groups:
                continue
            net.add_edge(a, b, color=style["color"], title=kind, width=3)

    net.set_options("""
    {
      "physics": {
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {"gravitationalConstant": -150, "springLength": 250, "avoidOverlap": 1},
        "stabilization": {"iterations": 300}
      }
    }
    """)
    net.write_html(out_path)


@logged(lambda _: "no group_relations in database — skipping group graph")
def _log_no_group_relations() -> None:
    pass


def maybe_render_group_graph(group_relations: dict, medium_groups: dict[str, set[str]],
                              large_groups: dict[str, set[str]], out_path: str) -> None:
    if not group_relations:
        _log_no_group_relations()
        return
    render_group_graph(group_relations, medium_groups, large_groups, out_path)
