"""Name normalization, clustering, and candidate extraction from raw
group-collection passes. Internals (normalize_name..classify_pair) are
"almost reliable" tools meant to run on a candidate pair someone already
suspects is a duplicate — not a discovery mechanism on their own; see
where each is called from, not here.
"""
import logging
from collections import Counter, defaultdict
from itertools import combinations

from src.services.collection.cast.steps.constants import ROMANIZATION_MAP, SPECIAL_CHAR_MAP
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


def build_name_resolver(spelling_key_map: dict, alias_key_map: dict):
    def resolve(raw_name: str) -> frozenset:
        k = name_key(raw_name)
        k = spelling_key_map.get(k, k)
        return alias_key_map.get(k, k)
    return resolve
