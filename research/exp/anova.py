"""Модель «замер = реальное значение + шум»: нормальность шума, равенство дисперсий, one-way ANOVA, ICC, смещение.

Параметр — балл персонажа по оси Big Five / HEXACO-H из извлечённых черт (статус actual):
    score_X = (#черт X+  −  #черт X−) / #всех черт персонажа        ∈ [−1, 1]
Повторные замеры персонажа берутся из:
  * model  — повторные прогоны модели с температурой (runs/<model>-t0.7-s<seed>/<method>.jsonl);
  * text   — случайные выборки абзацев с возвращением (bootstrap) из одного прогона: шум «какие абзацы попались».
Для каждой оси:
  Shapiro–Wilk на остатках (замер − среднее персонажа)  → нормален ли шум (ЦПТ);
  Levene (медиана) и Bartlett                           → равны ли дисперсии шума у персонажей (допущение ANOVA);
  one-way ANOVA, фактор = персонаж                      → различает ли параметр персонажей сильнее шума;
  Alexander–Govern                                      → то же без допущения равных дисперсий (проверка устойчивости);
  Kruskal–Wallis                                        → то же без допущения нормальности;
  ICC(1)                                                → доля дисперсии, приходящаяся на «реальное» значение;
  смещение: среднее по персонажу − значение по эталону, t-тест (H0: смещение 0) и корреляция с эталоном.
NB: для --source text p-value ANOVA зависят от числа bootstrap-повторов (псевдорепликация) — смотреть на ICC и
смещение; честные p-value — у --source model (каждый повтор — независимый прогон модели).

    python -m research.exp.anova --model qwen3.5-9b-Q4_K_M --method traits_verify --source model
    python -m research.exp.anova --model qwen3.5-9b-Q4_K_M --method traits_verify --source text --reps 30
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy import stats as st

from .run import ROOT, TRAIT_GOLD
from .score import load_gold

AXES = ["E", "A", "C", "N", "O", "H"]


def score(traits: list[dict]) -> dict[str, float]:
    poles = [t["pole"] for t in traits if t.get("status", "actual") == "actual" and t.get("pole")]
    n = len(poles) or 1
    return {a: (poles.count(f"{a}+") - poles.count(f"{a}-")) / n for a in AXES}


def _records(path: Path) -> dict[str, dict]:
    return {r["id"]: r for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x)}


def measurements(model: str, method: str, source: str, reps: int, gold: dict) -> dict[str, list[dict]]:
    """character -> список замеров (dict ось -> балл)."""
    out: dict[str, list[dict]] = {c: [] for c in gold["characters"]}
    runs = ROOT / "runs"
    if source == "model":
        dirs = sorted(d for d in runs.glob(f"{model}-t*-s*") if (d / f"{method}.jsonl").exists())
        for d in dirs:
            recs = _records(d / f"{method}.jsonl")
            for c, ch in gold["characters"].items():
                if all(p in recs for p in ch["paragraphs"]):
                    out[c].append(score([t for p in ch["paragraphs"] for t in recs[p]["traits"]]))
    else:
        rng = np.random.default_rng(0)
        recs = _records(runs / model / f"{method}.jsonl")
        for c, ch in gold["characters"].items():
            ps = [p for p in ch["paragraphs"] if p in recs]
            for _ in range(reps):
                pick = rng.choice(len(ps), len(ps), replace=True)
                out[c].append(score([t for i in pick for t in recs[ps[i]]["traits"]]))
    return {c: v for c, v in out.items() if len(v) >= 2}


def icc1(groups: list[np.ndarray]) -> float:
    k = np.mean([len(g) for g in groups])
    grand = np.concatenate(groups).mean()
    n_tot, a = sum(len(g) for g in groups), len(groups)
    msb = sum(len(g) * (g.mean() - grand) ** 2 for g in groups) / (a - 1)
    msw = sum(((g - g.mean()) ** 2).sum() for g in groups) / (n_tot - a)
    return float((msb - msw) / (msb + (k - 1) * msw)) if msb + (k - 1) * msw else float("nan")


def analyse(meas: dict[str, list[dict]], gold: dict) -> list[str]:
    chars = sorted(meas)
    gold_scores = {c: score([{"pole": t["pole"]} for t in gold["characters"][c]["traits"]]) for c in chars}
    reps = sorted({len(v) for v in meas.values()})
    lines = [f"Персонажей: {len(chars)}, замеров на персонажа: {reps}", "",
             "| ось | Shapiro (шум) p | Levene p | Bartlett p | ANOVA F | ANOVA p | Alexander–Govern p | Kruskal–Wallis p | ICC(1) | "
             "смещение vs эталон | t-тест смещения p | r с эталоном |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for a in AXES:
        groups = [np.array([m[a] for m in meas[c]]) for c in chars]
        resid = np.concatenate([g - g.mean() for g in groups])
        const = np.allclose(resid, 0)
        sw = st.shapiro(resid).pvalue if len(resid) >= 3 and not const else float("nan")
        lev = st.levene(*groups, center="median").pvalue if not const else float("nan")
        bart = st.bartlett(*groups).pvalue if not const and all(g.std() > 0 for g in groups) else float("nan")
        an = st.f_oneway(*groups)
        try:
            ag = st.alexandergovern(*groups).pvalue
        except Exception:  # noqa: BLE001 — нулевая дисперсия в группе
            ag = float("nan")
        try:
            kw = st.kruskal(*groups).pvalue
        except ValueError:  # все значения одинаковы
            kw = float("nan")
        means = np.array([g.mean() for g in groups])
        gs = np.array([gold_scores[c][a] for c in chars])
        bias = means - gs
        tb = st.ttest_1samp(bias, 0.0).pvalue if bias.std() > 0 else float("nan")
        r = st.pearsonr(means, gs).statistic if means.std() > 0 and gs.std() > 0 else float("nan")
        lines.append(f"| {a} | {sw:.3f} | {lev:.3f} | {bart:.3f} | {an.statistic:.1f} | {an.pvalue:.2g} | {ag:.2g} | "
                     f"{kw:.2g} | {icc1(groups):.2f} | {bias.mean():+.2f} | {tb:.3f} | {r:.2f} |")
    lines += ["", "Средний балл по персонажу (замеры) / эталон:", "",
              "| персонаж | " + " | ".join(AXES) + " |", "|---|" + "---|" * len(AXES)]
    for c in chars:
        lines.append(f"| {c} | " + " | ".join(
            f"{np.mean([m[a] for m in meas[c]]):+.2f} / {gold_scores[c][a]:+.2f}" for a in AXES) + " |")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5-9b-Q4_K_M")
    ap.add_argument("--method", default="traits_verify")
    ap.add_argument("--source", choices=["model", "text"], default="model")
    ap.add_argument("--reps", type=int, default=30, help="для --source text: число bootstrap-выборок абзацев")
    args = ap.parse_args()
    gold = load_gold(TRAIT_GOLD)
    meas = measurements(args.model, args.method, args.source, args.reps, gold)
    head = [f"# ANOVA — {args.method}, шум: {'повторные прогоны модели (t=0.7)' if args.source == 'model' else 'выборки абзацев (bootstrap)'}", ""]
    text = "\n".join(head + analyse(meas, gold)) + "\n"
    out = ROOT / "runs" / args.model / f"anova_{args.method}_{args.source}.md"
    out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
