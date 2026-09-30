"""Kyoka Jiro's own page -> cleaned, sentence-split, section-tagged. Reuses yuzuki_local's dump reader and
wikitext cleaner (pure text/IO utilities, not flags/ordinals/classifications/Postgres)."""
import re
from dataclasses import dataclass

from yuzuki_local.external.dump_reader import DumpReader
from yuzuki_local.workers.wikitext_cleaner import WikiTextCleaner

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")
# Dotted acronyms ("U.A.", "U.S.J." -- two or more single capital letters each followed by a period) and
# "No." before a digit ("No. 30 Hero") would otherwise split mid-phrase; protect both generically rather
# than hardcoding every abbreviation this dump happens to use.
_ACRONYM = re.compile(r"\b(?:[A-Z]\.){2,}")
_NO_DOT = re.compile(r"\bNo\.(?=\s*\d)")
_DOT_PLACEHOLDER = "․"


@dataclass(frozen=True)
class Sentence:
    id: int
    section: str
    text: str


def _split(paragraph: str) -> list[str]:
    protected = paragraph.strip()
    protected = _ACRONYM.sub(lambda m: m.group(0).replace(".", _DOT_PLACEHOLDER), protected)
    protected = _NO_DOT.sub("No" + _DOT_PLACEHOLDER, protected)
    parts = _SENTENCE_SPLIT.split(protected)
    return [p.strip().replace(_DOT_PLACEHOLDER, ".") for p in parts if p.strip()]


def load_sentences(dump_path, page_title: str, drop_sections: tuple[str, ...]) -> list[Sentence]:
    dump = DumpReader(dump_path)
    text = next((p.text for p in dump.pages() if p.title == page_title), None)
    if text is None:
        raise ValueError(f"page {page_title!r} not found in dump")
    cleaner = WikiTextCleaner(min_paragraph_words=4)
    sections = [s for s in cleaner.sections(text) if s.name.strip().lower() not in drop_sections]
    sentences = []
    i = 0
    for sec in sections:
        for p in sec.paragraphs:
            for sent in _split(p):
                sentences.append(Sentence(i, sec.name, sent))
                i += 1
    return sentences
