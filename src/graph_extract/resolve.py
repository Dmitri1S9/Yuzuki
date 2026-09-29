"""Snaps a subject/object name to its canonical roster form when it's an exact (case-insensitive) match on
a known name, alias, or a single unambiguous name-word from one (e.g. "Katsuki" or "Eijiro" alone -- the
model resolves aliases itself per the prompt, but sometimes uses a bare first/last name instead of the full
canonical form; only a word that belongs to exactly one roster entry is used this way, so it never merges
two different people who happen to share a first or last name (Kyoka/Kyotoku/Mika Jiro all share "Jiro" --
that word is correctly left out of the fallback)."""
from collections import Counter

from .settings import RosterEntry

# Words too generic to use as a bare-word match even when only one roster entry contains them (e.g. "All"
# from "All For One", "High"/"School" from "U.A. High School") -- short/common words are excluded outright.
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


def canonicalize(name: str, lookup: dict[str, str]) -> tuple[str, bool]:
    """(resolved name, was_in_roster)."""
    hit = lookup.get(name.strip().casefold())
    return (hit, True) if hit else (name.strip(), False)
