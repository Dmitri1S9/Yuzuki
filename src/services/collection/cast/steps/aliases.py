"""Alias resolution — a dedicated LLM call that links a hero name/codename/
title to a character's other name, confirmed by mutual or repeated
independent agreement (see ALIAS_MIN_HITS) so two unrelated minor
characters can't link by chance the way a structural near-match sometimes
can.
"""
import logging
from collections import Counter

from src.infra.ai_clients.gemini_client import GeminiClient
from src.services.collection.cast.steps.constants import ALIAS_MIN_HITS, ALIAS_PASSES, ARC, UNIVERSE_NAME
from src.services.collection.cast.steps.name_matching import UnionFind, consolidate, name_key
from src.shared.decorators import announce, report

log = logging.getLogger(__name__)


def collect_alias_hints(client: GeminiClient, names: list[str]) -> list[dict]:
    results = []
    for pass_number in range(1, ALIAS_PASSES + 1):
        log.info("  alias pass=%d ...", pass_number)
        results.append(client.alias_names(names, UNIVERSE_NAME, ARC, pass_number=pass_number))
    return results


def build_alias_pairs(alias_results: list[dict], canon: dict) -> list[tuple]:
    # rule 4: the claimed other name must already be a name we sent in (i.e.
    # something group extraction independently found) or it's discarded —
    # an invented name can't pass this.
    pair_counts = Counter()
    mutual_pairs = set()
    for result in alias_results:
        directed = set()
        for entry in result.get("entries", []):
            other = entry.get("other_name")
            if not other:
                continue
            key_a, key_b = name_key(entry["name"]), name_key(other)
            if key_a == key_b or key_b not in canon:
                continue
            directed.add((key_a, key_b))
        seen = set()
        for a, b in directed:
            undirected = tuple(sorted((a, b), key=lambda k: tuple(sorted(k))))
            seen.add(undirected)
            if (b, a) in directed:
                mutual_pairs.add(undirected)  # both sides named each other, same pass
        for pair in seen:
            pair_counts[pair] += 1
    return [pair for pair in pair_counts if pair_counts[pair] >= ALIAS_MIN_HITS or pair in mutual_pairs]


@announce("resolving aliases — dedicated LLM call")
@report(lambda r: f"aliases_detected={len(r[5])}")
def resolve_aliases(client: GeminiClient, canon: dict, presence: dict, mentions: Counter):
    # Applied before the roster threshold so a split character's counts
    # combine first. Confirmed by mutual, independent agreement (see
    # ALIAS_MIN_HITS) so two unrelated minor characters can't link by chance
    # the way a structural near-match sometimes can.
    alias_raw = collect_alias_hints(client, list(canon.values()))
    alias_pairs = build_alias_pairs(alias_raw, canon)
    for a, b in alias_pairs:
        log.warning("ALIAS LINKED: %r <-> %r", canon[a], canon[b])
    uf = UnionFind(canon.keys())
    for a, b in alias_pairs:
        uf.union(a, b)
    new_canon, new_presence, new_mentions, key_map, aliases_of = consolidate(uf, canon, presence, mentions)
    return new_canon, new_presence, new_mentions, key_map, aliases_of, alias_pairs
