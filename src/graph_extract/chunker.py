"""Cleaned wiki sections -> sentence-bounded chunks. Pure text processing, no I/O, no LLM."""
import re
from dataclasses import dataclass

# Reuses yuzuki_local's wikitext cleaner: pure text processing (strips infoboxes/navboxes/tables/refs,
# groups by section), not flags/ordinals/classifications/Postgres.
from yuzuki_local.entities.wiki import WikiSection

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")


@dataclass(frozen=True)
class Chunk:
    section: str
    text: str
    sentence_count: int


_UA_PLACEHOLDER = "U․A․"  # protects "U.A." (U.A. High School) from being split mid-abbreviation


def _sentences(paragraph: str) -> list[str]:
    protected = paragraph.strip().replace("U.A.", _UA_PLACEHOLDER)
    return [s.strip().replace(_UA_PLACEHOLDER, "U.A.") for s in _SENTENCE_SPLIT.split(protected) if s.strip()]


def chunk_sections(sections: list[WikiSection], min_sentences: int, max_sentences: int) -> list[Chunk]:
    """Main strategy: group each section's sentences into chunks of min-max sentences, in reading order.
    A trailing group smaller than min_sentences merges into the previous chunk (never dropped)."""
    chunks: list[Chunk] = []
    for sec in sections:
        sentences = [s for p in sec.paragraphs for s in _sentences(p)]
        i = 0
        group: list[str] = []
        while i < len(sentences):
            group = sentences[i:i + max_sentences]
            i += max_sentences
            if len(group) < min_sentences and chunks and chunks[-1].section == sec.name:
                prev = chunks.pop()
                group = _sentences(prev.text) + group
            chunks.append(Chunk(sec.name, " ".join(group), len(group)))
    return chunks


def chunk_sentence_plus_neighbors(sections: list[WikiSection]) -> list[Chunk]:
    """Alt strategy for the stage-4 comparison: one sentence + its immediate neighbor on each side (up to
    3 sentences), centered on every sentence -- heavy overlap, by design, to see if narrow context changes
    coreference/edge yield versus the 3-8 sentence main strategy."""
    chunks: list[Chunk] = []
    for sec in sections:
        sentences = [s for p in sec.paragraphs for s in _sentences(p)]
        for i in range(len(sentences)):
            window = sentences[max(0, i - 1):i + 2]
            chunks.append(Chunk(sec.name, " ".join(window), len(window)))
    return chunks
