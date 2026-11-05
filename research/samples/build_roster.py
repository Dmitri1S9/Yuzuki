"""Ростер вселенной из дампа кодом (а не моделью): персонажи = статьи в категории, алиасы = редиректы
+ подписи вики-ссылок ([[Denki Kaminari|Denki]]). Выход — YAML в формате samples/rosters/*.yaml.

    python -m research.samples.build_roster --dump ~/Загрузки/bokunoheroacademia_pages_current.xml \
        --char-category Characters --group-category Organizations --out research/samples/rosters/mha_auto.yaml

Категории на разных вики называются по-разному — посмотрите на странице любого персонажа внизу.
Алиас, ведущий к двум разным персонажам, отбрасывается (неоднозначен).
"""
import argparse
import re
from collections import defaultdict
from pathlib import Path

import yaml

from src.wiki.dump_reader import DumpReader

_REDIRECT = re.compile(r"^#REDIRECT\s*\[\[([^\]|#]+)", re.I)
_CAT = re.compile(r"\[\[Category:([^\]|]+)", re.I)
_LINK = re.compile(r"\[\[([^\]|#:]+)(?:#[^\]|]*)?\|([^\]]+)\]\]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True, type=Path)
    ap.add_argument("--char-category", default="Characters")
    ap.add_argument("--group-category", default="Organizations")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    chars, groups = set(), set()
    redirects: dict[str, str] = {}
    surfaces: dict[str, set[str]] = defaultdict(set)
    for pg in DumpReader(args.dump).pages():
        if pg.ns != 0:
            continue
        m = _REDIRECT.match(pg.text.strip())
        if m:
            redirects[pg.title] = m.group(1).strip()
            continue
        if "/" not in pg.title:
            cats = [c.strip() for c in _CAT.findall(pg.text)]
            if any(args.char_category.lower() in c.lower() for c in cats):
                chars.add(pg.title)
            elif any(args.group_category.lower() in c.lower() for c in cats):
                groups.add(pg.title)
        for target, surface in _LINK.findall(pg.text):
            surfaces[surface.strip()].add(target.strip())
    aliases: dict[str, set[str]] = defaultdict(set)
    owners: dict[str, set[str]] = defaultdict(set)
    for src, dst in redirects.items():
        owners[src].add(dst)
    for surface, targets in surfaces.items():
        owners[surface] |= {redirects.get(t, t) for t in targets}
    for alias, targets in owners.items():
        targets = {t for t in targets if t in chars or t in groups}
        if len(targets) == 1 and (t := next(iter(targets))) != alias and len(alias) > 2:
            aliases[t].add(alias)
    data = {"characters": [{"name": c, "aliases": sorted(aliases[c])} for c in sorted(chars)],
            "groups": [{"name": g, "aliases": sorted(aliases[g])} for g in sorted(groups)]}
    args.out.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"{len(chars)} characters, {len(groups)} groups -> {args.out}")


if __name__ == "__main__":
    main()
