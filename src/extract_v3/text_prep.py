"""Kyoka Jiro's pages (main article + Relationships + Synopsis) -> cleaned, sentence-split, page+section
tagged. Reads pages in a fixed, stable order (as given) so existing sentence ids -- and any checkpoint keyed
by them -- stay valid if a later page is appended to the list."""
import re
from dataclasses import dataclass

from .external.dump_reader import DumpReader
from .external.wikitext_cleaner import WikiTextCleaner

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
    page: str
    section: str
    text: str


def _split(paragraph: str) -> list[str]:
    protected = paragraph.strip()
    protected = _ACRONYM.sub(lambda m: m.group(0).replace(".", _DOT_PLACEHOLDER), protected)
    protected = _NO_DOT.sub("No" + _DOT_PLACEHOLDER, protected)
    parts = _SENTENCE_SPLIT.split(protected)
    return [p.strip().replace(_DOT_PLACEHOLDER, ".") for p in parts if p.strip()]


def load_sentences(dump_path, page_titles: tuple[str, ...], drop_sections: tuple[str, ...]) -> list[Sentence]:
    dump = DumpReader(dump_path)
    wanted = set(page_titles)
    texts = {p.title: p.text for p in dump.pages() if p.title in wanted}
    missing = wanted - set(texts)
    if missing:
        raise ValueError(f"page(s) not found in dump: {missing}")
    cleaner = WikiTextCleaner(min_paragraph_words=4)
    sentences = []
    i = 0
    for title in page_titles:  # fixed order, not dict/set order -- keeps ids stable across runs
        sections = [s for s in cleaner.sections(texts[title]) if s.name.strip().lower() not in drop_sections]
        for sec in sections:
            for p in sec.paragraphs:
                for sent in _split(p):
                    sentences.append(Sentence(i, title, sec.name, sent))
                    i += 1
    return sentences
