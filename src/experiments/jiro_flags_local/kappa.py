"""Cohen's kappa between passes (3 passes -> 3 pairs) per character + pooled, and agreement with
your labels if labels.csv exists (columns: character,flag,label with yes/no/no_data)."""
import csv
import json
import re
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHARS = ["Kyoka Jiro", "All For One", "Minoru Mineta", "Tomura Shigaraki", "Izuku Midoriya"]
CATS = ["yes", "no", "no_data"]
# labels you already gave in chat (prefilled into the template)
PREFILL = {("Kyoka Jiro", "charismatic"): "yes"}


def slug(c): return re.sub(r"\W+", "_", c)


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in CATS)
    return None if pe == 1 else (po - pe) / (1 - pe)


def load(c, p):
    f = HERE / "results" / f"{slug(c)}_p{p}.json"
    return {r["flag"]: r["answer"] for r in json.loads(f.read_text())} if f.exists() else None


def main():
    pooled = {1: [], 2: [], 3: []}
    print(f"{'character':<20}{'k(1,2)':>8}{'k(1,3)':>8}{'k(2,3)':>8}{'mean':>8}{'all3 same':>11}{'yes/no/nd (pass1)':>22}")
    for c in CHARS:
        ps = {p: load(c, p) for p in (1, 2, 3)}
        if not all(ps.values()):
            print(f"{c:<20} (incomplete)"); continue
        flags = sorted(ps[1])
        ks = []
        for i, j in combinations((1, 2, 3), 2):
            ks.append(kappa([ps[i][f] for f in flags], [ps[j][f] for f in flags]))
        same = sum(ps[1][f] == ps[2][f] == ps[3][f] for f in flags)
        cnt = "/".join(str(sum(ps[1][f] == k for f in flags)) for k in CATS)
        ks_ok = [k for k in ks if k is not None]
        print(f"{c:<20}" + "".join(f"{k:>8.3f}" if k is not None else f"{'n/a':>8}" for k in ks)
              + f"{sum(ks_ok)/len(ks_ok):>8.3f}{same:>8}/{len(flags)}{cnt:>17}")
        for p in (1, 2, 3):
            pooled[p] += [ps[p][f] for f in flags]
    if pooled[1]:
        ks = [kappa(pooled[i], pooled[j]) for i, j in combinations((1, 2, 3), 2)]
        print(f"\nPOOLED over characters: k(1,2)={ks[0]:.3f} k(1,3)={ks[1]:.3f} k(2,3)={ks[2]:.3f} mean={sum(ks)/3:.3f}")

    labels = HERE / "labels.csv"
    if labels.exists():
        agree, tot, mine, theirs = 0, 0, [], []
        for row in csv.DictReader(labels.open(encoding="utf-8")):
            ps = load(row["character"], 1)
            if not ps or row["flag"] not in ps or not row["label"].strip():
                continue
            mine.append(row["label"].strip()); theirs.append(ps[row["flag"]])
        if mine:
            k = kappa(mine, theirs)
            print(f"\nvs your labels (pass 1): n={len(mine)}, raw agreement={sum(a==b for a,b in zip(mine,theirs))/len(mine):.1%}, kappa={k:.3f}")
    else:
        rows = []
        for c in CHARS:
            ps = load(c, 1)
            if ps:
                rows += [(c, f, PREFILL.get((c, f), "")) for f in sorted(ps)]
        with (HERE / "labels_template.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh); w.writerow(["character", "flag", "label"]); w.writerows(rows)
        print("\nNo labels.csv yet -> wrote labels_template.csv (fill `label` with yes/no/no_data, save as labels.csv, rerun).")


if __name__ == "__main__":
    main()
