"""wikitext -> readable paragraphs grouped by section.

Drops infoboxes, navboxes, galleries, tables, refs, media links and the
reference-like sections (appearance lists, references, navigation). Pure text
processing: no I/O, no LLM.
"""
import re
from dataclasses import dataclass

import mwparserfromhell
from mwparserfromhell.nodes import Heading


@dataclass(frozen=True)
class WikiSection:
    name: str
    paragraphs: tuple[str, ...]

    @property
    def chars(self) -> int:
        return sum(len(p) for p in self.paragraphs)


SKIP_SECTIONS = (
    "references", "navigation", "site navigation", "gallery", "image gallery", "external links",
    "see also", "notes", "appearances", "voice actors", "merchandise", "video game appearances",
)
_NON_ENTITY_NAMESPACES = {"file", "image", "media", "category", "template", "special", "help", "user", "talk"}
_REMOVED_TAGS = {"ref", "table", "gallery", "noinclude", "references"}


class WikiTextCleaner:
    def __init__(self, min_paragraph_words: int = 4):
        self._min_words = min_paragraph_words

    def sections(self, text: str, intro_name: str = "Introduction") -> list[WikiSection]:
        code = mwparserfromhell.parse(text)
        self._prepare(code)
        sections: list[WikiSection] = []
        label = intro_name
        skip_level: int | None = None
        buf: list[str] = []

        def flush() -> None:
            if skip_level is not None or not buf:
                return
            paragraphs = self._paragraphs(mwparserfromhell.parse("".join(buf)))
            if paragraphs:
                sections.append(WikiSection(label, tuple(paragraphs)))

        for node in code.nodes:
            if not isinstance(node, Heading):
                buf.append(str(node))
                continue
            flush()
            buf = []
            name = node.title.strip_code().strip()
            if skip_level is not None and node.level <= skip_level:
                skip_level = None
            if skip_level is None and self._is_skipped(name):
                skip_level = node.level
            label = name
        flush()
        return sections

    def clean_line(self, line: str) -> str:
        """One raw wikitext line (a mention fragment) -> plain text, '' if nothing readable is left."""
        code = mwparserfromhell.parse(line)
        self._prepare(code)
        paragraphs = self._paragraphs(code)
        return " ".join(paragraphs)

    @staticmethod
    def _is_skipped(heading: str) -> bool:
        h = heading.casefold()
        return any(h == s or h.endswith(" " + s) for s in SKIP_SECTIONS)

    @staticmethod
    def _prepare(code) -> None:
        for tag in code.filter_tags(matches=lambda t: str(t.tag).strip().lower() in _REMOVED_TAGS):
            _safe_remove(code, tag)
        for tag in code.filter_tags(matches=lambda t: str(t.tag).strip().lower() == "br"):
            _safe_replace(code, tag, "\n")
        for link in code.filter_wikilinks():
            ns, sep, _ = str(link.title).strip().lstrip(":").partition(":")
            if sep and ns.strip().casefold() in _NON_ENTITY_NAMESPACES:
                _safe_remove(code, link)
        # {{Nihongo|English|kanji|romaji}} and {{Ruby|base|ruby}}: keep the readable part
        for tpl in code.filter_templates(matches=lambda t: str(t.name).strip().lower() in {"nihongo", "ruby"}):
            if tpl.params:
                _safe_replace(code, tpl, str(tpl.params[0].value).strip())

    def _paragraphs(self, code) -> list[str]:
        cleaned = code.strip_code(normalize=True, collapse=True)
        out = []
        for line in cleaned.split("\n"):
            line = re.sub(r"^[*#:;]+\s*", "", line.strip())
            line = re.sub(r"__[A-Z]+__", "", line)
            line = re.sub(r"\s+", " ", line).strip()
            if len(line.split()) >= self._min_words:
                out.append(line)
        return out


def _safe_remove(code, node) -> None:
    try:
        code.remove(node)
    except ValueError:
        pass


def _safe_replace(code, node, value: str) -> None:
    try:
        code.replace(node, value)
    except ValueError:
        pass
