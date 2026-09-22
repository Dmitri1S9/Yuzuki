"""Group-to-group relations — allied/rival (undirected, deduped pairs) and
part_of (directed child/parent hierarchy). A separate table from character
relations, never merged into character edges.
"""
import logging

from src.services.collection.relations.steps.constants import ARC, UNIVERSE_NAME

log = logging.getLogger(__name__)


def collect_group_relations(client, groups):
    """groups: combined large+medium group dicts. Two single-pass, temp=0
    calls (allied, rival) — result is a separate table, never merged into
    character edges."""
    group_names = {g["name"] for g in groups}
    result = {}
    dropped = []
    for kind in ("allied", "rival"):
        log.info("group_relations       kind=%-6s n_groups=%d", kind, len(groups))
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
        log.warning("DROPPED group_relations %s", d)
    return result, dropped


def collect_group_hierarchy(client, groups):
    """groups: combined large+medium group dicts. One single-pass, temp=0
    call — (child, parent) pairs, directional, so unlike allied/rival these
    are never order-sorted or deduped as an unordered pair."""
    group_names = {g["name"] for g in groups}
    log.info("group_hierarchy       n_groups=%d", len(groups))
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
        log.warning("DROPPED group_hierarchy %s", d)
    return pairs, dropped
