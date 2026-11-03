"""Re-check saved 'yes' quotes with the tolerant validator, no model calls. Rewrites result.json / flags_result.json."""
import json, re
from pathlib import Path
from run import norm, words, trigrams, quote_ok

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "result.json").read_text(encoding="utf-8"))
changed = []
for c, flags in R.items():
    ctx = (HERE / "contexts" / (re.sub(r"\W+", "_", c) + ".txt")).read_text(encoding="utf-8")
    ctx_norm, ctx_tri = norm(ctx), trigrams(words(ctx))
    for f, r in flags.items():
        if r["model_said"] == "yes":
            new = "yes" if (r["quote"] and quote_ok(r["quote"], ctx_norm, ctx_tri)) else "no_data"
            if new != r["answer"]:
                changed.append((c, f, r["answer"], new)); r["answer"] = new
(HERE / "result.json").write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
(HERE / "flags_result.json").write_text(json.dumps({c: {f: r["answer"] for f, r in fl.items()} for c, fl in R.items()}, ensure_ascii=False), encoding="utf-8")
print(f"restored {len(changed)} answers no_data -> yes")
for c, f, a, n in changed: print(f"  {c:<18}{f:<26}{a} -> {n}")
left = sum(1 for c in R for f in R[c] if R[c][f]["answer"] != R[c][f]["model_said"])
print(f"still downgraded: {left} of 320")
