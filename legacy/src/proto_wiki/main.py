"""The conductor: a flat, top-to-bottom sequence of named calls, no business
logic of its own — mirrors the main Yuzuki pipeline's own "one main.py per
level" idiom (see its ARCHITECTURE.md), just inlined into one function since
this prototype has a single stage, not several independently runnable ones.
"""
from pathlib import Path

from .domain.schemas import Triple
from .infra.ollama_client import OllamaClient
from .repository.step_cache import StepCache
from .services.coref.step import run_coref
from .services.graph.step import build_graph, write_graph
from .services.params.step import run_params
from .services.parsing.params_loader import load_params
from .services.parsing.text_loader import load_document
from .services.report.step import build_report
from .services.triples.step import run_triples
from .shared.decorators import logged


@logged(lambda n_errors, input_path, character, params_path, out_dir, llm, fresh=False:
        f"Готово: {out_dir} (ошибок: {n_errors})")
def run(input_path: str, character: str, params_path: str, out_dir: Path,
        llm: OllamaClient, fresh: bool = False) -> int:
    """Returns the number of errors (step 1/2 paragraph failures + step 3
    parameter failures) — 0 means a clean run. Writes all 6 output files
    into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = StepCache(out_dir)

    params = load_params(params_path)
    doc = load_document(input_path, character)

    paragraphs = run_coref(llm, doc, cache, fresh)
    step2 = run_triples(llm, paragraphs, character, cache, fresh)
    triples = [Triple(**t) for t in step2["triples"]]

    graph = build_graph(triples, character, doc.aliases)
    write_graph(graph, out_dir)

    results = run_params(llm, params, paragraphs, triples, character, cache, fresh)

    step_errors = [f"шаг 1, раздел «{p.section}»: {p.error}" for p in paragraphs if p.error]
    step_errors += [f"шаг 2, раздел «{e['section']}»: {e['error']}" for e in step2["errors"]]
    (out_dir / "report.md").write_text(build_report(character, llm.model, results, step_errors), encoding="utf-8")

    return sum(r.status == "error" for r in results) + len(step_errors)
