"""Paragraph/Document — the parsed-text entity. Pure data, no I/O; built by
services/parsing/text_loader.py the same way a repository builds a domain
object from DB rows."""
from dataclasses import dataclass, field


@dataclass
class Paragraph:
    section: str
    text: str


@dataclass
class Document:
    character: str
    paragraphs: list[Paragraph]
    # link text -> canonical entity id (the link target). Targets map to
    # themselves, so every linked entity is a known canonical name.
    aliases: dict[str, str] = field(default_factory=dict)
