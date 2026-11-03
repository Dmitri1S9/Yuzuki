"""Reads the character's text (MediaWiki XML dump, raw wikitext or plain
text) into a Document (paragraphs + alias dictionary). Pure parsing logic —
no LLM/network calls, no caching.
"""
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import mwparserfromhell
from mwparserfromhell.nodes import Heading

from ...domain.document import Document, Paragraph
from ...errors import LoaderError
from ...shared.decorators import logged

SKIP_SECTIONS = (
    "references", "navigation", "site navigation", "gallery", "external links",
    "see also", "notes", "appearances", "voice actors",
)
# links into these namespaces are media/meta, not entities
_NON_ENTITY_NAMESPACES = {"file", "image", "media", "category", "template", "special", "help", "user", "talk"}
_MIN_PARAGRAPH_WORDS = 4


@logged(lambda _, character: f"Подстраницы «{character}/Relationships» в дампе нет — идём без неё")
def _log_no_relationships_subpage(character: str) -> None:
    pass


@logged(lambda doc, input_path, character: f"Вход: {input_path} -> {len(doc.paragraphs)} абзацев, {len(doc.aliases)} алиасов")
def load_document(input_path: str | Path, character: str) -> Document:
    path = _resolve_input_file(Path(input_path), character)

    if path.suffix.lower() == ".xml":
        pages = _read_dump_pages(path, character)
        main_text = pages.get(_title_key(character))
        if main_text is None:
            raise LoaderError(f"В дампе {path.name} нет страницы «{character}»")
        parsed = [parse_wikitext(main_text, intro_name="Introduction")]
        rel_text = pages.get(_title_key(f"{character}/Relationships"))
        if rel_text is None:
            _log_no_relationships_subpage(character)
        else:
            parsed.append(parse_wikitext(rel_text, intro_name="Relationships", prefix="Relationships / "))
    else:
        text = path.read_text(encoding="utf-8")
        if _looks_like_wikitext(text):
            parsed = [parse_wikitext(text, intro_name="Introduction")]
        else:
            parsed = [(_plain_paragraphs(text), Counter())]

    paragraphs = [p for paras, _ in parsed for p in paras]
    if not paragraphs:
        raise LoaderError("После разбора текста не осталось ни одного абзаца")

    pair_counts: Counter = Counter()
    for _, c in parsed:
        pair_counts.update(c)
    return Document(character=character, paragraphs=paragraphs, aliases=_build_alias_dict(pair_counts, character))


def _resolve_input_file(path: Path, character: str) -> Path:
    if path.is_file():
        return path
    if not path.is_dir():
        raise LoaderError(f"--input не найден: {path}")
    xmls = sorted(path.glob("*.xml"))
    if xmls:
        preferred = [p for p in xmls if p.name.endswith("_pages_current.xml")]
        return (preferred or xmls)[0]
    texts = sorted(p for p in path.iterdir() if p.suffix.lower() in {".wiki", ".wikitext", ".txt"})
    if len(texts) == 1:
        return texts[0]
    named = [p for p in texts if p.stem.casefold() == character.casefold()]
    if named:
        return named[0]
    raise LoaderError(f"В папке {path} не нашёл ни дампа *.xml, ни однозначного текстового файла")


def _title_key(title: str) -> str:
    return title.replace("_", " ").strip().casefold()


def _read_dump_pages(path: Path, character: str) -> dict[str, str]:
    """Streams the dump (it is ~100 MB) and keeps only the character page
    and its /Relationships subpage."""
    wanted = {_title_key(character), _title_key(f"{character}/Relationships")}
    found: dict[str, str] = {}
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag.rsplit("}", 1)[-1] != "page":
            continue
        title = el.findtext("{*}title") or ""
        key = _title_key(title)
        if key in wanted:
            revisions = el.findall("{*}revision")
            if revisions:
                found[key] = revisions[-1].findtext("{*}text") or ""
        el.clear()
        if found.keys() == wanted:
            break
    return found


def _looks_like_wikitext(text: str) -> bool:
    return bool(re.search(r"\[\[|\{\{|'''|^=+[^=\n]+=+\s*$", text, re.M))


def _plain_paragraphs(text: str) -> list[Paragraph]:
    out = []
    for block in re.split(r"\n\s*\n", text):
        block = re.sub(r"\s+", " ", block).strip()
        if len(block.split()) >= _MIN_PARAGRAPH_WORDS:
            out.append(Paragraph("Text", block))
    return out


# --- wikitext -------------------------------------------------------------

def parse_wikitext(text: str, intro_name: str = "Introduction", prefix: str = "") -> tuple[list[Paragraph], Counter]:
    """Returns (paragraphs with their section names, Counter of
    (link text, link target) pairs found in the kept sections)."""
    code = mwparserfromhell.parse(text)
    _prepare(code)

    paragraphs: list[Paragraph] = []
    pairs: Counter = Counter()
    label = intro_name
    skip_level: int | None = None
    buf: list[str] = []

    def flush() -> None:
        if skip_level is not None or not buf:
            return
        sec_code = mwparserfromhell.parse("".join(buf))
        pairs.update(_link_pairs(sec_code))
        paragraphs.extend(Paragraph(label, t) for t in _clean_paragraphs(sec_code))

    for node in code.nodes:
        if not isinstance(node, Heading):
            buf.append(str(node))
            continue
        flush()
        buf = []
        name = node.title.strip_code().strip()
        if skip_level is not None and node.level <= skip_level:
            skip_level = None
        if skip_level is None and _is_skipped(name):
            skip_level = node.level
        if skip_level is None:
            pairs.update(_link_pairs(node.title))
        label = f"{prefix}{name}"
    flush()
    return paragraphs, pairs


def _is_skipped(heading: str) -> bool:
    h = heading.casefold()
    return any(h == s or h.endswith(" " + s) for s in SKIP_SECTIONS)


def _prepare(code) -> None:
    """Removes what strip_code() would otherwise leak into the text:
    refs, tables, media/category links; keeps the visible name from
    {{Nihongo|English|kanji|romaji}} (the intro sentence's subject)."""
    for tag in code.filter_tags(matches=lambda t: str(t.tag).strip().lower() in {"ref", "table", "gallery"}):
        _safe_remove(code, tag)
    for tag in code.filter_tags(matches=lambda t: str(t.tag).strip().lower() == "br"):
        _safe_replace(code, tag, "\n")
    for link in code.filter_wikilinks():
        ns, sep, _ = str(link.title).strip().lstrip(":").partition(":")
        if sep and ns.strip().casefold() in _NON_ENTITY_NAMESPACES:
            _safe_remove(code, link)
    for tpl in code.filter_templates(matches=lambda t: str(t.name).strip().lower() == "nihongo"):
        if tpl.params:
            _safe_replace(code, tpl, str(tpl.params[0].value).strip())


def _safe_remove(code, node) -> None:
    try:
        code.remove(node)
    except ValueError:  # already gone with an enclosing node
        pass


def _safe_replace(code, node, value: str) -> None:
    try:
        code.replace(node, value)
    except ValueError:
        pass


def _clean_paragraphs(code) -> list[str]:
    cleaned = code.strip_code(normalize=True, collapse=True)
    out = []
    for line in cleaned.split("\n"):
        line = re.sub(r"^[*#:;]+\s*", "", line.strip())
        line = re.sub(r"__[A-Z]+__", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if len(line.split()) >= _MIN_PARAGRAPH_WORDS:
            out.append(line)
    return out


def _link_pairs(code) -> list[tuple[str, str]]:
    pairs = []
    for link in code.filter_wikilinks():
        target = str(link.title).strip().lstrip(":")
        ns, sep, _ = target.partition(":")
        if sep and ns.strip().casefold() in _NON_ENTITY_NAMESPACES:
            continue
        target = re.sub(r"\s+", " ", target.split("#", 1)[0].replace("_", " ")).strip()
        if not target:
            continue
        target = target[0].upper() + target[1:]  # MediaWiki: first letter is case-insensitive, canonical form is capitalized
        alias = target
        if link.text is not None:
            alias = re.sub(r"\s+", " ", link.text.strip_code()).strip() or target
        if len(alias) >= 2 and len(alias) <= 80:
            pairs.append((alias, target))
        pairs.append((target, target))
    return pairs


def _build_alias_dict(pair_counts: Counter, character: str) -> dict[str, str]:
    best: dict[str, tuple[int, str]] = {}
    for (alias, target), n in pair_counts.items():
        if alias not in best or n > best[alias][0]:
            best[alias] = (n, target)
    aliases = {alias: target for alias, (_, target) in best.items()}
    aliases.setdefault(character, character)
    return aliases
