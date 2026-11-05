"""Group-to-group relations — allied/rival (undirected, deduped pairs) and
part_of (directed child/parent hierarchy). A separate table from character
relations, never merged into character edges.
"""
import logging

from src.services.collection.relations.steps.constants import ARC, UNIVERSE_NAME
from src.shared.decorators import logged


@logged(lambda _, kind, n_groups: f"group_relations       kind={kind:<6} n_groups={n_groups}")
def _log_group_relations_call(kind: str, n_groups: int) -> None:
    pass


@logged(lambda _, d: f"DROPPED group_relations {d}", level=logging.WARNING)
def _log_dropped_group_relation(d: dict) -> None:
    pass


@logged(lambda _, n_groups: f"group_hierarchy       n_groups={n_groups}")
def _log_group_hierarchy_call(n_groups: int) -> None:
    pass


@logged(lambda _, d: f"DROPPED group_hierarchy {d}", level=logging.WARNING)
def _log_dropped_group_hierarchy(d: dict) -> None:
    pass


def collect_group_relations(client, groups):
    """groups: combined large+medium group dicts. Two single-pass, temp=0
    calls (allied, rival) — result is a separate table, never merged into
    character edges."""
    group_names = {g["name"] for g in groups}
    result = {}
    dropped = []
    for kind in ("allied", "rival"):
        _log_group_relations_call(kind, len(groups))
        response = client.group_relations(kind, groups, UNIVERSE_NAME, ARC)
        pairs = []
        seen = set()
        for pair in response["pairs"]:
            if len(pair) != 2:
                dropped.append({"kind": kind, "pair": pair, "reason": "not a 2-element pair"})
                continue
            bad = [g for g in pair if g not in group_names]
            if bad:
                dropped.append({"kind": kind, "pair": pair, "not_in_groups": bad})
                continue
            key = tuple(sorted(pair))
            if key not in seen:
                seen.add(key)
                pairs.append(list(key))
        result[kind] = pairs
    for d in dropped:
        _log_dropped_group_relation(d)
    return result, dropped


def collect_group_hierarchy(client, groups):
    """groups: combined large+medium group dicts. One single-pass, temp=0
    call — (child, parent) pairs, directional, so unlike allied/rival these
    are never order-sorted or deduped as an unordered pair."""
    group_names = {g["name"] for g in groups}
    _log_group_hierarchy_call(len(groups))
    response = client.group_hierarchy(groups, UNIVERSE_NAME, ARC)
    pairs = []
    seen = set()
    dropped = []
    for pair in response["pairs"]:
        if len(pair) != 2:
            dropped.append({"kind": "part_of", "pair": pair, "reason": "not a 2-element pair"})
            continue
        child, parent = pair
        bad = [g for g in pair if g not in group_names]
        if bad:
            dropped.append({"kind": "part_of", "pair": pair, "not_in_groups": bad})
            continue
        if child == parent:
            dropped.append({"kind": "part_of", "pair": pair, "reason": "group can't be part of itself"})
            continue
        key = (child, parent)
        if key not in seen:
            seen.add(key)
            pairs.append([child, parent])
    for d in dropped:
        _log_dropped_group_hierarchy(d)
    return pairs, dropped
