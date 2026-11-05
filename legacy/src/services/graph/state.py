"""The state pipeline.py's chapters carry between each other — kept out of
pipeline.py itself so that file stays nothing but the chapters' own flow.
"""
from dataclasses import dataclass, field


@dataclass
class GraphData:
    characters: list = field(default_factory=list)
    char_set: set = field(default_factory=set)
    isolate_set: set = field(default_factory=set)
    low_info_set: set = field(default_factory=set)
    relation_edges: list = field(default_factory=list)
    medium_groups: list = field(default_factory=list)
    large_groups: list = field(default_factory=list)
    universe_id: int | None = None
