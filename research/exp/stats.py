"""Статистика по прогонам: доверительные интервалы, нормальность, проверка гипотез «метод A лучше B».

    python -m research.exp.stats --model qwen3.5-9b-Q4_K_M --rel rel_free,rel_anchored --traits traits_anchored,traits_verify

Что считается:
  * bootstrap 95% CI (10 000 повторов, пересэмплинг абзацев) для P / строгой P / R / F1 каждого метода;
  * метрики по каждому персонажу (единица для парных тестов между методами, n = число персонажей);
  * Shapiro–Wilk на разностях по персонажам -> парный t-тест, если нормально (p > 0.05), иначе Wilcoxon;
  * McNemar (точный) по решениям на уровне пар (абзац, кандидат): «верно/неверно» у A и у B на одних и тех же парах —
    самый мощный тест здесь, т. к. решений сотни.
Выход: research/runs/<model>/stats.md
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats as st

from .run import ROOT, TRAIT_GOLD, rel_golds, roster_for
from .pages import load_pages
from .score import _content, load_gold

RNG = np.random.default_rng(0)
B = 10_000


def _load(out_dir: Path, m: str) -> dict[str, dict]:
    p = out_dir / f"{m}.jsonl"
    return {r["id"]: r for r in (json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x)}


# ------------------------------------------------------------------ relations
def rel_items(records: dict[str, dict], golds: list[dict]):
    """Строки на абзац: (character, tp, fp, opt, fn) и решения на парах {(para, name): correct?}."""
    rows, decisions = [], {}
    for g in golds:
        owner = g["page_owner"]
        roster = roster_for(owner, golds)
        texts = {p.id: p for p in load_pages(g["page_file"])}
        for gp in g["paragraphs"]:
            rec = records.get(gp["id"])
            if rec is None:
                continue
            links, optional = gp.get("links") or {}, set(gp.get("optional") or [])
            pred = {r.get("canonical") or f"?{r.get('name')}" for r in rec.get("relations", [])} - {owner}
            tp = len(pred & set(links))
            fp = len(pred - set(links) - optional)
            opt = len(pred & optional)
            fn = len(set(links) - pred)
            rows.append((owner, tp, fp, opt, fn))
            p = texts[gp["id"]]
            universe = set(roster.mentions(p.text)) | (set(roster.mentions(p.section)) if p.page.endswith(
                "/Relationships") else set())
            for name in (universe | set(links) | pred) - {owner} - optional:
                decisions[(gp["id"], name)] = (name in pred) == (name in links)
    return rows, decisions


def rel_metrics(rows) -> dict[str, float]:
    a = np.array([r[1:] for r in rows], dtype=float)
    tp, fp, opt, fn = a.sum(0) if len(a) else (0, 0, 0, 0)
    P = tp / (tp + fp) if tp + fp else 0.0
    Ps = tp / (tp + fp + opt) if tp + fp + opt else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    return {"P": P, "P_strict": Ps, "R": R, "F1": 2 * P * R / (P + R) if P + R else 0.0}


# ------------------------------------------------------------------ traits
def trait_items(records: dict[str, dict], gold: dict):
    """Строки на абзац: (character, tp, pred, gold_n) — gold считается по абзацу, где фрагмент встречается."""
    rows = []
    for name, ch in gold["characters"].items():
        pages = {p.id: p.text.lower() for p in load_pages(name.replace(" ", "_"))}
        gold_by_para: dict[str, list] = {pid: [] for pid in ch["paragraphs"]}
        for t in ch["traits"]:
            pid = next((i for i in ch["paragraphs"] if t["span"].lower() in pages.get(i, "")), ch["paragraphs"][0])
            gold_by_para[pid].append(t)
        for pid in ch["paragraphs"]:
            rec = records.get(pid)
            if rec is None:
                continue
            preds = [t for t in rec.get("traits", []) if t.get("status", "actual") == "actual"]
            gl, used, tp = gold_by_para[pid], set(), 0
            all_gold = ch["traits"]
            for t in preds:
                w = _content(str(t.get("span", "")))
                hit = next((i for i, g in enumerate(all_gold) if i not in used and w & _content(g["span"])), None)
                if hit is not None:
                    used.add(hit)
                    tp += 1
            rows.append((name, tp, len(preds), len(gl)))
    return rows


def trait_metrics(rows) -> dict[str, float]:
    a = np.array([r[1:] for r in rows], dtype=float)
    tp, pred, gold_n = a.sum(0) if len(a) else (0, 0, 0)
    P = tp / pred if pred else 0.0
    R = min(tp / gold_n, 1.0) if gold_n else 0.0
    return {"P": P, "R": R, "F1": 2 * P * R / (P + R) if P + R else 0.0}


# ------------------------------------------------------------------ generic
def bootstrap(rows, fn) -> dict[str, tuple[float, float]]:
    n = len(rows)
    samples = [fn([rows[i] for i in RNG.integers(0, n, n)]) for _ in range(B)]
    return {k: (float(np.percentile([s[k] for s in samples], 2.5)), float(np.percentile([s[k] for s in samples], 97.5)))
            for k in samples[0]}


def per_character(rows, fn) -> dict[str, dict]:
    chars = sorted({r[0] for r in rows})
    return {c: fn([r for r in rows if r[0] == c]) for c in chars}


def paired_test(a: list[float], b: list[float]) -> str:
    d = np.array(b) - np.array(a)
    if len(d) < 3 or np.allclose(d, d[0]):
        return f"n={len(d)}: разности одинаковы/мало данных — тест не применим"
    sw = st.shapiro(d)
    if sw.pvalue > 0.05:
        t = st.ttest_rel(b, a)
        return (f"Shapiro–Wilk W={sw.statistic:.3f}, p={sw.pvalue:.3f} → нормальность не отвергнута → "
                f"парный t-тест: t={t.statistic:.2f}, p={t.pvalue:.4f}; средняя разность {d.mean():+.3f}")
    w = st.wilcoxon(b, a)
    return (f"Shapiro–Wilk W={sw.statistic:.3f}, p={sw.pvalue:.3f} → не нормально → "
            f"Wilcoxon: W={w.statistic:.1f}, p={w.pvalue:.4f}; медиана разности {np.median(d):+.3f}")


def mcnemar(da: dict, db: dict) -> str:
    keys = da.keys() & db.keys()
    b01 = sum(1 for k in keys if not da[k] and db[k])   # A ошибся, B прав
    b10 = sum(1 for k in keys if da[k] and not db[k])   # A прав, B ошибся
    n = b01 + b10
    p = st.binomtest(min(b01, b10), n, 0.5).pvalue if n else 1.0
    acc_a = sum(da[k] for k in keys) / len(keys)
    acc_b = sum(db[k] for k in keys) / len(keys)
    return (f"{len(keys)} решений; доля верных A={acc_a:.3f}, B={acc_b:.3f}; только B прав: {b01}, только A прав: {b10}; "
            f"точный McNemar p={p:.4f}")


def fmt(m: dict, ci: dict) -> str:
    return ", ".join(f"{k} {v:.2f} [{ci[k][0]:.2f}–{ci[k][1]:.2f}]" for k, v in m.items())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5-9b-Q4_K_M")
    ap.add_argument("--rel", default="rel_free,rel_anchored")
    ap.add_argument("--traits", default="traits_anchored,traits_verify")
    args = ap.parse_args()
    out_dir = ROOT / "runs" / args.model
    golds, tgold = rel_golds(), load_gold(TRAIT_GOLD)
    lines = [f"# Статистика — {args.model}", "",
             "95% CI — bootstrap по абзацам (10 000 повторов). Тесты между методами — на одних и тех же абзацах.", ""]

    rel_methods = [m for m in args.rel.split(",") if (out_dir / f"{m}.jsonl").exists()]
    rel = {m: rel_items(_load(out_dir, m), golds) for m in rel_methods}
    lines += ["## Связи", ""]
    for m, (rows, _) in rel.items():
        chars = sorted({r[0] for r in rows})
        lines.append(f"- **{m}** ({len(rows)} абзацев, {len(chars)} персонажей): {fmt(rel_metrics(rows), bootstrap(rows, rel_metrics))}")
    lines += ["", "По персонажам (F1 / строгая P / R):", "", "| персонаж | " + " | ".join(rel_methods) + " |",
              "|---|" + "---|" * len(rel_methods)]
    pcs = {m: per_character(rows, rel_metrics) for m, (rows, _) in rel.items()}
    for c in sorted(set().union(*[p.keys() for p in pcs.values()]) if pcs else []):
        cells = [f"{pcs[m][c]['F1']:.2f} / {pcs[m][c]['P_strict']:.2f} / {pcs[m][c]['R']:.2f}" if c in pcs[m] else "—"
                 for m in rel_methods]
        lines.append(f"| {c} | " + " | ".join(cells) + " |")
    if len(rel_methods) >= 2:
        a, b = rel_methods[0], rel_methods[1]
        common = sorted(set(pcs[a]) & set(pcs[b]))
        lines += ["", f"**{b} против {a}:**", ""]
        for k in ("F1", "P_strict", "R"):
            lines.append(f"- {k} по персонажам (n={len(common)}): " + paired_test(
                [pcs[a][c][k] for c in common], [pcs[b][c][k] for c in common]))
        lines.append(f"- McNemar по парам (абзац, имя): " + mcnemar(rel[a][1], rel[b][1]))

    tr_methods = [m for m in args.traits.split(",") if (out_dir / f"{m}.jsonl").exists()]
    tr = {m: trait_items(_load(out_dir, m), tgold) for m in tr_methods}
    lines += ["", "## Черты", ""]
    for m, rows in tr.items():
        lines.append(f"- **{m}** ({len(rows)} абзацев, {len({r[0] for r in rows})} персонажей): "
                     f"{fmt(trait_metrics(rows), bootstrap(rows, trait_metrics))}")
    tpc = {m: per_character(rows, trait_metrics) for m, rows in tr.items()}
    lines += ["", "По персонажам (P / R / F1):", "", "| персонаж | " + " | ".join(tr_methods) + " |",
              "|---|" + "---|" * len(tr_methods)]
    for c in sorted(set().union(*[p.keys() for p in tpc.values()]) if tpc else []):
        lines.append(f"| {c} | " + " | ".join(
            f"{tpc[m][c]['P']:.2f} / {tpc[m][c]['R']:.2f} / {tpc[m][c]['F1']:.2f}" if c in tpc[m] else "—"
            for m in tr_methods) + " |")
    if len(tr_methods) >= 2:
        a, b = tr_methods[0], tr_methods[1]
        common = sorted(set(tpc[a]) & set(tpc[b]))
        lines += ["", f"**{b} против {a}:**", ""]
        for k in ("P", "R", "F1"):
            lines.append(f"- {k} по персонажам (n={len(common)}): " + paired_test(
                [tpc[a][c][k] for c in common], [tpc[b][c][k] for c in common]))
    text = "\n".join(lines) + "\n"
    (out_dir / "stats.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
