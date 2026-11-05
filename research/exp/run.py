"""Запуск экспериментов и сравнение с эталоном.

    python -m research.exp.run --methods all --model qwen3.5:9b            # всё, на qwen локально
    python -m research.exp.run --methods rel_anchored --limit 10           # быстрый прогон на 10 абзацах
    python -m research.exp.run --methods all --oracle                      # без модели: эталон сам с собой (проверка харнесса)
    python -m research.exp.run --score-only                                # пересчитать таблицу по готовым runs/

Ответы пишутся в research/runs/<model>/<method>.jsonl (+ stats), таблица — research/runs/<model>/summary.md.
"""
import argparse
import functools
import json
import re
import time
from pathlib import Path

from .llm import FakeLLM, LlamaCppLLM, OllamaLLM
from .methods import METHODS
from .pages import load_pages
from .roster import Roster
from .score import load_gold, score_relations, score_traits

ROOT = Path(__file__).resolve().parent.parent
REL_METHODS = ["rel_cooccur", "rel_free", "rel_anchored", "rel_pairwise", "rel_verify"]
TRAIT_METHODS = ["traits_lexicon", "traits_llm", "traits_anchored", "traits_verify"]
TRAIT_GOLD = "traits.yaml"
GOLD_DIR = ROOT / "gold"
ROSTERS = ROOT / "samples" / "rosters"
DEFAULT_ROSTER = "my_hero_academia"


def rel_golds() -> list[dict]:
    """Все эталоны связей research/gold/*.relations.yaml (у каждого: page_owner, page_file, roster)."""
    return [load_gold(p.name) for p in sorted(GOLD_DIR.glob("*.relations.yaml"))]


def roster_for(name: str, golds: list[dict]) -> Roster:
    r = next((g.get("roster") for g in golds if g["page_owner"] == name), DEFAULT_ROSTER)
    return Roster.load(ROSTERS / f"{r}.yaml", owner=name)


def _oracle_relations(golds: list[dict]):
    by_id = {x["id"]: (x, g) for g in golds for x in g["paragraphs"]}

    def run(paragraphs, roster, llm, owner):
        out = []
        for p in paragraphs:
            x, g = by_id.get(p.id, ({}, {"targets": {}}))
            out.append({"id": p.id, "relations": [
                {"name": c, "canonical": c, "affinity": v["affinity"][0],
                 "type": (g["targets"].get(c) or {}).get("types", ["unspecified"])[0]}
                for c, v in (x.get("links") or {}).items()]})
        return out
    return run


def _oracle_traits(gold: dict, pages: dict):
    by_para: dict[str, list] = {}
    for name, ch in gold["characters"].items():
        texts = {p.id: p.text.lower() for p in pages[name] if p.id in set(ch["paragraphs"])}
        for t in ch["traits"]:
            pid = next((i for i in ch["paragraphs"] if t["span"].lower() in texts.get(i, "")), ch["paragraphs"][0])
            by_para.setdefault(pid, []).append({"span": t["span"], "pole": t["pole"], "status": "actual"})
    return lambda paragraphs, roster, llm, owner: [{"id": p.id, "traits": by_para.get(p.id, [])} for p in paragraphs]


def _select(paragraphs, gold_ids: set[str], limit: int | None):
    ps = [p for p in paragraphs if p.id in gold_ids]
    return ps[:limit] if limit else ps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", default="all", help="comma list or 'all': " + ",".join(REL_METHODS + TRAIT_METHODS))
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--gguf", default=None, help="путь к GGUF: llama.cpp в процессе вместо Ollama (--model = имя для отчёта)")
    ap.add_argument("--temperature", type=float, default=0.0, help=">0 — повторные замеры со случайностью")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None, help="первые N размеченных абзацев (быстрый прогон)")
    ap.add_argument("--oracle", action="store_true", help="без LLM: эталон как предсказание (должно дать 1.0)")
    ap.add_argument("--score-only", action="store_true")
    args = ap.parse_args()

    methods = REL_METHODS + TRAIT_METHODS if args.methods == "all" else args.methods.split(",")
    tag = "oracle" if args.oracle else re.sub(r"[^\w.-]+", "_", args.model)
    if args.temperature > 0 and not args.oracle:
        tag += f"-t{args.temperature}-s{args.seed}"
    out_dir = ROOT / "runs" / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    golds, trait_gold = rel_golds(), load_gold(TRAIT_GOLD)
    rel_pages = {g["page_owner"]: load_pages(g["page_file"]) for g in golds}
    trait_pages = {name: load_pages(name.replace(" ", "_")) for name in trait_gold["characters"]}

    rows = []
    for m in methods:
        path = out_dir / f"{m}.jsonl"
        is_rel = m in REL_METHODS
        stats = {}
        if not args.score_only:
            if args.oracle:
                llm = FakeLLM(lambda *a: {})
            elif args.gguf and m not in ("rel_cooccur", "traits_lexicon"):
                llm = LlamaCppLLM(args.gguf, num_ctx=args.num_ctx, temperature=args.temperature, seed=args.seed)
            else:
                llm = OllamaLLM(args.model, num_ctx=args.num_ctx, temperature=args.temperature)
            t0 = time.monotonic()
            # resumable: каждый абзац дописывается сразу; уже посчитанные (с прошлого запуска) пропускаются
            done = {}
            if path.exists() and not args.oracle:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line:
                        r = json.loads(line)
                        done[r["id"]] = r
            prev = json.loads((out_dir / f"{m}.stats.json").read_text()) if done and (
                out_dir / f"{m}.stats.json").exists() else {}
            jobs = []
            if is_rel:
                fn = _oracle_relations(golds) if args.oracle else METHODS[m]
                m1 = out_dir / "rel_anchored.jsonl"
                if m == "rel_verify" and m1.exists() and not args.oracle:  # проверяем уже готовые ответы M1, а не считаем их заново
                    drafts = {r["id"]: r for r in (json.loads(x) for x in m1.read_text(encoding="utf-8").splitlines() if x)}
                    fn = functools.partial(METHODS[m], drafts=drafts)
                for g in golds:
                    roster = roster_for(g["page_owner"], golds)
                    ps = _select(rel_pages[g["page_owner"]], {x["id"] for x in g["paragraphs"]}, args.limit)
                    jobs += [(p, roster, g["page_owner"]) for p in ps]
            else:
                fn = _oracle_traits(trait_gold, trait_pages) if args.oracle else METHODS[m]
                t2 = out_dir / "traits_anchored.jsonl"
                if m == "traits_verify" and t2.exists() and not args.oracle:  # проверяем готовые ответы T2, а не считаем их заново
                    drafts = {r["id"]: r for r in (json.loads(x) for x in t2.read_text(encoding="utf-8").splitlines() if x)}
                    fn = functools.partial(METHODS[m], drafts=drafts)
                for name, ch in trait_gold["characters"].items():
                    roster = roster_for(name, golds)
                    jobs += [(p, roster, name) for p in _select(trait_pages[name], set(ch["paragraphs"]), args.limit)]
            mode = "a" if done else "w"
            with path.open(mode, encoding="utf-8") as fh:
                for p, roster, owner in jobs:
                    if p.id in done:
                        continue
                    for r in fn([p], roster, llm, owner):
                        done[r["id"]] = r
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                        fh.flush()
            records = [done[p.id] for p, _, _ in jobs if p.id in done]
            stats = {**vars(llm.stats), "wall_s": round(time.monotonic() - t0, 1), "paragraphs": len(records)}
            for k in ("calls", "prompt_tokens", "gen_tokens", "seconds", "schema_violations", "errors", "wall_s"):
                stats[k] = round(stats.get(k, 0) + prev.get(k, 0), 1)
            (out_dir / f"{m}.stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
        elif path.exists():
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            sp = out_dir / f"{m}.stats.json"
            stats = json.loads(sp.read_text()) if sp.exists() else {}
        else:
            continue

        if is_rel:
            c = {}
            per_char, fp_all, fn_all = {}, [], []
            for g in golds:
                roster = roster_for(g["page_owner"], golds)
                texts = {p.id: (p.section, p.text) for p in rel_pages[g["page_owner"]]}
                ids = {x["id"] for x in g["paragraphs"]}
                s = score_relations([r for r in records if r["id"] in ids], g, roster, texts)
                per_char[g["page_owner"]] = s
                fp_all += s["fp"]
                fn_all += s["fn"]
                for k, v in s["counts"].items():
                    c[k] = c.get(k, 0) + v
            (out_dir / f"{m}.errors.txt").write_text("FP\n" + "\n".join(fp_all) + "\n\nFN\n" + "\n".join(fn_all),
                                                     encoding="utf-8")
            (out_dir / f"{m}.per_character.json").write_text(json.dumps(
                {k: {kk: vv for kk, vv in v.items() if kk not in ("fp", "fn")} for k, v in per_char.items()},
                indent=1, ensure_ascii=False), encoding="utf-8")
            d = lambda a, b: a / b if b else 0.0  # noqa: E731
            P, R = d(c["tp"], c["tp"] + c["fp"]), d(c["tp"], c["tp"] + c["fn"])
            rows.append((m, f"{P:.2f} / {d(c['tp'], c['tp'] + c['fp'] + c['opt']):.2f}", f"{R:.2f}",
                         f"{d(2 * P * R, P + R):.2f}", f"{d(c['aff_ok'], c['tp']):.2f}",
                         f"{d(c['halluc'], c['names_out']):.1%}", f"{d(c['tP'], c['tP_all']):.2f}",
                         f"{d(c['tR_hit'], c['tR_all']):.2f}", "", "", _speed(stats)))
        else:
            agg = {"tp": 0.0, "pred": 0, "gold": 0, "pole": 0.0, "bad": 0, "nit": 0, "all": 0}
            per_tr: dict[str, dict] = {}
            notes = []
            for name, ch in trait_gold["characters"].items():
                ids = set(ch["paragraphs"])
                texts = {p.id: p.text for p in trait_pages[name]}
                s = score_traits([r for r in records if r["id"] in ids], ch, texts)
                per_tr[name] = {k: v for k, v in s.items() if k not in ("missed", "unmatched", "not_in_text")}
                tp = s["trait_P"] * s["predicted"]
                agg["tp"] += tp
                agg["pred"] += s["predicted"]
                agg["gold"] += len(ch["traits"])
                agg["pole"] += s["pole_acc"] * tp
                agg["bad"] += s["not_trait_hits"]
                agg["nit"] += len(s["not_in_text"])
                agg["all"] += sum(len(r.get("traits", [])) for r in records if r["id"] in ids)
                notes.append(f"## {name}\nmissed: {s['missed']}\nunmatched (проверить руками — эталон может быть неполон): "
                             f"{s['unmatched']}\nnot in text (выдуманные фрагменты): {s['not_in_text']}\n")
            (out_dir / f"{m}.errors.txt").write_text("\n".join(notes), encoding="utf-8")
            (out_dir / f"{m}.per_character.json").write_text(json.dumps(per_tr, indent=1, ensure_ascii=False),
                                                             encoding="utf-8")
            p = agg["tp"] / agg["pred"] if agg["pred"] else 0.0
            r = agg["tp"] / agg["gold"] if agg["gold"] else 0.0
            f = 2 * p * r / (p + r) if p + r else 0.0
            nit = f"{agg['nit'] / agg['all']:.1%} (not in text)" if agg["all"] else ""
            rows.append((m, f"{p:.2f}", f"{r:.2f}", f"{f:.2f}", "", nit, "", "",
                         f"{agg['pole'] / agg['tp']:.2f}" if agg["tp"] else "-", str(agg["bad"]), _speed(stats)))

    header = ("method", "P (lenient/strict)", "R", "F1", "affinity", "halluc.names", "type_P", "type_R", "pole_acc",
              "not_trait", "speed")
    table = "| " + " | ".join(header) + " |\n|" + "---|" * len(header) + "\n"
    table += "".join("| " + " | ".join(r) + " |\n" for r in rows)
    (out_dir / "summary.md").write_text(f"# {tag}\n\n{table}", encoding="utf-8")
    print(table)
    print(f"-> {out_dir}")


def _speed(stats: dict) -> str:
    if not stats or not stats.get("paragraphs"):
        return "-"
    return f"{stats.get('wall_s', 0) / stats['paragraphs']:.1f}s/para, {stats.get('calls', 0)} calls"


if __name__ == "__main__":
    main()
