"""Name matching, clustering, alias resolution, and roster building for
stage 1. Internals (normalize_name .. build_alias_pairs) are "almost
reliable" tools meant to run on a candidate pair someone already suspects is
a duplicate — not a discovery mechanism on their own; see where each is
called from, not here.
"""
import logging
from collections import Counter, defaultdict
from itertools import combinations

from src.infra.ai_clients.gemini_client import GeminiClient
from src.services.collection.cast.constants import (
    ALIAS_MIN_HITS, ALIAS_PASSES, ARC, CAST_PASSES, ROMANIZATION_MAP,
    ROSTER_MIN_PASSES, SPECIAL_CHAR_MAP, UNIVERSE_NAME,
)
from src.shared.decorators import announce, report

log = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    for special, plain in SPECIAL_CHAR_MAP.items():
        name = name.replace(special, plain)
    for pattern, repl in ROMANIZATION_MAP:
        name = name.replace(pattern, repl)
    return " ".join(name.split())


def name_key(name: str) -> frozenset:
    return frozenset(normalize_name(name).split())


def edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def classify_pair(key_a: frozenset, key_b: frozenset) -> str:
    shared = key_a & key_b
    only_a, only_b = key_a - shared, key_b - shared
    if not shared:
        return "alias"
    if len(only_a) == 1 and len(only_b) == 1:
        ta, tb = next(iter(only_a)), next(iter(only_b))
        if edit_distance(ta, tb) <= 2:
            return "spelling"
    return "ambiguous"


class UnionFind:
    def __init__(self, keys):
        self.parent = {k: k for k in keys}

    def find(self, k):
        while self.parent[k] != k:
            self.parent[k] = self.parent[self.parent[k]]
            k = self.parent[k]
        return k

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def consolidate(uf: UnionFind, canon: dict, presence: dict, mentions: Counter):
    groups = defaultdict(list)
    for k in canon:
        groups[uf.find(k)].append(k)

    new_canon, new_presence, new_mentions, aliases_of = {}, {}, Counter(), {}
    key_map = {}
    for members in groups.values():
        best = max(members, key=lambda k: mentions[k])
        new_canon[best] = canon[best]
        merged_presence = defaultdict(set)
        total = 0
        for m in members:
            key_map[m] = best
            total += mentions[m]
            for ct, passes in presence[m].items():
                merged_presence[ct] |= passes
        new_presence[best] = merged_presence
        new_mentions[best] = total
        others = sorted({canon[m] for m in members if m != best})
        if others:
            aliases_of[best] = others
    return new_canon, new_presence, new_mentions, key_map, aliases_of


def collect_names(results_by_type: dict[str, list[dict]]):
    display = defaultdict(Counter)
    presence = defaultdict(lambda: defaultdict(set))
    mentions = Counter()
    for cast_type, results in results_by_type.items():
        for pass_idx, pass_data in enumerate(results, start=1):
            if cast_type == "isolates":
                raw_names = list(pass_data.get("isolates", []))
            else:
                raw_names = [m for g in pass_data.get("groups", []) for m in g["members"]]
            for raw in raw_names:
                key = name_key(raw)
                display[key][normalize_name(raw)] += 1
                presence[key][cast_type].add(pass_idx)
                mentions[key] += 1
    canon = {key: sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
             for key, counter in display.items()}
    return canon, presence, mentions


@announce("extracting candidate names from raw passes")
@report(lambda r: f"raw_name_clusters={len(r[0])}")
def extract_candidate_names(raw_groups: dict[str, list[dict]]):
    return collect_names(raw_groups)


def find_spelling_pairs(canon: dict) -> list[tuple]:
    pairs = []
    for a, b in combinations(canon, 2):
        if a & b and classify_pair(a, b) == "spelling":
            pairs.append((a, b))
    return pairs


@announce("merging spelling variants (safe, unscoped — shared token + edit distance <=2)")
@report(lambda r: f"spelling_merges={r[4]}")
def merge_spelling_variants(canon: dict, presence: dict, mentions: Counter):
    spelling_pairs = find_spelling_pairs(canon)
    uf = UnionFind(canon.keys())
    for a, b in spelling_pairs:
        uf.union(a, b)
    new_canon, new_presence, new_mentions, key_map, _ = consolidate(uf, canon, presence, mentions)
    for a, b in spelling_pairs:
        log.info("SPELLING MERGE: %r <-> %r",
                  new_canon.get(key_map.get(a, a), a), new_canon.get(key_map.get(b, b), b))
    return new_canon, new_presence, new_mentions, key_map, len(spelling_pairs)


def find_ambiguous_pairs(canon: dict) -> list[dict]:
    ambiguous = []
    for a, b in combinations(canon, 2):
        if a & b and classify_pair(a, b) == "ambiguous":
            ambiguous.append({"a": canon[a], "b": canon[b], "shared": sorted(a & b)})
    return ambiguous


@announce("flagging ambiguous same-token name pairs for manual review (not merged)")
@report(lambda r: f"ambiguous_matches={len(r)}")
def flag_ambiguous_matches(canon: dict) -> list[dict]:
    ambiguous = find_ambiguous_pairs(canon)
    for pair in ambiguous:
        log.warning("AMBIGUOUS NAME MATCH (manual review, not merged): %r vs %r, shared=%s",
                    pair["a"], pair["b"], pair["shared"])
    return ambiguous


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


@announce("resolving aliases — dedicated LLM call, 3 independent passes")
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


def build_name_resolver(spelling_key_map: dict, alias_key_map: dict):
    def resolve(raw_name: str) -> frozenset:
        k = name_key(raw_name)
        k = spelling_key_map.get(k, k)
        return alias_key_map.get(k, k)
    return resolve


@announce("building roster (found_medium/large/isolate >= threshold in at least one type)")
@report(lambda r: f"roster_size={len(r)}")
def build_roster(canon: dict, presence: dict, mentions: Counter, aliases_of: dict, merged_groups: dict) -> list[dict]:
    roster = []
    for key, name in canon.items():
        found = {ct: len(presence[key].get(ct, set())) for ct in CAST_PASSES}
        if any(v >= ROSTER_MIN_PASSES for v in found.values()):
            group_count = sum(1 for gt in merged_groups for cl in merged_groups[gt] if key in cl["members"])
            roster.append({
                "name": name,
                "aliases": aliases_of.get(key, []),
                "found_medium": found["medium"],
                "found_large": found["large"],
                "found_isolate": found["isolates"],
                "group_count": group_count,
                "mention_count": mentions[key],
                "is_isolated": found["isolates"] >= ROSTER_MIN_PASSES,
            })
    roster.sort(key=lambda r: r["name"])
    return roster


def list_dropped_names(canon: dict, presence: dict, mentions: Counter, aliases_of: dict,
                        roster: list[dict], resolve) -> list[dict]:
    roster_keys = {resolve(r["name"]) for r in roster}
    return sorted(
        ({"name": canon[k],
          "aliases": aliases_of.get(k, []),
          "found_medium": len(presence[k].get("medium", set())),
          "found_large": len(presence[k].get("large", set())),
          "found_isolate": len(presence[k].get("isolates", set())),
          "mention_count": mentions[k]}
         for k in canon if resolve(canon[k]) not in roster_keys),
        key=lambda r: r["name"])
