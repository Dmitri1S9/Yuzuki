"""Full run for Kyoka Jiro, v2 schema (ACTION with action/action_raw/manner/target/complement +
DESCRIBED_AS traits). No single-chunk smoke test, no chunk-size experiment -- straight to the full run over
the same chunks as the v1 run. Resumable: writes to Neo4j and checkpoints after every chunk, so a crash
partway through picks up where it left off on the next invocation (same run_id).

Run: python -m graph_extract.run_jiro
"""
import hashlib
import json
import time
from pathlib import Path

from yuzuki_local.external.dump_reader import DumpReader
from yuzuki_local.external.embedder import Embedder
from yuzuki_local.external.neo4j_client import Neo4jClient
from yuzuki_local.external.ollama import OllamaClient, PromptTooLong
from yuzuki_local.workers.wikitext_cleaner import WikiTextCleaner

from .chunker import chunk_sections
from .extractor import ActionExtractor
from .neo4j_schema import ensure_constraints
from .neo4j_writer import ChunkWriter, write_roster
from .prompt_renderer import PromptRenderer
from .settings import Settings

HERE = Path(__file__).resolve().parent
RUN_ID = "jiro-v2"  # stable across resumes; the v1 run used a random run_id and is untouched in Neo4j
CHECKPOINT_PATH = HERE / f".checkpoint_{RUN_ID}.json"


def _chunk_key(chunk) -> str:
    return hashlib.sha1(f"{chunk.section}|{chunk.text}".encode("utf-8")).hexdigest()


def _load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    return {"done": {}}


def _save_checkpoint(state: dict) -> None:
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(CHECKPOINT_PATH)


def main() -> int:
    s = Settings.load()
    print(f"run_id={RUN_ID}")

    dump = DumpReader(s.dump_path)
    cleaner = WikiTextCleaner(min_paragraph_words=4)
    pages = {p.title: p.text for p in dump.pages() if p.title in set(s.pages)}
    missing = set(s.pages) - set(pages)
    if missing:
        print(f"WARNING: pages not found in dump: {missing}")

    llm = OllamaClient(s.model, s.num_ctx, s.num_predict, s.keep_alive, s.timeout_s, s.retries)
    renderer = PromptRenderer()
    extractor = ActionExtractor(llm, renderer, s.universe, s.characters, s.groups)

    # ---- same chunking as the v1 run: 3-8 sentences per section, same page scope ----------------------
    all_chunks = []
    per_page_chars = {}
    for title, text in pages.items():
        sections = cleaner.sections(text)
        page_chunks = chunk_sections(sections, s.min_sentences, s.max_sentences)
        per_page_chars[title] = sum(len(c.text) for c in page_chunks)
        all_chunks.extend(page_chunks)
    total_context_chars = sum(len(c.text) for c in all_chunks)
    print(f"{len(pages)} pages -> {len(all_chunks)} chunks, {total_context_chars} chars")

    checkpoint = _load_checkpoint()
    already_done = checkpoint["done"]
    print(f"resuming: {len(already_done)}/{len(all_chunks)} chunks already done per checkpoint")

    client = Neo4jClient(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    failed_constraints = ensure_constraints(client)
    if failed_constraints:
        print(f"WARNING: {len(failed_constraints)} constraint(s) could not be created: {failed_constraints}")
    write_roster(client, s.universe, s.characters, s.groups)
    embedder = Embedder(s.embedding_model)
    writer = ChunkWriter(client, embedder, s.universe, RUN_ID, s.model, extractor.prompt_version(),
                         s.characters, s.groups)

    per_call_metrics = []
    t0 = time.monotonic()
    processed_this_run = 0
    for i, c in enumerate(all_chunks):
        key = _chunk_key(c)
        if key in already_done:
            continue
        try:
            r = extractor.extract(c, s.temperature)
        except PromptTooLong as e:
            print(f"  chunk {i} ({c.section}): PromptTooLong, skipped permanently: {e}")
            already_done[key] = {"status": "skipped_too_long"}
            _save_checkpoint(checkpoint)
            continue
        n_a, n_t = writer.write(list(r.actions), list(r.traits))
        if r.status == "ok":
            per_call_metrics.append(r)
        already_done[key] = {"status": r.status, "n_actions": n_a, "n_traits": n_t}
        _save_checkpoint(checkpoint)
        processed_this_run += 1
        if processed_this_run % 25 == 0:
            print(f"  {len(already_done)}/{len(all_chunks)} chunks done ({processed_this_run} this run)")
    extraction_seconds = time.monotonic() - t0
    client.close()
    print(f"processed {processed_this_run} chunks this run ({len(already_done)}/{len(all_chunks)} total) "
         f"in {extraction_seconds:.0f}s")

    # ---- report -------------------------------------------------------------------------------------
    from .report import build_report
    report = build_report(
        s=s, run_id=RUN_ID, pages=pages, per_page_chars=per_page_chars, all_chunks=all_chunks,
        extraction_seconds=extraction_seconds, per_call_metrics=per_call_metrics)
    out = HERE / "REPORT.md"
    out.write_text(report, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
