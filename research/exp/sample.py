"""Детерминированная выборка абзацев для эталона: первый абзац секции, секции — равномерно по странице."""
from collections import OrderedDict

from .pages import Paragraph


def sample_relationships(paragraphs: list[Paragraph], k: int = 15) -> list[Paragraph]:
    secs: "OrderedDict[str, Paragraph]" = OrderedDict()
    for p in paragraphs:
        if p.page.endswith("/Relationships") and p.section not in secs:
            secs[p.section] = p
    firsts = list(secs.values())
    if len(firsts) <= k:
        return firsts
    return [firsts[round(i * (len(firsts) - 1) / (k - 1))] for i in range(k)]
