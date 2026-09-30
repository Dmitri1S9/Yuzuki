"""extract_v3 full run for Kyoka Jiro's own page only.

Pass 1: rewrite every sentence into simple sentences (one LLM call per sentence).
Pass 2: parse every simple sentence into an EDGE/PROPERTY fact, twice -- spaCy (no LLM) and qwen3.5:9b --
so the report can compare them on identical input.

Resumable: pass 1 results cache to disk as they're produced; pass 2 (LLM variant) checkpoints per sentence;
a crash and rerun picks up where it left off instead of restarting either pass.

Run: python -m extract_v3.run_jiro
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import spacy

from yuzuki_local.external.embedder import Embedder
from yuzuki_local.external.neo4j_client import Neo4jClient
from yuzuki_local.external.ollama import OllamaClient, PromptTooLong

from .neo4j_schema import ensure_constraints
from .neo4j_writer import FactWriter, write_roster
from .parser_llm import LlmParser
from .parser_spacy import SpacyParser
from .prompt_renderer import PromptRenderer
from .rewriter import Rewriter
from .settings import Settings
from .text_prep import load_sentences

HERE = Path(__file__).resolve().parent
RUN_ID = "jiro-v3"
PASS1_CACHE_PATH = HERE / f".pass1_{RUN_ID}.json"
PASS2_CHECKPOINT_PATH = HERE / f".checkpoint_{RUN_ID}.json"


def _load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _save(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    s = Settings.load()
    print(f"run_id={RUN_ID}")

    sentences = load_sentences(s.dump_path, s.page, s.drop_sections)
    print(f"{s.page}: {len(sentences)} sentences after cleaning")

    llm = OllamaClient(s.model, s.num_ctx, s.num_predict, s.keep_alive, s.timeout_s, s.retries)
    renderer = PromptRenderer()
    rewriter = Rewriter(llm, renderer, s.universe, s.characters, s.groups)

    # ================= PASS 1: rewrite =================
    pass1 = _load(PASS1_CACHE_PATH, {})
    pass1_calls_this_run = 0
    t0 = time.monotonic()
    for i, sent in enumerate(sentences):
        key = str(sent.id)
        if key in pass1:
            continue
        try:
            r = rewriter.rewrite(sentences, i, s.temperature)
        except PromptTooLong as e:
            pass1[key] = dict(section=sent.section, source_text=sent.text, simple_sentences=[],
                              hypothetical=False, status="skipped_too_long", note=str(e),
                              created_at=datetime.now(timezone.utc).isoformat())
            _save(PASS1_CACHE_PATH, pass1)
            continue
        pass1[key] = dict(section=sent.section, source_text=sent.text,
                          simple_sentences=list(r.simple_sentences), hypothetical=r.hypothetical,
                          status=r.status, note=r.error, prompt_eval_count=r.prompt_eval_count,
                          created_at=datetime.now(timezone.utc).isoformat())
        _save(PASS1_CACHE_PATH, pass1)
        pass1_calls_this_run += 1
        if pass1_calls_this_run % 25 == 0:
            print(f"  pass 1: {len(pass1)}/{len(sentences)} sentences done ({pass1_calls_this_run} this run)")
    pass1_seconds_this_run = time.monotonic() - t0
    print(f"pass 1: {pass1_calls_this_run} calls this run, {len(pass1)}/{len(sentences)} total, "
         f"{pass1_seconds_this_run:.0f}s this run")

    # flat list of simple sentences to parse
    simple_items = []
    for sent in sentences:
        entry = pass1.get(str(sent.id))
        if not entry or entry["status"] != "ok" or entry["hypothetical"]:
            continue
        for idx, simple_text in enumerate(entry["simple_sentences"]):
            simple_items.append(dict(
                simple_id=f"{sent.id}.{idx}", source_id=sent.id, section=entry["section"],
                source_text=entry["source_text"], simple_text=simple_text))
    hypothetical_count = sum(1 for e in pass1.values() if e.get("hypothetical"))
    print(f"{len(simple_items)} simple sentences to parse ({hypothetical_count} source sentences were "
         f"HYPOTHETICAL and excluded)")

    # ================= setup for pass 2 =================
    client = Neo4jClient(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    failed_constraints = ensure_constraints(client)
    if failed_constraints:
        print(f"WARNING: {len(failed_constraints)} constraint(s) could not be created: {failed_constraints}")
    write_roster(client, s.universe, s.characters, s.groups)
    embedder = Embedder(s.embedding_model)
    llm_parser = LlmParser(llm, renderer, s.universe, s.characters, s.groups)
    nlp = spacy.load(s.spacy_model)
    spacy_parser = SpacyParser(nlp, s.characters, s.groups)
    writer = FactWriter(client, embedder, s.universe, RUN_ID, s.model, llm_parser.prompt_version(),
                        s.characters, s.groups)

    # ================= PASS 2a: spaCy (no LLM, fast -- just rerun every time, no checkpoint needed) =====
    t0 = time.monotonic()
    spacy_written, spacy_failed = 0, 0
    for item in simple_items:
        res = spacy_parser.parse(item["simple_text"])
        if res.parsed is None:
            spacy_failed += 1
            continue
        writer.write_one(res.parsed, "spacy", item["simple_id"], item["source_id"], item["section"],
                         item["source_text"])
        spacy_written += 1
    spacy_seconds = time.monotonic() - t0
    print(f"pass 2a (spaCy): {spacy_written} written, {spacy_failed} failed to parse, {spacy_seconds:.1f}s")

    # ================= PASS 2b: LLM (resumable) ============================================================
    checkpoint = _load(PASS2_CHECKPOINT_PATH, {})
    llm_calls_this_run = 0
    per_call_metrics = []
    t0 = time.monotonic()
    for i, item in enumerate(simple_items):
        key = item["simple_id"] + "|llm"
        if key in checkpoint:
            continue
        try:
            res = llm_parser.parse(item["simple_text"], s.temperature)
        except PromptTooLong as e:
            checkpoint[key] = {"status": "skipped_too_long"}
            _save(PASS2_CHECKPOINT_PATH, checkpoint)
            continue
        if res.status == "ok" and res.parsed is not None:
            writer.write_one(res.parsed, "llm", item["simple_id"], item["source_id"], item["section"],
                             item["source_text"])
            per_call_metrics.append(res)
        checkpoint[key] = {"status": res.status}
        _save(PASS2_CHECKPOINT_PATH, checkpoint)
        llm_calls_this_run += 1
        if llm_calls_this_run % 25 == 0:
            print(f"  pass 2b: {len(checkpoint)}/{len(simple_items)} done ({llm_calls_this_run} this run)")
    llm_seconds_this_run = time.monotonic() - t0
    client.close()
    print(f"pass 2b (LLM): {llm_calls_this_run} calls this run, {len(checkpoint)}/{len(simple_items)} total, "
         f"{llm_seconds_this_run:.0f}s this run")

    # ================= report ================================================================================
    from .report import build_report
    report = build_report(
        s=s, run_id=RUN_ID, sentences=sentences, pass1=pass1, simple_items=simple_items,
        pass1_seconds_this_run=pass1_seconds_this_run, llm_seconds_this_run=llm_seconds_this_run,
        spacy_seconds=spacy_seconds, per_call_metrics=per_call_metrics, spacy_failed=spacy_failed)
    out = HERE / "REPORT.md"
    out.write_text(report, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
