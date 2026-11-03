"""Step 1: pronoun/reference resolution, one LLM call per paragraph."""
import logging
import re

from ...domain.document import Document
from ...domain.schemas import CorefOutput, ResolvedParagraph
from ...infra.ollama_client import LLMError, OllamaClient
from ...infra.prompts import render, templates_digest
from ...repository.step_cache import StepCache, digest
from ...shared.decorators import logged

COREF_RATIO_RANGE = (0.7, 1.6)
MAX_NAMES_IN_PROMPT = 25
STEP1_FILE = "step1_coref.json"


def names_in_paragraph(text: str, aliases: dict[str, str]) -> list[str]:
    """Canonical link targets mentioned in the paragraph: by their full
    name / alias, or (for 2-3 word alphabetic names) by first or last name —
    the wiki often writes just "Denki" for [[Denki Kaminari]]."""
    found: list[str] = []

    def add(name: str) -> None:
        if name not in found:
            found.append(name)

    for alias, target in aliases.items():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text):
            add(target)
    for target in set(aliases.values()):
        words = target.split()
        if 2 <= len(words) <= 3 and all(w.isalpha() for w in words):
            for w in (words[0], words[-1]):
                if len(w) >= 3 and re.search(rf"(?<!\w){re.escape(w)}(?!\w)", text):
                    add(target)
    return found[:MAX_NAMES_IN_PROMPT]


@logged(lambda _, n: f"Шаг 1: беру кеш ({n} абзацев)")
def _log_cache_hit(n: int) -> None:
    pass


@logged(lambda _, i, total, section, error: f"Шаг 1 [{i}/{total}] ОШИБКА в разделе «{section}»: {error}",
        level=logging.ERROR)
def _log_error(i: int, total: int, section: str, error: str) -> None:
    pass


@logged(lambda _, i, total, ratio, section: f"Шаг 1 [{i}/{total}] REJECTED (длина {ratio:.2f} от оригинала, "
        f"раздел «{section}») — беру оригинал", level=logging.WARNING)
def _log_rejected(i: int, total: int, ratio: float, section: str) -> None:
    pass


@logged(lambda _, i, total: f"Шаг 1 [{i}/{total}] ok")
def _log_ok(i: int, total: int) -> None:
    pass


def run_coref(llm: OllamaClient, doc: Document, cache: StepCache, fresh: bool = False) -> list[ResolvedParagraph]:
    key = digest(
        llm.model, templates_digest("system_prompt_coref", "user_prompt_coref"), doc.character,
        [(p.section, p.text) for p in doc.paragraphs], sorted(doc.aliases.items()),
    )
    cached = cache.read(STEP1_FILE, key, fresh)
    if cached and not any(p.get("error") for p in cached["paragraphs"]):
        _log_cache_hit(len(cached["paragraphs"]))
        return [ResolvedParagraph(**p) for p in cached["paragraphs"]]

    system = render("system_prompt_coref", character=doc.character)
    results: list[ResolvedParagraph] = []
    for i, p in enumerate(doc.paragraphs, 1):
        user = render(
            "user_prompt_coref", character=doc.character, section=p.section,
            names=names_in_paragraph(p.text, doc.aliases), paragraph=p.text,
        )
        try:
            resolved = llm.generate(system, user, CorefOutput).text.strip()
        except LLMError as e:
            _log_error(i, len(doc.paragraphs), p.section, str(e))
            results.append(ResolvedParagraph(
                section=p.section, original=p.text, resolved=p.text, coref_ok=False, error=str(e)))
            continue
        ratio = len(resolved) / len(p.text)
        if not COREF_RATIO_RANGE[0] <= ratio <= COREF_RATIO_RANGE[1]:
            _log_rejected(i, len(doc.paragraphs), ratio, p.section)
            results.append(ResolvedParagraph(section=p.section, original=p.text, resolved=p.text, coref_ok=False))
        else:
            _log_ok(i, len(doc.paragraphs))
            results.append(ResolvedParagraph(section=p.section, original=p.text, resolved=resolved, coref_ok=True))

    cache.write(STEP1_FILE, {
        "cache_key": key, "model": llm.model, "character": doc.character,
        "paragraphs": [r.model_dump() for r in results],
    })
    return results
