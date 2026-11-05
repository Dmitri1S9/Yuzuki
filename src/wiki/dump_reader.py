"""Streams a MediaWiki XML dump page by page (never holds more than one page). Atomic."""
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class DumpPage:
    title: str
    ns: int
    text: str


class DumpReader:
    def __init__(self, path: Path):
        self._path = path

    def pages(self) -> Iterator[DumpPage]:
        for _, el in ET.iterparse(self._path, events=("end",)):
            if el.tag.rsplit("}", 1)[-1] != "page":
                continue
            revisions = el.findall("{*}revision")
            text = (revisions[-1].findtext("{*}text") or "") if revisions else ""
            yield DumpPage(el.findtext("{*}title") or "", int(el.findtext("{*}ns") or 0), text)
            el.clear()
