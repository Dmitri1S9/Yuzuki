"""Step 3: one LLM call per parameter, judged against the resolved article
text and the triples extracted from it."""
import logging
import re

from ...domain.param import Param
from ...domain.schemas import ParamResult, ResolvedParagraph, Triple, answer_model
from ...infra.ollama_client import LLMError, OllamaClient
from ...infra.prompts import render, templates_digest
from ...repository.step_cache import StepCache, digest
from ...shared.decorators import logged

STEP3_FILE = "step3_params.json"
MIN_EVIDENCE_LEN = 10


def _norm(text: str) -> str:
    """Lowercase, punctuation-insensitive form used for quote matching."""
    return re.sub(r"[\W_]+", " ", text.casefold()).strip()


def build_article_text(paragraphs: list[ResolvedParagraph]) -> str:
    blocks: list[str] = []
    last_section = None
    for p in paragraphs:
        if p.section != last_section:
            blocks.append(f"## {p.section}")
            last_section = p.section
        blocks.append(p.resolved)
    return "\n\n".join(blocks)


def build_triples_block(triples: list[Triple]) -> str:
    lines = list(dict.fromkeys(f"- {t.subject} | {t.relation} | {t.object} ({t.section})" for t in triples))
    return "\n".join(lines) if lines else "(none)"


def evidence_found(evidence: str, paragraphs: list[ResolvedParagraph]) -> bool:
    """Verbatim (case- and punctuation-insensitive) occurrence of the quote
    in the step-1 text or in the original text, at least 10 characters."""
    quote = _norm(evidence)
    if len(quote) < MIN_EVIDENCE_LEN:
        return False
    for field in ("resolved", "original"):
        if quote in _norm(" ".join(getattr(p, field) for p in paragraphs)):
            return True
    return False


def judge_param(llm: OllamaClient, system: str, param: Param, article_text: str, triples_block: str,
                paragraphs: list[ResolvedParagraph]) -> ParamResult:
    # The article and the relations come first and are identical for every
    # parameter, so Ollama reuses the prompt-prefix KV cache; only the
    # trait block at the end changes.
    user = render(
        "user_prompt_params", article_text=article_text, triples_block=triples_block,
        param=param, tiers=param.tiers[:-1], top_tier=param.tiers[-2],
    )
    try:
        answer = llm.generate(system, user, answer_model(tuple(param.tiers)))
    except LLMError as e:
        return ParamResult(name=param.name, ordinal=param.ordinal, tier=None, evidence="", reason=str(e), status="error")

    if answer.tier == "unknown":
        status = "ok"
    else:
        status = "ok" if evidence_found(answer.evidence, paragraphs) else "evidence_not_found"
    return ParamResult(
        name=param.name, ordinal=param.ordinal, tier=answer.tier,
        evidence=answer.evidence.strip(), reason=answer.reason.strip(), status=status,
    )


@logged(lambda _, done, total: f"Шаг 3: из кеша {done} из {total} параметров" if done else None)
def _log_cache_hit(done: int, total: int) -> None:
    pass


@logged(lambda _, i, total, name, tier, status: f"Шаг 3 [{i}/{total}] {name} -> {tier} ({status})")
def _log_progress(i: int, total: int, name: str, tier: str | None, status: str) -> None:
    pass


@logged(lambda _, name, reason: f"Шаг 3: параметр {name} не получен: {reason}", level=logging.ERROR)
def _log_param_error(name: str, reason: str) -> None:
    pass


def run_params(llm: OllamaClient, params: list[Param], paragraphs: list[ResolvedParagraph], triples: list[Triple],
               character: str, cache: StepCache, fresh: bool = False) -> list[ParamResult]:
    article_text = build_article_text(paragraphs)
    triples_block = build_triples_block(triples)
    key = digest(
        llm.model, templates_digest("system_prompt_params", "user_prompt_params"), character,
        article_text, triples_block,
    )
    param_hash = {p.name: digest(p.__dict__) for p in params}

    # Resume: keep results that are done (ok / evidence_not_found) for an
    # unchanged parameter; failed ones are always asked again.
    done: dict[str, ParamResult] = {}
    cached = cache.read(STEP3_FILE, key, fresh)
    if cached:
        for raw in cached["results"]:
            r = ParamResult(**raw)
            if r.status != "error" and cached["param_hashes"].get(r.name) == param_hash.get(r.name):
                done[r.name] = r
    _log_cache_hit(len(done), len(params))

    system = render("system_prompt_params", character=character)
    results: dict[str, ParamResult] = dict(done)

    def checkpoint() -> None:
        ordered = [results[p.name] for p in params if p.name in results]
        cache.write(STEP3_FILE, {
            "cache_key": key, "model": llm.model, "character": character,
            "param_hashes": param_hash, "results": [r.model_dump() for r in ordered],
        })

    for i, param in enumerate(params, 1):
        if param.name in done:
            continue
        r = judge_param(llm, system, param, article_text, triples_block, paragraphs)
        results[param.name] = r
        _log_progress(i, len(params), param.name, r.tier, r.status)
        if r.status == "error":
            _log_param_error(param.name, r.reason)
        checkpoint()
    checkpoint()
    return [results[p.name] for p in params]
