"""Builds extract_v3/REPORT.md. Fact tallies come from Neo4j (full accumulated state, correct across
resumed/multi-invocation runs); pass-1 stats come from the local pass1 cache (has its own created_at per
entry, so it's resumption-safe too)."""
import random
import statistics
from collections import Counter
from datetime import datetime

from .external.neo4j_client import Neo4jClient


def _fmt_s(x: float) -> str:
    return f"{x:.1f}s" if x < 120 else f"{x / 60:.1f}min"


def _fetch_facts(client: Neo4jClient, run_id: str) -> list[dict]:
    q = ("MATCH (s)-[r:EDGE {run_id:$run_id}]->(o) RETURN 'edge' AS kind, s.name AS subject, "
        "r.predicate AS predicate, r.predicate_raw AS predicate_raw, r.via AS via, o.name AS target, "
        "r.description AS description, r.modality AS modality, r.negated AS negated, r.mutual AS mutual, "
        "r.frequency AS frequency, r.degree AS degree, r.certainty AS certainty, r.former AS former, "
        "r.simple_sentence_id AS simple_sentence_id, r.source_sentence_id AS source_sentence_id, "
        "r.source_sentence AS source_sentence "
        "UNION "
        "MATCH (s)-[r:HAS_PROPERTY {run_id:$run_id}]->(p) RETURN 'property' AS kind, "
        "s.name AS subject, null AS predicate, null AS predicate_raw, null AS via, p.name AS target, "
        "r.description AS description, r.modality AS modality, r.negated AS negated, false AS mutual, "
        "r.frequency AS frequency, r.degree AS degree, r.certainty AS certainty, r.former AS former, "
        "r.simple_sentence_id AS simple_sentence_id, r.source_sentence_id AS source_sentence_id, "
        "r.source_sentence AS source_sentence")
    with client.session() as session:
        return [dict(rec) for rec in session.run(q, run_id=run_id)]


def _fact_summary(f: dict) -> str:
    if f["kind"] == "property":
        return f"PROPERTY({f['subject']}, {f['target']})" + (" [neg]" if f["negated"] else "")
    return (f"EDGE({f['subject']} -{f['predicate']}-> {f['target']})" +
           (f" via={f['via']}" if f.get("via") else "") + (" [neg]" if f["negated"] else "") +
           (" [mutual]" if f["mutual"] else ""))


def build_report(*, s, run_id, sentences, pass1, simple_items, pass1_seconds_this_run,
                 pass2_seconds_this_run, per_call_metrics) -> str:
    lines = [f"# extract_v3 — Kyoka Jiro's own page ({s.universe})", "",
            f"run_id={run_id}, model={s.model}, temperature={s.temperature}, think=false, pages={s.pages!r}.",
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
                 f"{len(hypothetical)} HYPOTHETICAL ({len(hypothetical) / max(1, len(pass1)):.0%}), "
                 f"{len(errored)} errored. Wall-clock span across all invocations: " +
                 (_fmt_s(p1_span) if p1_span else f"{_fmt_s(pass1_seconds_this_run)} (this invocation only)"))
    lines.append(f"- Pass 2 (LLM parse): {len(simple_items)} simple sentences to parse, "
                 f"{_fmt_s(pass2_seconds_this_run)} this invocation ({len(per_call_metrics)} calls this "
                 f"invocation).")
    lines.append("")
    lines.append(f"{len(sentences)} source sentences -> {len(simple_items)} simple sentences "
                 f"({len(simple_items) / max(1, len(ok_entries)):.1f} simple sentences per rewritten source "
                 f"sentence on average).")
    lines.append("")
    if per_call_metrics:
        counts = [m.prompt_eval_count for m in per_call_metrics]
        lines.append(f"Pass 2 prompt_eval_count: first call {counts[0]}, median of the rest "
                     f"{statistics.median(counts[1:]):.0f}" if len(counts) > 1 else
                     f"Pass 2 prompt_eval_count: {counts[0]} (one call)")
        lines.append("")

    total_span = (p1_span or pass1_seconds_this_run) + pass2_seconds_this_run
    lines.append(f"### Projection for one average character page ({total_span:.0f}s measured for Jiro's "
                 f"page, {len(sentences)} sentences, this specific page's length)")
    lines.append(f"Scales roughly linearly with sentence count -- no per-character number is claimed here "
                 f"beyond Jiro's own page, since v3's scope this round is deliberately just the one page "
                 f"(per instruction: small steps). A page 2x/3x this length would take roughly 2x/3x as long.")
    lines.append("")

    # ================= connect to Neo4j =================
    client = Neo4jClient(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    facts = _fetch_facts(client, run_id)
    client.close()
    by_simple = {f["simple_sentence_id"]: f for f in facts}

    # ================= B. source -> simple sentences table =================
    lines.append("## B. Source sentence -> simple sentences (rewriting check)")
    lines.append("")
    lines.append("| id | page | section | source | simple sentences |")
    lines.append("|---:|---|---|---|---|")
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
        lines.append(f"| {sent.id} | {e.get('page','')} | {e['section']} | "
                     f"{sent.text[:100].replace('|','/')} | {simple_s[:300].replace(chr(10),' ')} |")
    lines.append("")

    # ================= C. simple sentence -> fact =================
    lines.append("## C. Simple sentence -> fact")
    lines.append("")
    lines.append(f"{len(simple_items)} simple sentences, {len(facts)} facts written "
                 f"({len(facts) / max(1, len(simple_items)):.0%} yield -- the rest failed to parse or the "
                 f"call errored).")
    lines.append("")
    lines.append("| simple sentence | fact |")
    lines.append("|---|---|")
    for item in simple_items:
        f = by_simple.get(item["simple_id"])
        lines.append(f"| {item['simple_text'][:120].replace('|','/')} | "
                     f"{_fact_summary(f) if f else '(no fact)'} |")
    lines.append("")

    # ================= D. predicate_raw -> predicate =================
    lines.append("## D. predicate_raw -> predicate generalization")
    lines.append("")
    pairs = Counter((f["predicate_raw"], f["predicate"]) for f in facts if f["kind"] == "edge")
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
        f = by_simple.get(item["simple_id"])
        lines.append(f"- **source** (#{item['source_id']}, {item.get('page','')}/{item['section']}): "
                     f"{item['source_text'][:130]}")
        lines.append(f"  **simple**: {item['simple_text']}")
        lines.append(f"  **fact**: {_fact_summary(f) if f else '(none)'}")
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

    return "\n".join(lines)
