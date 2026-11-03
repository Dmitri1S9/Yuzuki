"""Param — one parameters.json entry, entirely built from that JSON so a
change to prompt text/tiers there never touches code. Built by
services/parsing/params_loader.py."""
from dataclasses import dataclass, field


@dataclass
class Param:
    name: str
    ordinal: bool
    definition: str
    tiers: list[str]  # includes "unknown" last
    sort_axis: str | None = None
    tier_descriptions: dict[str, str] = field(default_factory=dict)
