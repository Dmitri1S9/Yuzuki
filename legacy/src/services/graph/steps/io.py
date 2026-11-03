"""Loading the DCS-approved roster/groups/relations from Postgres and
preparing the plain data (nodes, edges, groups, degree, colors) both the
pyvis renderer and the DCS-facing draft builder draw from. Reads the
database directly rather than a stage's own leftover snapshot file, so this
always reflects the current approved state, including any edit made in DCS
after the stage that originally collected the data ran.
"""
import logging
from itertools import combinations

from src.domain.relation import GroupRelation, Relation
from src.repository import GroupRepository, RelationRepository, UniverseRepository
from src.services.collection.relations.steps.low_info import compute_low_info
from src.services.graph.steps.constants import ARC, NODE_PALETTE, RELATION_STYLE, UNIVERSE_NAME

log = logging.getLogger(__name__)
_universe_repo = UniverseRepository()
_relation_repo = RelationRepository()
_group_repo = GroupRepository()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")


def get_universe():
    universe = _universe_repo.get_universe(UNIVERSE_NAME, ARC)
    if universe is None:
        raise RuntimeError(
            f"universe {UNIVERSE_NAME!r}/{ARC!r} not found — run stage 1 (cast) and approve the "
            "roster in DCS before rendering its graph")
    return universe


def extract_roster_info(universe) -> tuple[list[str], set[str], set[str]]:
    characters = [c.get_name() for c in universe.get_roster()]
    isolate_set = {c.get_name() for c in universe.get_roster() if c.is_isolated()}
    return characters, set(characters), isolate_set


def _merged_relations_dict(relations: list[Relation]) -> dict:
    merged: dict[str, list[dict]] = {}
    for rel in relations:
        entry = {"members": rel.get_members()} if not rel.is_directed() \
            else {"source": rel.get_source(), "target": rel.get_target()}
        entry["count"] = rel.get_count()
        entry["source_level"] = rel.get_source_level()
        merged.setdefault(rel.get_type(), []).append(entry)
    return merged


def group_relations_dict(group_relations: list[GroupRelation]) -> dict:
    out: dict[str, list[list[str]]] = {}
    for gr in group_relations:
        out.setdefault(gr.get_kind(), []).append([gr.get_group_a(), gr.get_group_b()])
    return out


def load_low_info_set(universe, roster: list[str], characters: set[str]) -> set[str]:
    # Same source of truth stage2 uses to decide who to skip — 0 relations,
    # not a confirmed isolate — recomputed fresh from the database each time
    # rather than read from a stage's own snapshot, so the graph marker and
    # the collection exclusion never disagree, even after a later DCS edit.
    relations = _relation_repo.get_relations(universe.get_id())
    if not relations:
        return set()
    merged = _merged_relations_dict(relations)
    isolate_set = {c.get_name() for c in universe.get_roster() if c.is_isolated()}
    low_info = set(compute_low_info(merged, roster, isolate_set))
    return low_info & characters


def load_relation_edges(universe, characters: set[str], isolate_set: set[str]) -> list[dict]:
    relations = _merged_relations_dict(_relation_repo.get_relations(universe.get_id()))
    return merge_relation_edges(relations, characters, isolate_set)


def _group_to_dict(g) -> dict:
    return {"name": g.get_name(), "members": g.get_members()}


def prepare_graph_data(universe) -> dict:
    """Everything both the pyvis renderer (graph/pipeline.py, CLI) and the
    DCS-facing draft builder (api/routes/relations.py) need, from a Universe
    that's already been resolved by name+arc (CLI) or by id (API) — the one
    piece that differs between those two entry points."""
    characters, char_set, isolate_set = extract_roster_info(universe)
    low_info_set = load_low_info_set(universe, characters, char_set)
    excluded = isolate_set | low_info_set

    relation_edges = load_relation_edges(universe, char_set, isolate_set)
    medium_group_dicts = [_group_to_dict(g) for g in universe.get_groups() if g.get_type() == "medium"]
    large_group_dicts = [_group_to_dict(g) for g in universe.get_groups() if g.get_type() == "large"]
    medium_groups = build_medium_groups(medium_group_dicts, char_set, excluded)
    large_groups = build_large_groups(large_group_dicts, char_set, excluded)

    return {
        "characters": characters, "char_set": char_set, "isolate_set": isolate_set,
        "low_info_set": low_info_set, "relation_edges": relation_edges,
        "medium_group_dicts": medium_group_dicts, "large_group_dicts": large_group_dicts,
        "medium_groups": medium_groups, "large_groups": large_groups,
    }


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


def assign_node_colors(medium_groups: dict[str, set[str]]) -> dict[str, str]:
    node_colors: dict[str, str] = {}
    for i, (name, members) in enumerate(medium_groups.items()):
        color = NODE_PALETTE[i % len(NODE_PALETTE)]
        for m in members:
            node_colors.setdefault(m, color)  # first medium group wins on multi-membership
    return node_colors
