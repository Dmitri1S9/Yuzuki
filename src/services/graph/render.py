"""Load stage 1/3's JSON handoff files and render the interactive pyvis
graphs. `Network(..., directed=True)` is required on both networks below —
pyvis silently drops any second edge between an already-connected node pair
when directed is left at its False default, regardless of relation type.
"""
import json
import logging
from itertools import combinations

from pyvis.network import Network

from src.services.graph.constants import (
    AREA_PALETTE, GROUP_RELATION_STYLE, NODE_PALETTE, RELATION_STYLE, SLUG,
)
from src.shared.paths import run_path

log = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")


def load_stage1() -> dict:
    with open(run_path(f"stage1_cast_{SLUG}.json"), encoding="utf-8") as f:
        return json.load(f)


def load_relations_merged() -> dict:
    with open(run_path(f"relations_merged_{SLUG}.json"), encoding="utf-8") as f:
        return json.load(f)


def extract_roster_info(stage1: dict) -> tuple[list[str], set[str], set[str]]:
    characters = [r["name"] for r in stage1["roster"]]
    isolate_set = {r["name"] for r in stage1["roster"] if r["is_isolated"]}
    return characters, set(characters), isolate_set


def load_low_info_set(characters: set[str]) -> set[str]:
    # Same source of truth stage2 uses to decide who to skip — 0 relations,
    # not a confirmed isolate. Computed once by stage3, read here rather
    # than re-derived, so the graph marker and the collection exclusion
    # never disagree.
    low_info = set(load_relations_merged().get("low_info_characters", []))
    return low_info & characters


def load_relation_edges(characters: set[str], isolate_set: set[str]) -> list[dict]:
    relations = load_relations_merged()["relations"]
    return merge_relation_edges(relations, characters, isolate_set)


def merge_relation_edges(relations: dict, characters: set[str], isolate_set: set[str]) -> list[dict]:
    """The merge logic load_relation_edges reads from disk for — split out
    so callers that already have `relations` in memory (e.g.
    relations/persistence.py building a DCS graph draft) don't need a JSON
    round-trip."""
    raw = []
    for rel_type, entries in relations.items():
        directed = RELATION_STYLE[rel_type]["directed"]
        for entry in entries:
            pairs = list(combinations(entry["members"], 2)) if "members" in entry \
                else [(entry["source"], entry["target"])]
            for a, b in pairs:
                if a not in characters or b not in characters:
                    continue
                if a in isolate_set or b in isolate_set:
                    continue
                raw.append((a, b, rel_type, entry["count"], entry["source_level"], directed))

    # The same (pair, type) relationship can be named by more than one raw
    # entry — medium and general_pool are independent collection levels and
    # both can surface it. Drawing one edge per raw entry stacked identical
    # curves exactly on top of each other, hiding all but the last one drawn
    # (this is why a node's title could say "6 relations" while only 2-3
    # lines were visible). Merge to one edge per (pair, type); every level's
    # count survives in the tooltip instead of being silently overdrawn.
    merged: dict[tuple, dict] = {}
    for a, b, rel_type, count, level, directed in raw:
        key = (a, b, rel_type) if directed else (frozenset((a, b)), rel_type)
        if key not in merged:
            merged[key] = {"a": a, "b": b, "rel_type": rel_type, "directed": directed, "levels": {}}
        merged[key]["levels"][level] = merged[key]["levels"].get(level, 0) + count
    return list(merged.values())


def build_medium_groups(groups_list: list[dict], characters: set[str], excluded: set[str]) -> dict[str, set[str]]:
    # excluded = isolates + low_info: neither has edges pulling them toward
    # their group-mates in the force layout, so including them would let one
    # stray node balloon the group's bounding box unpredictably.
    # groups_list: stage1's cast["groups"]["medium"] (or ["large"]) — a flat
    # list of {"name", "members", ...}, not the full stage1 dict, so callers
    # that already have just the list (e.g. relations/persistence.py, via
    # relations/io.load_cast_data) don't need the whole stage1 payload.
    groups = {}
    for g in groups_list:
        members = {m for m in g["members"] if m in characters and m not in excluded}
        if len(members) >= 2:
            groups[g["name"]] = members
    return groups


def build_large_groups(groups_list: list[dict], characters: set[str], excluded: set[str]) -> dict[str, set[str]]:
    groups = {}
    for g in groups_list:
        members = {m for m in g["members"] if m in characters and m not in excluded}
        if len(members) >= 2:
            groups[g["name"]] = members
    return groups


def compute_degree(characters: list[str], relation_edges: list[dict]) -> dict[str, int]:
    # Post-merge count — matches what's actually drawn, one per (pair, type).
    degree = {c: 0 for c in characters}
    for e in relation_edges:
        if e["a"] in degree:
            degree[e["a"]] += 1
        if e["b"] in degree:
            degree[e["b"]] += 1
    return degree


def inject_large_group_areas(out_path: str, large_groups: dict[str, set[str]],
                              area_colors: dict[str, str]) -> None:
    with open(out_path, encoding="utf-8") as f:
        html = f.read()

    groups_json = json.dumps({name: sorted(members) for name, members in large_groups.items()})
    colors_json = json.dumps(area_colors)

    extra = f"""
<script type="text/javascript">
window.addEventListener("load", function() {{
  var largeGroups = {groups_json};
  var largeColors = {colors_json};
  var names = Object.keys(largeGroups);
  var basePad = 45;

  function calcBox(ids, pad) {{
    var positions = network.getPositions(ids);
    var xs = [], ys = [];
    ids.forEach(function(id) {{
      if (positions[id]) {{ xs.push(positions[id].x); ys.push(positions[id].y); }}
    }});
    if (xs.length === 0) return null;
    return {{
      minX: Math.min.apply(null, xs) - pad, maxX: Math.max.apply(null, xs) + pad,
      minY: Math.min.apply(null, ys) - pad, maxY: Math.max.apply(null, ys) + pad,
    }};
  }}

  function overlaps(a, b) {{
    return a.minX < b.maxX && a.maxX > b.minX && a.minY < b.maxY && a.maxY > b.minY;
  }}

  network.on("beforeDrawing", function(ctx) {{
    // Areas must never visually overlap. Large groups are normally disjoint
    // (a character belongs to one side), but if physics ever puts two boxes
    // in conflict, shrink both together until they clear, down to a floor —
    // never draw two overlapping filled regions.
    var pad = basePad;
    var boxes = {{}};
    names.forEach(function(name) {{ boxes[name] = calcBox(largeGroups[name], pad); }});
    for (var iter = 0; iter < 8; iter++) {{
      var conflict = false;
      for (var i = 0; i < names.length; i++) {{
        for (var j = i + 1; j < names.length; j++) {{
          var a = boxes[names[i]], b = boxes[names[j]];
          if (a && b && overlaps(a, b)) {{
            conflict = true;
            var shrink = Math.max(pad - (iter + 1) * 6, 5);
            boxes[names[i]] = calcBox(largeGroups[names[i]], shrink);
            boxes[names[j]] = calcBox(largeGroups[names[j]], shrink);
          }}
        }}
      }}
      if (!conflict) break;
    }}
    names.forEach(function(name) {{
      var box = boxes[name];
      if (!box) return;
      ctx.save();
      ctx.strokeStyle = largeColors[name];
      ctx.fillStyle = largeColors[name] + "22";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.rect(box.minX, box.minY, box.maxX - box.minX, box.maxY - box.minY);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = largeColors[name];
      ctx.font = "bold 16px sans-serif";
      ctx.fillText(name, box.minX + 8, box.minY + 20);
      ctx.restore();
    }});
  }});
}});
</script>
"""
    html = html.replace("</body>", extra + "</body>")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)


def assign_node_colors(medium_groups: dict[str, set[str]]) -> dict[str, str]:
    node_colors: dict[str, str] = {}
    for i, (name, members) in enumerate(medium_groups.items()):
        color = NODE_PALETTE[i % len(NODE_PALETTE)]
        for m in members:
            node_colors.setdefault(m, color)  # first medium group wins on multi-membership
    return node_colors


def build_graph_draft(characters: list[str], relation_edges: list[dict],
                       medium_groups: dict[str, set[str]],
                       isolate_set: set[str], low_info_set: set[str]) -> dict:
    """The DCS-facing counterpart to render_graph: same node/edge styling
    (color by medium group, isolate/low_info markers, per-type edge style),
    but as plain JSON for React Flow instead of a pyvis HTML file."""
    node_colors = assign_node_colors(medium_groups)
    degree = compute_degree(characters, relation_edges)
    nodes = [
        {
            "name": c,
            "color": ("#bdc3c7" if c in isolate_set else
                      "#f4f6f7" if c in low_info_set else
                      node_colors.get(c, "#ffffff")),
            "is_isolate": c in isolate_set,
            "is_low_info": c in low_info_set,
            "degree": degree[c],
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

    log.info("wrote %s (%d low-info of %d characters)", out_path, len(low_info_set), len(characters))


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
    log.info("wrote %s", out_path)


def maybe_render_group_graph(merged: dict, medium_groups: dict[str, set[str]],
                              large_groups: dict[str, set[str]], out_path: str) -> None:
    group_relations = merged.get("group_relations")
    if not group_relations:
        log.info("no group_relations in relations_merged — skipping group graph")
        return
    render_group_graph(group_relations, medium_groups, large_groups, out_path)
