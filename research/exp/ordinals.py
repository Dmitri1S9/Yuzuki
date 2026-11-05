"""Тиры из текста: comparisons() по страницам -> Bradley–Terry–Davidson -> рейтинг по компонентам.

    python -m research.exp.ordinals --pages All_For_One,Izuku_Midoriya,Tomura_Shigaraki --model qwen3.5:9b

Эталона нет (сравнения не размечены) — вывод для ручной проверки: исход + цитата + итоговый рейтинг.
"""
import argparse
import json
import re
from pathlib import Path

from .llm import OllamaLLM
from .methods import comparisons
from .pages import load_pages, page_owner
from .ratings import components, fit, tiers
from .roster import Roster

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="All_For_One,Izuku_Midoriya,Tomura_Shigaraki")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--sections", default="Synopsis", help="подстрока в имени страницы (Synopsis = сюжет)")
    args = ap.parse_args()
    llm = OllamaLLM(args.model)
    games, evidence = [], []
    for name in args.pages.split(","):
        ps = load_pages(name)
        owner = page_owner(ps)
        roster = Roster.load(ROOT / "samples" / "rosters" / "my_hero_academia.yaml", owner=owner)
        for rec in comparisons([p for p in ps if args.sections in p.page], roster, llm, owner):
            for r in rec["comparisons"]:
                games.append((r["winner"], r["loser"], r["outcome"] == "draw"))
                evidence.append({"id": rec["id"], **r})
    out = ROOT / "runs" / re.sub(r"[^\w.-]+", "_", args.model) / "comparisons.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in evidence), encoding="utf-8")
    players = {p for g in games for p in g[:2]}
    for comp in components(players, games):
        sub = [g for g in games if g[0] in comp]
        theta, nu = fit(sub)
        t = tiers(theta)
        print(f"\n== component of {len(comp)} (games={len(sub)}, nu={nu:.2f})")
        for p in sorted(theta, key=theta.get, reverse=True):
            print(f"  tier {t[p]}  {theta[p]:+.2f}  {p}")
    print(f"\nevidence -> {out}  ({llm.stats.calls} calls, {llm.stats.seconds:.0f}s)")


if __name__ == "__main__":
    main()
