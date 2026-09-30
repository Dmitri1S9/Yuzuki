"""Same approach as graph_extract/resolve.py: exact name/alias match, plus a single unambiguous name-word
fallback (e.g. "Katsuki" alone), guarded against short/common words and cross-character collisions."""
from collections import Counter

from .settings import RosterEntry

_STOPWORDS = {"all", "for", "one", "high", "school", "class", "the", "of", "and", "league"}


def build_lookup(characters: tuple[RosterEntry, ...], groups: tuple[RosterEntry, ...]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    word_owner: Counter = Counter()
    word_to_canonical: dict[str, str] = {}
    for entry in (*characters, *groups):
        lookup[entry.name.casefold()] = entry.name
        for alias in entry.aliases:
            lookup[alias.casefold()] = entry.name
        for word in entry.name.split():
            w = word.casefold()
            if len(w) <= 3 or w in _STOPWORDS:
                continue
            word_owner[w] += 1
            word_to_canonical[w] = entry.name
    for word, count in word_owner.items():
        if count == 1 and word not in lookup:
            lookup[word] = word_to_canonical[word]
    return lookup


def canonicalize(name: str, lookup: dict[str, str]) -> str:
    return lookup.get(name.strip().casefold(), name.strip())
