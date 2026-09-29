"""Builds graph_extract/REPORT.md. Edge/trait tallies come from Neo4j (the run_id's full accumulated state,
correct across resumed/multi-invocation runs); timing/prompt_eval_count come from this invocation's own
calls only (see the note the report itself prints if the run was resumed from a checkpoint)."""
import random
import statistics
from collections import Counter

from yuzuki_local.external.neo4j_client import Neo4jClient


def _fmt_s(x: float) -> str:
    return f"{x:.1f}s" if x < 120 else f"{x / 60:.1f}min"


def _fetch_actions(client: Neo4jClient, run_id: str) -> list[dict]:
    q = ("MATCH (s)-[r:ACTION {run_id:$run_id}]->(o) RETURN s.name AS subject, labels(s) AS subject_labels, "
        "r.action AS action, r.action_raw AS action_raw, r.manner AS manner, o.name AS target, "
        "labels(o) AS target_labels, r.complement AS complement, r.modality AS modality, "
        "r.negated AS negated, r.source_sentence AS source_sentence, r.section AS section, "
        "r.valid_source AS valid_source, r.created_at AS created_at")
    with client.session() as session:
        return [dict(rec) for rec in session.run(q, run_id=run_id)]


def _fetch_traits(client: Neo4jClient, run_id: str) -> list[dict]:
    q = ("MATCH (c:Character)-[r:DESCRIBED_AS {run_id:$run_id}]->(t:Trait) RETURN c.name AS character, "
        "t.name AS trait, r.said_by AS said_by, r.negated AS negated, "
        "r.source_sentence AS source_sentence, r.section AS section, r.valid_source AS valid_source")
    with client.session() as session:
        return [dict(rec) for rec in session.run(q, run_id=run_id)]


def _fetch_old_run_stats(client: Neo4jClient) -> dict | None:
    """v1 run used a random run_id; find it by looking for any ACTION edge that is NOT jiro-v2."""
    q = ("MATCH ()-[r:ACTION]->() WHERE r.run_id <> 'jiro-v2' RETURN r.run_id AS run_id, count(r) AS n "
        "ORDER BY n DESC LIMIT 1")
    with client.session() as session:
        rec = session.run(q).single()
        if not rec:
            return None
        old_id = rec["run_id"]
        rows = list(session.run(
            "MATCH (s)-[r:ACTION {run_id:$id}]->(o) RETURN s.name AS subject, r.verb AS verb, "
            "o.name AS object, r.valid_source AS valid_source", id=old_id))
        return {"run_id": old_id, "edges": rows}


def _violation_rate(subjects: list[str], targets: list[str]) -> dict:
    """v1-comparable rule checks: bare-word violations we can still detect post hoc.
    A None subject/target is a People node (schema-correct -- People has no `.name`), not a violation."""
    subjects = [x for x in subjects if x is not None]
    targets = [x for x in targets if x is not None]
    multiword_verb_in_target = sum(1 for t in targets if len(t.split()) > 4)
    bare_generic = sum(1 for x in (*subjects, *targets) if x.strip().lower() in
                       {"people", "students", "villains", "crowd", "everyone", "class"} and x.strip() != "people")
    return {"target_looks_like_a_clause (>4 words)": multiword_verb_in_target,
           "bare_generic_noun_not_resolved_to_people": bare_generic}


def build_report(*, s, run_id, pages, per_page_chars, all_chunks, extraction_seconds, per_call_metrics) -> str:
    lines = [f"# graph_extract — Kyoka Jiro ({s.universe}), schema v2", "",
            f"run_id={run_id}, model={s.model}, temperature={s.temperature}, num_ctx={s.num_ctx}.", ""]

    lines.append("## Scope")
    lines.append("")
    lines.append("Same page set and same 3-8 sentence chunking as the v1 run (no re-experimentation this "
                 "time, per instruction). See v1's REPORT.md / config.yaml comment for why this page set "
                 "(pages ABOUT Jiro, not all 737 pages that merely mention her name) was chosen.")
    lines.append("")
    for title in s.pages:
        n = per_page_chars.get(title)
        lines.append(f"- {title}: " + (f"{n} chars after cleaning" if n is not None else "**NOT FOUND**"))
    lines.append("")

    # ================= connect to Neo4j for the accumulated (possibly multi-invocation) state =========
    client = Neo4jClient(s.neo4j_uri, s.neo4j_user, s.neo4j_password)
    actions = _fetch_actions(client, run_id)
    traits = _fetch_traits(client, run_id)
    old = _fetch_old_run_stats(client)
    client.close()

    valid_actions = [a for a in actions if a["valid_source"]]
    valid_traits = [t for t in traits if t["valid_source"]]

    # ================= A. timing =================
    lines.append("## A. Timing")
    lines.append("")
    prompt_counts = [m.prompt_eval_count for m in per_call_metrics]
    lines.append(f"This invocation: {len(per_call_metrics)} LLM calls in {_fmt_s(extraction_seconds)}. "
                 f"Total accumulated in Neo4j for run_id={run_id}: {len(actions)} ACTION edges, "
                 f"{len(traits)} DESCRIBED_AS edges.")
    lines.append("")

    # Real wall-clock span from the edges' own created_at timestamps -- correct even when this specific
    # invocation processed 0 new chunks (e.g. it crashed building the report after a fully-finished
    # extraction pass, and got rerun just to regenerate the report from what's already in Neo4j).
    timestamps = sorted(a["created_at"] for a in actions if a["created_at"])
    span_seconds = None
    if len(timestamps) >= 2:
        from datetime import datetime
        span_seconds = (datetime.fromisoformat(timestamps[-1]) - datetime.fromisoformat(timestamps[0])).total_seconds()
        lines.append(f"Wall-clock span from the first to the last edge's `created_at` (covers every "
                     f"invocation this run took, crash-resumed or not): {_fmt_s(span_seconds)}.")
        lines.append("")

    if prompt_counts:
        lines.append(f"prompt_eval_count: first call {prompt_counts[0]}, "
                     f"median of the rest {statistics.median(prompt_counts[1:]):.0f}" if len(prompt_counts) > 1
                     else f"prompt_eval_count: {prompt_counts[0]} (only one call this invocation)")
    total_context_chars = sum(len(c.text) for c in all_chunks)
    lines.append(f"Jiro's total processed text: {total_context_chars} chars across {len(all_chunks)} "
                 f"chunks (chunks are independent LLM calls, no shared prefix across chunks beyond the "
                 f"instruction+few-shot+roster block, which IS identical and at the front of every "
                 f"prompt per the ordering instruction -- prefix cache should apply to that shared part).")
    lines.append("")
    per_char = span_seconds or (extraction_seconds if len(per_call_metrics) == len(all_chunks) else None)
    if per_char:
        lines.append(f"### Projections ({per_char:.0f}s for one character)")
        lines.append(f"- 100 characters: {_fmt_s(per_char * 100)} ({per_char * 100 / 3600:.1f}h)")
        lines.append(f"- 50 universes x 100 characters: {per_char * 100 * 50 / 86400:.1f} days, sequential, "
                     f"one GPU.")
    else:
        lines.append("Projection skipped: not enough data to estimate a clean per-character time yet.")
    lines.append("")

    # ================= B. comparison with v1 =================
    lines.append("## B. Comparison with the v1 run")
    lines.append("")
    if old:
        old_valid = [e for e in old["edges"] if e["valid_source"]]
        lines.append(f"v1 (run_id={old['run_id']}): {len(old['edges'])} edges, {len(old_valid)} valid source "
                     f"({len(old_valid) / len(old['edges']):.0%} valid)." if old["edges"] else "v1: 0 edges.")
    else:
        lines.append("No v1 ACTION edges found in Neo4j (the v1 run was stopped before it reached the "
                     "Neo4j-write stage when this v2 rewrite was requested, so there is nothing to compare "
                     "against -- see the reply message for the few example edges v1 produced on individual "
                     "test chunks before that point).")
    lines.append("")
    lines.append(f"v2 (this run): {len(actions)} edges, {len(valid_actions)} valid source "
                 f"({len(valid_actions) / len(actions):.0%} valid)." if actions else "v2: 0 edges.")
    lines.append("")
    v2_violations = _violation_rate([a["subject"] for a in valid_actions], [a["target"] for a in valid_actions])
    lines.append("v2 rule-violation checks (post hoc, on what actually got written -- the schema itself "
                 "blocks a target/subject that isn't a noun via the field description, this checks whether "
                 "the model still slipped past it):")
    for k, v in v2_violations.items():
        lines.append(f"  - {k}: {v}/{len(valid_actions)}")
    lines.append("")

    # ================= C. action_raw -> action table =================
    lines.append("## C. action_raw -> action generalization")
    lines.append("")
    pairs = Counter((a["action_raw"], a["action"]) for a in valid_actions)
    lines.append("| action_raw | action | count |")
    lines.append("|---|---|---:|")
    for (raw, gen), n in sorted(pairs.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {raw} | {gen} | {n} |")
    lines.append("")

    # ================= D. all Jiro ACTION edges =================
    lines.append("## D. All ACTION edges where Kyoka Jiro is subject or target")
    lines.append("")
    jiro_actions = [a for a in valid_actions if a["subject"] == s.target_character or a["target"] == s.target_character]
    lines.append(f"{len(jiro_actions)} edges.")
    lines.append("")
    lines.append("| subject | action | manner | target | complement | modality | neg | source |")
    lines.append("|---|---|---|---|---|---|:-:|---|")
    for a in jiro_actions:
        lines.append(f"| {a['subject']} | {a['action']} | {a['manner']} | {a['target']} | {a['complement']} | "
                     f"{a['modality']} | {'Y' if a['negated'] else ''} | "
                     f"{a['source_sentence'][:110].replace('|','/')} |")
    lines.append("")

    # ================= E. all Jiro DESCRIBED_AS =================
    lines.append("## E. All DESCRIBED_AS for Kyoka Jiro")
    lines.append("")
    jiro_traits = [t for t in valid_traits if t["character"] == s.target_character]
    lines.append(f"{len(jiro_traits)} traits.")
    lines.append("")
    for t in jiro_traits:
        lines.append(f"- **{t['trait']}**" + (" (negated)" if t["negated"] else "") +
                     f", said by {t['said_by']} — \"{t['source_sentence'][:150]}\"")
    lines.append("")

    # ================= F. random sample =================
    lines.append("## F. 20 random edges for manual review")
    lines.append("")
    sample = random.sample(valid_actions, min(20, len(valid_actions)))
    for a in sample:
        lines.append(f"- {a['subject']} --[{a['action']}" + (f" ({a['manner']})" if a["manner"] else "") +
                     f"]--> {a['target']}" + (f" ({a['complement']})" if a["complement"] else "") +
                     f" [{a['modality']}{', negated' if a['negated'] else ''}] — \"{a['source_sentence'][:140]}\"")
    lines.append("")

    # ================= G. invalid share =================
    lines.append("## G. Invalid source_sentence share")
    lines.append("")
    lines.append(f"ACTION: {len(actions) - len(valid_actions)}/{len(actions)} invalid "
                 f"({(len(actions) - len(valid_actions)) / len(actions):.0%})" if actions else "ACTION: n/a (0 edges)")
    lines.append(f"DESCRIBED_AS: {len(traits) - len(valid_traits)}/{len(traits)} invalid "
                 f"({(len(traits) - len(valid_traits)) / len(traits):.0%})" if traits else "DESCRIBED_AS: n/a (0 edges)")
    lines.append("")

    # ================= H. cypher =================
    lines.append("## H. Cypher query — Kyoka Jiro's graph, this run")
    lines.append("")
    lines.append("```cypher")
    lines.append(f"""MATCH (n)-[r]-(m)
WHERE (n.name = "{s.target_character}" OR m.name = "{s.target_character}")
  AND r.run_id = "{run_id}"
RETURN n, r, m""")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)
