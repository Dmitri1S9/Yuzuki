"""The state pipeline.py's chapters carry between each other — kept out of
pipeline.py itself so that file stays nothing but the chapters' own flow.
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CastCollection:
    canon: dict = field(default_factory=dict)
    presence: dict = field(default_factory=dict)
    mentions: Counter = field(default_factory=Counter)
    raw_groups: dict = field(default_factory=dict)
    raw_cluster_count: int = 0
    spelling_merge_count: int = 0
    ambiguous_matches: list = field(default_factory=list)
    alias_pairs: list = field(default_factory=list)
    aliases_of: dict = field(default_factory=dict)
    anilist_names: list = field(default_factory=list)
    anilist_added: list = field(default_factory=list)
    resolve: Callable[[str], frozenset] | None = None
    merged_groups: dict = field(default_factory=dict)
    roster: list = field(default_factory=list)
    groups_out: dict = field(default_factory=dict)
