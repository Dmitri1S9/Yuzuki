"""Second check for every 'yes': does the quote ALONE show the property? Short prompt (definition + quote),
no page context. A 'no' verdict downgrades the answer to no_data; the pre-verification answer is kept."""
import json, requests, yaml
from pathlib import Path
from jinja2 import Template

HERE = Path(__file__).resolve().parent
flags = {f["id"]: f for f in yaml.safe_load((HERE / "flags.yaml").read_text(encoding="utf-8"))["flags"]}
SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["yes", "no"]}}, "required": ["verdict"]}
T = Template('''Character: {{ c }}.
PROPERTY: {{ f.id }}
QUESTION: {{ f.question }}
COUNTS AS YES: {{ f.look_for }}
DOES NOT COUNT: {{ f.not_this }}

QUOTE from the wiki: "{{ q }}"

Judge ONLY this quote. Does the quote by itself clearly show that the property holds for {{ c }}?
A quote that merely mentions the character, describes a different trait, or describes an event every character goes
through does not count. Return only JSON: {"verdict": "yes" | "no"}''')

R = json.loads((HERE / "result.json").read_text(encoding="utf-8"))
dropped = []
n = 0
for c, fl in R.items():
    for fid, r in fl.items():
        if r["answer"] != "yes":
            continue
        n += 1
        r.setdefault("answer_before_verify", "yes")
        resp = requests.post("http://127.0.0.1:11434/api/chat", timeout=300, json={
            "model": "qwen3.5:9b", "stream": False, "think": False, "keep_alive": "30m", "format": SCHEMA,
            "messages": [{"role": "user", "content": T.render(c=c, f=flags[fid], q=r["quote"])}],
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 30}}).json()
        v = json.loads(resp["message"]["content"])["verdict"]
        r["verify"] = v
        if v == "no":
            r["answer"] = "no_data"; dropped.append((c, fid))
(HERE / "result.json").write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
(HERE / "flags_result.json").write_text(json.dumps({c: {f: r["answer"] for f, r in fl.items()} for c, fl in R.items()}, ensure_ascii=False), encoding="utf-8")
print(f"verified {n} yes-answers, dropped {len(dropped)}")
for c, f in dropped: print(f"  {c:<18}{f}")
for c, fl in R.items():
    cnt = {k: sum(1 for r in fl.values() if r["answer"] == k) for k in ("yes", "no", "no_data")}
    print(f"{c:<18} yes={cnt['yes']} no={cnt['no']} no_data={cnt['no_data']}")
