"""Step 2: subject-relation-object triples, one LLM call per paragraph."""
import logging
import re

from ...domain.schemas import RELATION_OBJECT_TYPE, RELATIONS_BY_OBJECT_TYPE, ResolvedParagraph, Triple, TriplesOutput
from ...infra.ollama_client import LLMError, OllamaClient
from ...infra.prompts import render, templates_digest
from ...repository.step_cache import StepCache, digest
from ...shared.decorators import logged

STEP2_FILE = "step2_triples.json"

_ABBREVIATIONS = ("Mr", "Mrs", "Ms", "Dr", "St", "Jr", "Sr", "vs", "No", "Vol", "Ch", "Lt", "Capt", "Gen")
_SENT_BOUNDARY = re.compile(r"(?<=[.!?])[\"'”’)\]]*\s+(?=[\"'“‘(\[]*[A-Z0-9])")


def split_sentences(text: str) -> list[str]:
    parts = _SENT_BOUNDARY.split(text.strip())
    sentences: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if sentences and re.search(rf"\b(?:{'|'.join(_ABBREVIATIONS)})\.$", sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {part}"
        else:
            sentences.append(part)
    return sentences


def _check_triple(t, n_sentences: int) -> str | None:
    """Returns why the triple must be dropped, or None if it is fine."""
    if not 1 <= t.sentence_id <= n_sentences:
        return "sentence_id_out_of_range"
    if not t.subject.strip() or not t.object.strip():
        return "empty_name"
    if t.subject_type != "Character" or RELATION_OBJECT_TYPE[t.relation] != t.object_type:
        return "relation_type_mismatch"
    return None


@logged(lambda _, n: f"Шаг 2: беру кеш ({n} троек)")
def _log_cache_hit(n: int) -> None:
    pass


@logged(lambda _, i, total, section, error: f"Шаг 2 [{i}/{total}] ОШИБКА в разделе «{section}»: {error}",
        level=logging.ERROR)
def _log_error(i: int, total: int, section: str, error: str) -> None:
    pass


@logged(lambda _, i, total, kept: f"Шаг 2 [{i}/{total}] троек: {kept}")
def _log_paragraph_done(i: int, total: int, kept: int) -> None:
    pass


@logged(lambda _, dropped: f"Шаг 2: отброшено троек: {dropped}" if dropped else None, level=logging.WARNING)
def _log_dropped_summary(dropped: dict) -> None:
    pass


def run_triples(llm: OllamaClient, paragraphs: list[ResolvedParagraph], character: str,
                cache: StepCache, fresh: bool = False) -> dict:
    """Returns the step-2 payload: {"triples": [...], "errors": [...], "dropped": {...}}."""
    key = digest(
        llm.model, templates_digest("system_prompt_triples", "user_prompt_triples"), character,
        [(p.section, p.resolved) for p in paragraphs],
    )
    cached = cache.read(STEP2_FILE, key, fresh)
    if cached and not cached["errors"]:
        _log_cache_hit(len(cached["triples"]))
        return cached

    system = render("system_prompt_triples", character=character, groups=RELATIONS_BY_OBJECT_TYPE)
    triples: list[Triple] = []
    errors: list[dict] = []
    dropped: dict[str, int] = {}
    for i, p in enumerate(paragraphs, 1):
        sentences = split_sentences(p.resolved)
        if not sentences:
            continue
        user = render("user_prompt_triples", character=character, section=p.section, sentences=sentences)
        try:
            answer = llm.generate(system, user, TriplesOutput)
        except LLMError as e:
            _log_error(i, len(paragraphs), p.section, str(e))
            errors.append({"paragraph_index": i - 1, "section": p.section, "error": str(e)})
            continue
        kept = 0
        seen: set[tuple] = set()
        for t in answer.triples:
            reason = _check_triple(t, len(sentences))
            if not reason:
                identity = (t.sentence_id, t.subject.casefold(), t.relation, t.object.casefold())
                reason = "duplicate_in_answer" if identity in seen else None
                seen.add(identity)
            if reason:
                dropped[reason] = dropped.get(reason, 0) + 1
                continue
            data = t.model_dump()
            if t.object_type != "Item":
                data["item_class"] = "none"
            elif data["item_class"] == "none":
                data["item_class"] = "other"
            triples.append(Triple(**data, evidence=sentences[t.sentence_id - 1], section=p.section))
            kept += 1
        _log_paragraph_done(i, len(paragraphs), kept)

    _log_dropped_summary(dropped)
    payload = {
        "cache_key": key, "model": llm.model, "character": character,
        "triples": [t.model_dump() for t in triples], "errors": errors, "dropped": dropped,
    }
    cache.write(STEP2_FILE, payload)
    return payload
