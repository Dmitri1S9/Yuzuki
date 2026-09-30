"""Builds extract_v3/REPORT.md. Fact tallies come from Neo4j (both variants, full accumulated state);
pass-1 stats come from the local pass1 cache (has its own created_at per entry, so it's resumption-safe)."""
import random
import statistics
from collections import Counter, defaultdict
from datetime import datetime

from yuzuki_local.external.neo4j_client import Neo4jClient


def _fmt_s(x: float) -> str:
    return f"{x:.1f}s" if x < 120 else f"{x / 60:.1f}min"


def _fetch_facts(client: Neo4jClient, run_id: str, variant: str) -> list[dict]:
    q = ("MATCH (s)-[r:EDGE {run_id:$run_id, variant:$variant}]->(o) RETURN 'edge' AS kind, s.name AS subject, "
        "r.predicate AS predicate, r.predicate_raw AS predicate_raw, r.via AS via, o.name AS target, "
        "r.description AS description, r.modality AS modality, r.negated AS negated, r.mutual AS mutual, "
        "r.frequency AS frequency, r.degree AS degree, r.certainty AS certainty, r.former AS former, "
        "r.simple_sentence_id AS simple_sentence_id, r.source_sentence_id AS source_sentence_id, "
        "r.source_sentence AS source_sentence "
        "UNION "
        "MATCH (s)-[r:HAS_PROPERTY {run_id:$run_id, variant:$variant}]->(p) RETURN 'property' AS kind, "
        "s.name AS subject, null AS predicate, null AS predicate_raw, null AS via, p.name AS target, "
        "r.description AS description, r.modality AS modality, r.negated AS negated, false AS mutual, "
        "r.frequency AS frequency, r.degree AS degree, r.certainty AS certainty, r.former AS former, "
        "r.simple_sentence_id AS simple_sentence_id, r.source_sentence_id AS source_sentence_id, "
        "r.source_sentence AS source_sentence")
    with client.session() as session:
        return [dict(rec) for rec in session.run(q, run_id=run_id, variant=variant)]


def _fact_summary(f: dict) -> str:
    if f["kind"] == "property":
        return f"PROPERTY({f['subject']}, {f['target']})" + (" [neg]" if f["negated"] else "")
    return (f"EDGE({f['subject']} -{f['predicate']}-> {f['target']})" +
           (f" via={f['via']}" if f.get("via") else "") + (" [neg]" if f["negated"] else "") +
           (" [mutual]" if f["mutual"] else ""))


def build_report(*, s, run_id, sentences, pass1, simple_items, pass1_seconds_this_run, llm_seconds_this_run,
                 spacy_seconds, per_call_metrics, spacy_failed) -> str:
    lines = [f"# extract_v3 — Kyoka Jiro's own page ({s.universe})", "",
            f"run_id={run_id}, model={s.model}, temperature={s.temperature}, think=false, page={s.page!r}.",
            ""]

    ok_entries = [e for e in pass1.values() if e["status"] == "ok"]
    hypothetical = [e for e in pass1.values() if e.get("hypothetical")]
    errored = [e for e in pass1.values() if e["status"] not in ("ok",)]

    # ================= A. timing =================
    lines.append("## A. Timing")
    lines.append("")
    p1_timestamps = sorted(e["created_at"] for e in pass1.values() if e.get("created_at"))
    p1_span = None
    if len(p1_timestamps) >= 2:
        p1_span = (datetime.fromisoformat(p1_timestamps[-1]) - datetime.fromisoformat(p1_timestamps[0])).total_seconds()
    lines.append(f"- Pass 1 (rewrite): {len(pass1)}/{len(sentences)} source sentences done, "
                 f"{len(hypothetical)} HYPOTHETICAL ({len(hypothetical) / len(pass1):.0%}), {len(errored)} "
                 f"errored. Wall-clock span across all invocations: " +
                 (_fmt_s(p1_span) if p1_span else f"{_fmt_s(pass1_seconds_this_run)} (this invocation only)"))
    lines.append(f"- Pass 2a (spaCy, no LLM): {len(simple_items)} simple sentences, {spacy_failed} failed to "
                 f"parse, {_fmt_s(spacy_seconds)} (this invocation; spaCy is deterministic and re-run in "
                 f"full every invocation, not checkpointed).")
    lines.append(f"- Pass 2b (LLM): {len(simple_items)} simple sentences to parse, "
                 f"{_fmt_s(llm_seconds_this_run)} this invocation ({len(per_call_metrics)} calls this "
                 f"invocation).")
    lines.append("")
    lines.append(f"{len(sentences)} source sentences -> {len(simple_items)} simple sentences "
                 f"({len(simple_items) / max(1, len(ok_entries)):.1f} simple sentences per rewritten source "
                 f"sentence on average).")
    lines.append("")
    if per_call_metrics:
        counts = [m.prompt_eval_count for m in per_call_metrics]
        lines.append(f"Pass 2b prompt_eval_count: first call {counts[0]}, median of the rest "
                     f"{statistics.median(counts[1:]):.0f}" if len(counts) > 1 else
                     f"Pass 2b prompt_eval_count: {counts[0]} (one call)")
        lines.append("")

    total_span = (p1_span or pass1_seconds_this_run) + spacy_seconds + llm_seconds_this_run
    lines.append(f"### Projection for one average character page ({total_span:.0f}s measured for Jiro's "
                 f"page, {len(sentences)} sentences, this specific page's length)")
    lines.append(f"Scales roughly linearly with sentence count -- no per-character number is claimed here "
                 f"beyond Jiro's own page, since v3's scope this round is deliberately just the one page "
                 f"(per instruction: small steps). A page 2x/3x this length would take roughly 2x/3x as long.")
    lines.append("")

    # ================= connect to Neo4j =================
    client = Neo4jClient(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    spacy_facts = _fetch_facts(client, run_id, "spacy")
    llm_facts = _fetch_facts(client, run_id, "llm")
    client.close()
    by_simple_spacy = {f["simple_sentence_id"]: f for f in spacy_facts}
    by_simple_llm = {f["simple_sentence_id"]: f for f in llm_facts}

    # ================= B. source -> simple sentences table =================
    lines.append("## B. Source sentence -> simple sentences (rewriting check)")
    lines.append("")
    lines.append("| id | section | source | simple sentences |")
    lines.append("|---:|---|---|---|")
    for sent in sentences:
        e = pass1.get(str(sent.id))
        if not e:
            continue
        if e.get("hypothetical"):
            simple_s = "*HYPOTHETICAL*"
        elif e["status"] != "ok":
            simple_s = f"*{e['status']}*"
        else:
            simple_s = "<br>".join(e["simple_sentences"]) or "*(none)*"
        lines.append(f"| {sent.id} | {e['section']} | {sent.text[:100].replace('|','/')} | "
                     f"{simple_s[:300].replace(chr(10),' ')} |")
    lines.append("")

    # ================= C. simple sentence -> fact, spaCy vs LLM =================
    lines.append("## C. Simple sentence -> fact: spaCy vs LLM")
    lines.append("")
    disagreements = 0
    rows = []
    for item in simple_items:
        sid = item["simple_id"]
        sp = by_simple_spacy.get(sid)
        lm = by_simple_llm.get(sid)
        sp_s = _fact_summary(sp) if sp else "(no fact)"
        lm_s = _fact_summary(lm) if lm else "(no fact)"
        agree = sp is not None and lm is not None and sp["kind"] == lm["kind"] and \
               sp["subject"] == lm["subject"] and sp["target"] == lm["target"]
        if not agree:
            disagreements += 1
        rows.append((item, sp_s, lm_s, agree))
    lines.append(f"{len(rows)} simple sentences compared, {disagreements} where subject/target/kind "
                 f"disagree between spaCy and LLM ({disagreements / len(rows):.0%}).")
    lines.append("")
    lines.append("### Disagreements only")
    lines.append("")
    lines.append("| simple sentence | spaCy | LLM |")
    lines.append("|---|---|---|")
    for item, sp_s, lm_s, agree in rows:
        if not agree:
            lines.append(f"| {item['simple_text'][:100].replace('|','/')} | {sp_s} | {lm_s} |")
    lines.append("")

    # ================= D. predicate_raw -> predicate (LLM only -- spaCy doesn't generalize) =================
    lines.append("## D. predicate_raw -> predicate generalization (LLM variant)")
    lines.append("")
    pairs = Counter((f["predicate_raw"], f["predicate"]) for f in llm_facts if f["kind"] == "edge")
    lines.append("| predicate_raw | predicate | count |")
    lines.append("|---|---|---:|")
    for (raw, gen), n in sorted(pairs.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {raw} | {gen} | {n} |")
    lines.append("")

    # ================= E. 20 random chains =================
    lines.append("## E. 20 random source -> simple -> fact chains for manual review")
    lines.append("")
    sample = random.sample(simple_items, min(20, len(simple_items)))
    for item in sample:
        sp = by_simple_spacy.get(item["simple_id"])
        lm = by_simple_llm.get(item["simple_id"])
        lines.append(f"- **source** (#{item['source_id']}, {item['section']}): "
                     f"{item['source_text'][:130]}")
        lines.append(f"  **simple**: {item['simple_text']}")
        lines.append(f"  **spaCy**: {_fact_summary(sp) if sp else '(none)'}")
        lines.append(f"  **LLM**: {_fact_summary(lm) if lm else '(none)'}")
    lines.append("")

    # ================= F. cypher =================
    lines.append("## F. Cypher query — Kyoka Jiro's v3 graph")
    lines.append("")
    lines.append("```cypher")
    lines.append(f"""MATCH (n)-[r]-(m)
WHERE (n.name = "{s.target_character}" OR m.name = "{s.target_character}")
  AND r.run_id = "{run_id}"
RETURN n, r, m""")
    lines.append("```")
    lines.append("")
    lines.append("Filter to one variant by adding `AND r.variant = \"llm\"` (or `\"spacy\"`) to the WHERE clause.")
    lines.append("")

    return "\n".join(lines)
