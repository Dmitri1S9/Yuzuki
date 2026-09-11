"""main.py — the instruction list for stage 4 (graph rendering, run manually
after the pipeline — not part of run_pipeline.sh). Read main() top to
bottom, nothing else; every step's own logic lives in render.py — see
ARCHITECTURE.md.
"""
from src.services.graph.constants import SLUG
from src.services.graph.render import (
    build_large_groups, build_medium_groups, configure_logging, extract_roster_info,
    load_low_info_set, load_relation_edges, load_relations_merged, load_stage1,
    maybe_render_group_graph, render_graph,
)
from src.shared.paths import run_path


def main():
    configure_logging()

    stage1 = load_stage1()
    characters, char_set, isolate_set = extract_roster_info(stage1)
    low_info_set = load_low_info_set(char_set)
    excluded = isolate_set | low_info_set

    relation_edges = load_relation_edges(char_set, isolate_set)
    medium_groups = build_medium_groups(stage1["groups"]["medium"], char_set, excluded)
    large_groups = build_large_groups(stage1["groups"]["large"], char_set, excluded)

    render_graph(characters, relation_edges, medium_groups, large_groups,
                 isolate_set, low_info_set, run_path(f"character_graph_{SLUG}.html"))

    merged = load_relations_merged()
    maybe_render_group_graph(merged, medium_groups, large_groups, run_path(f"group_graph_{SLUG}.html"))


if __name__ == "__main__":
    main()
