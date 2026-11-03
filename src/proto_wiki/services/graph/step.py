"""Triples -> normalized graph (networkx) -> graph.json + graph.html (pyvis)."""
import json
import re
from collections import Counter
from pathlib import Path

import networkx as nx
from pyvis.network import Network

from ...domain.schemas import Graph, GraphEdge, GraphNode, Triple
from ...shared.decorators import logged

TYPE_COLORS = {
    "Character": "#4e79a7",
    "Organization": "#f28e2b",
    "Item": "#59a14f",
    "Concept": "#b07aa1",
    "Activity": "#e15759",
}
_CENTER_SIZE, _NODE_SIZE = 42, 22


def make_normalizer(character: str, aliases: dict[str, str]):
    """name -> canonical id. Order matters: the page character's own name
    parts ("Jiro", "Kyoka") win over wiki aliases, because on Kyoka Jiro's
    page a bare "Jiro" means her, even if some link aliases it to a relative."""
    alias_index = {a.casefold(): t for a, t in aliases.items()}
    parts = {p.casefold() for p in character.split() if len(p) > 1}
    full = character.casefold()

    def normalize(name: str) -> str:
        n = re.sub(r"\s+", " ", name).strip()
        n = re.sub(r"['’]s$", "", n)
        key = n.casefold()
        if key == full or key in parts:
            return character
        return alias_index.get(key, n)

    return normalize


def build_graph(triples: list[Triple], character: str, aliases: dict[str, str]) -> Graph:
    normalize_name = make_normalizer(character, aliases)
    spellings: dict[str, str] = {}

    def normalize(name: str) -> str:
        # names that differ only in case ("music" / "Music") are one node; the first spelling seen wins
        n = normalize_name(name)
        return spellings.setdefault(n.casefold(), n)

    node_types: dict[str, Counter] = {character: Counter()}
    edges: Counter = Counter()

    for t in triples:
        subject, obj = normalize(t.subject), normalize(t.object)
        if subject == obj:
            continue
        node_types.setdefault(subject, Counter())[t.subject_type] += 1
        node_types.setdefault(obj, Counter())[t.object_type] += 1
        edges[(subject, obj, t.relation)] += 1

    nodes = [
        GraphNode(id=name, type="Character" if name == character else types.most_common(1)[0][0])
        for name, types in node_types.items()
    ]
    return Graph(
        center=character,
        nodes=nodes,
        edges=[GraphEdge(source=s, target=o, relation=r, count=n) for (s, o, r), n in edges.items()],
    )


def to_networkx(graph: Graph) -> nx.DiGraph:
    g = nx.DiGraph()
    for n in graph.nodes:
        g.add_node(n.id, type=n.type)
    for e in graph.edges:
        # DiGraph holds one edge per (source, target): several relations
        # between the same pair are folded into one labelled edge.
        if g.has_edge(e.source, e.target):
            data = g[e.source][e.target]
            data["relations"].append((e.relation, e.count))
        else:
            g.add_edge(e.source, e.target, relations=[(e.relation, e.count)])
    return g


@logged(lambda _, graph, out_dir: f"Граф: {len(graph.nodes)} узлов, {len(graph.edges)} рёбер")
def write_graph(graph: Graph, out_dir: Path) -> None:
    (out_dir / "graph.json").write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    _write_html(to_networkx(graph), graph.center, out_dir / "graph.html")


def _write_html(g: nx.DiGraph, center: str, path: Path) -> None:
    # cdn_resources="in_line" embeds vis-network, so the page works offline.
    net = Network(height="100vh", width="100%", directed=True, bgcolor="#ffffff", cdn_resources="in_line")
    for name, data in g.nodes(data=True):
        is_center = name == center
        opts = dict(
            label=name, title=f"{name} ({data['type']})", color=TYPE_COLORS.get(data["type"], "#999999"),
            size=_CENTER_SIZE if is_center else _NODE_SIZE,
        )
        if is_center:
            # pinned to the middle of the canvas, everything else settles around it
            opts.update(x=0, y=0, fixed=True, borderWidth=4, color={"background": TYPE_COLORS["Character"],
                                                                    "border": "#222222"})
        net.add_node(name, **opts)
    for source, target, data in g.edges(data=True):
        label = ", ".join(r if n == 1 else f"{r} ×{n}" for r, n in data["relations"])
        net.add_edge(source, target, label=label, title=label, width=sum(n for _, n in data["relations"]))
    net.set_options(json.dumps({
        "physics": {"solver": "forceAtlas2Based", "forceAtlas2Based": {"gravitationalConstant": -120,
                                                                       "springLength": 180}},
        "edges": {"font": {"size": 11, "align": "middle"}, "arrows": {"to": {"enabled": True}}, "smooth": False},
        "nodes": {"font": {"size": 15}},
    }))
    net.write_html(str(path), notebook=False)

    legend = "".join(
        f'<div><span style="display:inline-block;width:12px;height:12px;border-radius:50%;'
        f'background:{color};margin-right:6px"></span>{node_type}</div>'
        for node_type, color in TYPE_COLORS.items()
    )
    html = path.read_text(encoding="utf-8")
    # pyvis's template always links Bootstrap from a CDN (cosmetic only);
    # drop it so the page makes no network requests.
    html = re.sub(r'<link\b[^>]*href="https?://[^>]*>', "", html)
    html = re.sub(r'<script\b[^>]*src="https?://[^>]*>\s*</script>', "", html)
    box = ('<div style="position:fixed;top:10px;left:10px;background:#fffffff0;border:1px solid #ccc;'
           f'border-radius:6px;padding:8px 12px;font:13px sans-serif;z-index:10">{legend}</div>')
    path.write_text(html.replace("</body>", box + "</body>", 1), encoding="utf-8")
