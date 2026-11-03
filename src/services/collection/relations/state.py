"""The state pipeline.py's chapters carry between each other — kept out of
pipeline.py itself so that file stays nothing but the chapters' own flow.
"""
from dataclasses import dataclass, field


@dataclass
class RelationsCollection:
    roster: list = field(default_factory=list)
    isolate_set: set = field(default_factory=set)
    medium_groups: list = field(default_factory=list)
    large_groups: list = field(default_factory=list)
    all_groups: list = field(default_factory=list)
    medium_per_group: dict = field(default_factory=dict)
    general_rounds: list = field(default_factory=list)
    cross_group: dict = field(default_factory=dict)
    group_relations: dict = field(default_factory=dict)
    group_relations_dropped: list = field(default_factory=list)
    merged: dict = field(default_factory=dict)
    dropped: list = field(default_factory=list)
    low_info: list = field(default_factory=list)
    output: dict = field(default_factory=dict)
    universe_id: int | None = None
    alias_map: dict = field(default_factory=dict)
