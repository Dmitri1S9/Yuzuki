"""The state pipeline.py's chapters carry between each other — kept out of
pipeline.py itself so that file stays nothing but the chapters' own flow.
"""
from dataclasses import dataclass, field


@dataclass
class FeatureCollection:
    roster: list = field(default_factory=list)
    low_info_set: set = field(default_factory=set)
    collect_roster: list = field(default_factory=list)
    ordinal_names: list = field(default_factory=list)
    flag_names: list = field(default_factory=list)
    params: list = field(default_factory=list)
    per_pass: dict = field(default_factory=dict)
    merged: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    null_share: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)
    profile: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    universe_id: int | None = None
