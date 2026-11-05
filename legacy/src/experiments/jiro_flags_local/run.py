"""Flags on the local model: one flag = one call, yes/no/no_data. A quote is required (and verified
against the context) only for "yes"; "no"/"no_data" are kept as the model said them.
Usage: python run.py "Kyoka Jiro" [--pass N] [--temp T]   (Jiro uses the prebuilt combined context)
Spec/prompt copied from the old yuzuki_local (wip-full-snapshot); nothing in the project is modified.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
import yaml
from jinja2 import Template

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))  # src/, for extract_v3.external.*
CHARS_PER_TOKEN = 3.6   # conservative (measured ~4.4 on this wiki text) so the window is never short
MODEL = "qwen3.5:9b"
UNIVERSE = "My Hero Academia"
DUMP = Path("/home/Di/Загрузки/bokunoheroacademia_pages_current.xml")

SCHEMA = {
    "type": "object",
    "properties": {"flag": {"type": "string"},
                  "answer": {"type": "string", "enum": ["yes", "no", "no_data"]},
                  "quotes": {"type": "array", "items": {"type": "string"}, "maxItems": 1}},
    "required": ["flag", "answer", "quotes"],
}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def trigrams(ws: list[str]) -> set:
    return set(zip(ws, ws[1:], ws[2:]))


def quote_ok(quote: str, ctx_norm: str, ctx_tri: set, threshold: float = 0.85) -> bool:
    """Exact normalized substring, or (tolerant of quote marks/dashes/case/small rewordings and quotes stitched
    from two nearby places) >= 85% of the quote's word trigrams occur in the context. Invented text fails."""
    if norm(quote) in ctx_norm:
        return True
    qw = words(quote)
    q_tri = trigrams(qw)
    if len(qw) < 4 or not q_tri:
        return False
    return len(q_tri & ctx_tri) / len(q_tri) >= threshold


def build_context(character: str) -> str:
    cache = HERE / "contexts" / (re.sub(r"\W+", "_", character) + ".txt")
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    from extract_v3.external.dump_reader import DumpReader
    from extract_v3.external.wikitext_cleaner import WikiTextCleaner
    titles = [character, f"{character}/Relationships", f"{character}/Synopsis"]
    texts = {p.title: p.text for p in DumpReader(DUMP).pages() if p.title in titles}
    cleaner = WikiTextCleaner(min_paragraph_words=4)
    lines = []
    for t in titles:
        if t not in texts:
            continue
        lines.append(f"=== PAGE: {t} ===")
        for s in cleaner.sections(texts[t]):
            lines.append(f"== {s.name} ==")
            lines.extend(s.paragraphs)
            lines.append("")
    ctx = "\n".join(lines)   # full pages, never truncated
    cache.parent.mkdir(exist_ok=True)
    cache.write_text(ctx, encoding="utf-8")
    return ctx


def run(character: str, pass_no: int, temp: float) -> list[dict]:
    flags = yaml.safe_load((HERE / "flags.yaml").read_text(encoding="utf-8"))["flags"]
    tpl = Template((HERE / "flag_prompt.j2").read_text(encoding="utf-8"))
    context = build_context(character)
    ctx_norm = norm(context)
    ctx_tri = trigrams(words(context))
    num_ctx = -(-int(len(context) / CHARS_PER_TOKEN + 2500) // 2048) * 2048   # fixed for this whole run
    print(f"{character}: pass {pass_no}, temp {temp}, {len(flags)} flags, context {len(context)} chars, num_ctx {num_ctx}", flush=True)
    results, t0 = [], time.monotonic()
    for flag in flags:
        prompt = tpl.render(context=context, character=character, universe=UNIVERSE, flag=flag)
        r = requests.post("http://127.0.0.1:11434/api/chat", timeout=600, json={
            "model": MODEL, "stream": False, "think": False, "keep_alive": "30m", "format": SCHEMA,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": temp, "seed": pass_no, "num_ctx": num_ctx, "num_predict": 300}})
        r.raise_for_status()
        data = r.json()
        try:
            reply = json.loads(data["message"]["content"])
            raw, quotes = reply["answer"], reply.get("quotes", [])
        except Exception:
            raw, quotes = "error", []
        final, downgraded = raw, False
        if raw == "yes" and not (quotes and quote_ok(quotes[0], ctx_norm, ctx_tri)):
            final, downgraded = "no_data", True
        results.append(dict(flag=flag["id"], answer_raw=raw, answer=final, downgraded=downgraded,
                            quote=quotes[0] if raw == "yes" and quotes else None,
                            cached=data.get("prompt_eval_cached_count"), prompt_eval=data.get("prompt_eval_count"),
                            done_reason=data.get("done_reason")))
    c = {k: sum(1 for x in results if x["answer"] == k) for k in ("yes", "no", "no_data", "error")}
    print(f"  done in {time.monotonic()-t0:.0f}s: yes={c['yes']} no={c['no']} no_data={c['no_data']} "
          f"error={c['error']} downgraded_yes={sum(x['downgraded'] for x in results)}", flush=True)
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("character")
    ap.add_argument("--pass", dest="pass_no", type=int, default=1)
    ap.add_argument("--temp", type=float, default=0.0)   # single pass, deterministic
    a = ap.parse_args()
    res = run(a.character, a.pass_no, a.temp)
    out = HERE / "results" / f"{re.sub(r'\W+', '_', a.character)}_p{a.pass_no}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
