"""Страница вики в формате research/samples/pages/*.txt -> абзацы с устойчивыми id.

Формат файла (его пишет research/samples/extract_pages.py):
    === PAGE: Kyoka Jiro/Relationships ===
    == Denki Kaminari ==
    <абзац на строку>

id абзаца = "page|section|idx", idx — номер абзаца внутри секции (с 0).
"""
from dataclasses import dataclass
from pathlib import Path

PAGES_DIR = Path(__file__).resolve().parent.parent / "samples" / "pages"


@dataclass(frozen=True)
class Paragraph:
    page: str
    section: str
    idx: int
    text: str

    @property
    def id(self) -> str:
        return f"{self.page}|{self.section}|{self.idx}"


def parse_pages(text: str) -> list[Paragraph]:
    out: list[Paragraph] = []
    page, section, idx = "", "", 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("=== PAGE:") and line.endswith("==="):
            page, section, idx = line[len("=== PAGE:"):-3].strip(), "", 0
        elif line.startswith("==") and line.endswith("=="):
            section, idx = line.strip("=").strip(), 0
        else:
            out.append(Paragraph(page, section, idx, line))
            idx += 1
    return out


def load_pages(name: str, pages_dir: Path = PAGES_DIR) -> list[Paragraph]:
    """name = имя файла без .txt ("Kyoka_Jiro")."""
    return parse_pages((pages_dir / f"{name}.txt").read_text(encoding="utf-8"))


def page_owner(paragraphs: list[Paragraph]) -> str:
    """Владелец страницы — заголовок первой страницы без подстраницы ("Kyoka Jiro/Synopsis" -> "Kyoka Jiro")."""
    return paragraphs[0].page.split("/")[0]
