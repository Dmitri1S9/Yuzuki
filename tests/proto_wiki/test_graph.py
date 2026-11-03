import json
import re

from proto_wiki.domain.schemas import Triple
from proto_wiki.services.graph.step import TYPE_COLORS, build_graph, write_graph

ALIASES = {"Kaminari": "Denki Kaminari", "Denki Kaminari": "Denki Kaminari", "Kyoka Jiro": "Kyoka Jiro",
           "Jiro": "Kyotoku Jiro"}  # a stray link alias must not beat the page character's own name part


def triple(subject, relation, obj, object_type, subject_type="Character"):
    return Triple(sentence_id=1, subject=subject, subject_type=subject_type, relation=relation, object=obj,
                  object_type=object_type, item_class="none", evidence="e", section="s")


def test_jiro_and_kaminari_normalize_to_full_names():
    graph = build_graph([
        triple("Jiro", "friend_of", "Kaminari", "Character"),
        triple("Kyoka", "friend_of", "denki kaminari", "Character"),
        triple("Kyoka Jiro", "enjoys", "Music", "Activity"),
    ], "Kyoka Jiro", ALIASES)
    ids = {n.id for n in graph.nodes}
    assert ids == {"Kyoka Jiro", "Denki Kaminari", "Music"}
    friend = next(e for e in graph.edges if e.relation == "friend_of")
    assert (friend.source, friend.target, friend.count) == ("Kyoka Jiro", "Denki Kaminari", 2)


def test_node_type_is_the_most_frequent_and_self_loops_are_dropped():
    graph = build_graph([
        triple("Kyoka", "pursues", "Music", "Concept"),
        triple("Kyoka", "enjoys", "Music", "Activity"),
        triple("Kyoka", "skilled_in", "Music", "Activity"),
        triple("Jiro", "friend_of", "Kyoka Jiro", "Character"),
    ], "Kyoka Jiro", {})
    assert next(n for n in graph.nodes if n.id == "Music").type == "Activity"
    assert all(e.source != e.target for e in graph.edges)


def test_names_differing_only_in_case_are_one_node():
    graph = build_graph([
        triple("Kyoka", "enjoys", "Music", "Activity"),
        triple("Kyoka", "skilled_in", "music", "Activity"),
    ], "Kyoka Jiro", {})
    assert sorted(n.id for n in graph.nodes) == ["Kyoka Jiro", "Music"]


def test_graph_html_has_center_pinned_and_colors_per_type(tmp_path):
    graph = build_graph([
        triple("Kyoka", "friend_of", "Denki Kaminari", "Character"),
        triple("Kyoka", "member_of", "U.A. High School", "Organization"),
        triple("Kyoka", "uses", "Guitar", "Item"),
        triple("Kyoka", "pursues", "Becoming a Hero", "Concept"),
        triple("Kyoka", "enjoys", "Music", "Activity"),
    ], "Kyoka Jiro", {})
    write_graph(graph, tmp_path)
    assert (tmp_path / "graph.json").exists()
    html = (tmp_path / "graph.html").read_text(encoding="utf-8")

    nodes = {n["id"]: n for n in json.loads(re.search(r"nodes = new vis\.DataSet\((\[.*?\])\);", html, re.S).group(1))}
    center = nodes["Kyoka Jiro"]
    assert center["fixed"] is True and center["x"] == 0 and center["y"] == 0

    def color(n):
        return n["color"]["background"] if isinstance(n["color"], dict) else n["color"]

    by_type = {"Character": "Denki Kaminari", "Organization": "U.A. High School", "Item": "Guitar",
               "Concept": "Becoming a Hero", "Activity": "Music"}
    assert {t: color(nodes[n]) for t, n in by_type.items()} == TYPE_COLORS
    assert len(set(TYPE_COLORS.values())) == 5
    assert all(c in html for c in TYPE_COLORS.values())  # legend
    assert not re.search(r'src="https?://', html)  # works offline
