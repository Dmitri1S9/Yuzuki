"""Запуск экспериментов и сравнение с эталоном.

    python -m research.exp.run --methods all --model qwen3.5:9b            # всё, на qwen локально
    python -m research.exp.run --methods rel_anchored --limit 10           # быстрый прогон на 10 абзацах
    python -m research.exp.run --methods all --oracle                      # без модели: эталон сам с собой (проверка харнесса)
    python -m research.exp.run --score-only                                # пересчитать таблицу по готовым runs/

Ответы пишутся в research/runs/<model>/<method>.jsonl (+ stats), таблица — research/runs/<model>/summary.md.
"""
import argparse
import json
import re
import time
from pathlib import Path

from .llm import FakeLLM, OllamaLLM
from .methods import METHODS
from .pages import load_pages
from .roster import Roster
from .score import load_gold, score_relations, score_traits

ROOT = Path(__file__).resolve().parent.parent
REL_METHODS = ["rel_cooccur", "rel_free", "rel_anchored", "rel_pairwise", "rel_verify"]
TRAIT_METHODS = ["traits_lexicon", "traits_llm"]
REL_GOLD, TRAIT_GOLD = "kyoka_jiro.relations.yaml", "traits.yaml"
ROSTER = ROOT / "samples" / "rosters" / "my_hero_academia.yaml"


def _oracle_relations(gold: dict):
    by_id = {g["id"]: g for g in gold["paragraphs"]}

    def run(paragraphs, roster, llm, owner):
        out = []
        for p in paragraphs:
            links = (by_id.get(p.id) or {}).get("links") or {}
            out.append({"id": p.id, "relations": [
                {"name": c, "canonical": c, "affinity": v["affinity"][0],
                 "type": (gold["targets"].get(c) or {}).get("types", ["unspecified"])[0]} for c, v in links.items()]})
        return out
    return run


def _oracle_traits(gold: dict):
    by_para: dict[str, list] = {}
    for ch in gold["characters"].values():
        by_para.setdefault(ch["paragraphs"][0], []).extend(
            {"span": t["span"], "pole": t["pole"], "status": "actual"} for t in ch["traits"])
    return lambda paragraphs, roster, llm, owner: [{"id": p.id, "traits": by_para.get(p.id, [])} for p in paragraphs]


def _select(paragraphs, gold_ids: set[str], limit: int | None):
    ps = [p for p in paragraphs if p.id in gold_ids]
    return ps[:limit] if limit else ps


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--methods", default="all", help="comma list or 'all': " + ",".join(REL_METHODS + TRAIT_METHODS))
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--limit", type=int, default=None, help="первые N размеченных абзацев (быстрый прогон)")
    ap.add_argument("--oracle", action="store_true", help="без LLM: эталон как предсказание (должно дать 1.0)")
    ap.add_argument("--score-only", action="store_true")
    args = ap.parse_args()

    methods = REL_METHODS + TRAIT_METHODS if args.methods == "all" else args.methods.split(",")
    tag = "oracle" if args.oracle else re.sub(r"[^\w.-]+", "_", args.model)
    out_dir = ROOT / "runs" / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    rel_gold, trait_gold = load_gold(REL_GOLD), load_gold(TRAIT_GOLD)
    rel_pages = load_pages("Kyoka_Jiro")
    trait_pages = {name: load_pages(name.replace(" ", "_")) for name in trait_gold["characters"]}

    rows = []
    for m in methods:
        path = out_dir / f"{m}.jsonl"
        is_rel = m in REL_METHODS
        stats = {}
        if not args.score_only:
            llm = FakeLLM(lambda *a: {}) if args.oracle else OllamaLLM(args.model, num_ctx=args.num_ctx)
            t0 = time.monotonic()
            records = []
            if is_rel:
                fn = _oracle_relations(rel_gold) if args.oracle else METHODS[m]
                ps = _select(rel_pages, {g["id"] for g in rel_gold["paragraphs"]}, args.limit)
                roster = Roster.load(ROSTER, owner=rel_gold["page_owner"])
                records = fn(ps, roster, llm, rel_gold["page_owner"])
            else:
                fn = _oracle_traits(trait_gold) if args.oracle else METHODS[m]
                for name, ch in trait_gold["characters"].items():
                    ps = _select(trait_pages[name], set(ch["paragraphs"]), args.limit)
                    records += fn(ps, Roster.load(ROSTER, owner=name), llm, name)
            stats = {**vars(llm.stats), "wall_s": round(time.monotonic() - t0, 1), "paragraphs": len(records)}
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
            (out_dir / f"{m}.stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
        elif path.exists():
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            sp = out_dir / f"{m}.stats.json"
            stats = json.loads(sp.read_text()) if sp.exists() else {}
        else:
            continue

        if is_rel:
            roster = Roster.load(ROSTER, owner=rel_gold["page_owner"])
            texts = {p.id: (p.section, p.text) for p in rel_pages}
            s = score_relations(records, rel_gold, roster, texts)
            (out_dir / f"{m}.errors.txt").write_text("FP\n" + "\n".join(s["fp"]) + "\n\nFN\n" + "\n".join(s["fn"]),
                                                     encoding="utf-8")
            rows.append((m, f"{s['link_P']:.2f} / {s['link_P_strict']:.2f}", f"{s['link_R']:.2f}", f"{s['link_F1']:.2f}",
                         f"{s['affinity_acc']:.2f}", f"{s['hallucinated']:.1%}", f"{s['type_P']:.2f}",
                         f"{s['type_R']:.2f}", "", "", _speed(stats)))
        else:
            agg = {"tp": 0.0, "pred": 0, "gold": 0, "pole": 0.0, "bad": 0}
            notes = []
            for name, ch in trait_gold["characters"].items():
                ids = set(ch["paragraphs"])
                s = score_traits([r for r in records if r["id"] in ids], ch)
                tp = s["trait_P"] * s["predicted"]
                agg["tp"] += tp
                agg["pred"] += s["predicted"]
                agg["gold"] += len(ch["traits"])
                agg["pole"] += s["pole_acc"] * tp
                agg["bad"] += s["not_trait_hits"]
                notes.append(f"## {name}\nmissed: {s['missed']}\nunmatched (проверить руками — эталон может быть неполон): "
                             f"{s['unmatched']}\n")
            (out_dir / f"{m}.errors.txt").write_text("\n".join(notes), encoding="utf-8")
            p = agg["tp"] / agg["pred"] if agg["pred"] else 0.0
            r = agg["tp"] / agg["gold"] if agg["gold"] else 0.0
            f = 2 * p * r / (p + r) if p + r else 0.0
            rows.append((m, f"{p:.2f}", f"{r:.2f}", f"{f:.2f}", "", "", "", "",
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
