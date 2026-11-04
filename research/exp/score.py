"""Метрики против эталона research/gold/*.yaml.

Отношения (уровень абзаца, только абзацы, размеченные в эталоне):
  link P/R/F1 — пары (абзац, X). TP: X в links. FP: X не в links и не в optional. optional не влияет.
  link_P_strict — то же, но optional (co-presence) считается ошибкой: отличает ли метод прямую связь от соседства.
  affinity acc — доля TP, где affinity модели в допустимом списке.
  hallucinated — доля выданных имён, которых НЕТ в абзаце (не разрешились ростером, или разрешились,
                 но в тексте абзаца/заголовке секции не упомянуты). Главная беда прошлых попыток.
Отношения (уровень страницы, targets): объединение типов по всем абзацам для X.
  type P = |pred ∩ (types ∪ also_ok)| / |pred|,  type R = |pred ∩ types| / |types|   (unspecified не считается).
Черты: совпадение фрагмента по общему содержательному слову; pole acc — полюс в {pole} ∪ also_ok;
  not_trait hits — выдано как actual то, что в эталоне помечено как "не черта".
"""
import re
from pathlib import Path

import yaml

from .roster import Roster
from .taxonomy import UNSPECIFIED

GOLD_DIR = Path(__file__).resolve().parent.parent / "gold"
_STOP = {"with", "that", "this", "from", "when", "they", "them", "their", "being", "very", "quite", "about",
         "towards", "toward", "into", "side", "personality", "others", "other", "himself", "herself"}


def _f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if p + r else 0.0


def _div(a: float, b: float) -> float:
    return a / b if b else 0.0


def score_relations(records: list[dict], gold: dict, roster: Roster, para_text: dict[str, tuple[str, str]]) -> dict:
    """para_text: id -> (section, text) — для проверки "имя есть в абзаце"."""
    gold_p = {g["id"]: g for g in gold["paragraphs"]}
    owner = gold["page_owner"]
    tp = fp = fn = aff_ok = opt = 0
    names_out = halluc = 0
    fp_list, fn_list = [], []
    page_types: dict[str, set[str]] = {}
    for rec in records:
        section, text = para_text.get(rec["id"], ("", ""))
        present = set(roster.mentions(text)) | (set(roster.mentions(section)) if "/Relationships|" in rec["id"] else set())
        predicted: dict[str, dict] = {}
        for r in rec.get("relations", []):
            names_out += 1
            c = r.get("canonical")
            if c is None or c not in present:
                halluc += 1
            if c and c != owner and c not in predicted:
                predicted[c] = r
            if c and r.get("type") and r["type"] != UNSPECIFIED:
                page_types.setdefault(c, set()).add(r["type"])
        g = gold_p.get(rec["id"])
        if g is None:
            continue
        links, optional = g.get("links") or {}, set(g.get("optional") or [])
        for c, r in predicted.items():
            if c in links:
                tp += 1
                aff_ok += r.get("affinity") in links[c]["affinity"]
            elif c in optional:
                opt += 1
            else:
                fp += 1
                fp_list.append(f"{rec['id']} -> {c}")
        for c in links:
            if c not in predicted:
                fn += 1
                fn_list.append(f"{rec['id']} -> {c}")
    tP = tR_hit = tR_all = tP_all = 0
    for name, t in (gold.get("targets") or {}).items():
        pred = page_types.get(name, set())
        ok = set(t["types"]) | set(t.get("also_ok") or [])
        tP += len(pred & ok)
        tP_all += len(pred)
        tR_hit += len(pred & set(t["types"]))
        tR_all += len(t["types"])
    p, r = _div(tp, tp + fp), _div(tp, tp + fn)
    return {"counts": {"tp": tp, "fp": fp, "opt": opt, "fn": fn, "aff_ok": aff_ok, "halluc": halluc,
                       "names_out": names_out, "tP": tP, "tP_all": tP_all, "tR_hit": tR_hit, "tR_all": tR_all},
            "link_P": p, "link_P_strict": _div(tp, tp + fp + opt), "link_R": r, "link_F1": _f1(p, r), "affinity_acc": _div(aff_ok, tp),
            "hallucinated": _div(halluc, names_out), "names_out": names_out,
            "type_P": _div(tP, tP_all), "type_R": _div(tR_hit, tR_all),
            "fp": fp_list, "fn": fn_list}


def _content(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z'-]+", s.lower()) if len(w) > 3 and w not in _STOP}


def score_traits(records: list[dict], gold_char: dict, texts: dict[str, str] | None = None) -> dict:
    """texts: id -> текст абзаца; если дан, считается not_in_text — фрагменты (любого статуса), которых нет в абзаце."""
    wanted = set(gold_char["paragraphs"])
    not_in_text = [t.get("span") for rec in records if rec["id"] in wanted and texts for t in rec.get("traits", [])
                   if str(t.get("span", "")).lower() not in texts.get(rec["id"], "").lower()]
    preds = [t for rec in records if rec["id"] in wanted for t in rec.get("traits", [])
             if t.get("status", "actual") == "actual"]
    gold = list(gold_char["traits"])
    used = [False] * len(gold)
    tp = pole_ok = 0
    unmatched = []
    for t in preds:
        words = _content(str(t.get("span", "")))
        hit = next((i for i, g in enumerate(gold) if not used[i] and words & _content(g["span"])), None)
        if hit is None:
            unmatched.append(t.get("span"))
            continue
        used[hit] = True
        tp += 1
        pole_ok += t.get("pole") in {gold[hit]["pole"], *(gold[hit].get("also_ok") or [])}
    bad = sum(any(nt.lower() in str(t.get("span", "")).lower() for nt in gold_char.get("not_traits") or [])
              for t in preds)
    p, r = _div(tp, len(preds)), _div(tp, len(gold))
    return {"counts": {"tp": tp, "pred": len(preds), "gold": len(gold), "pole_ok": pole_ok, "bad": bad,
                       "not_in_text": len(not_in_text)},
            "trait_P": p, "trait_R": r, "trait_F1": _f1(p, r), "pole_acc": _div(pole_ok, tp),
            "not_trait_hits": bad, "predicted": len(preds), "not_in_text": not_in_text,
            "missed": [g["span"] for i, g in enumerate(gold) if not used[i]], "unmatched": unmatched}


def load_gold(name: str) -> dict:
    return yaml.safe_load((GOLD_DIR / name).read_text(encoding="utf-8"))
