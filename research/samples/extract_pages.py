"""Вырезает страницы персонажей из дампа Fandom в формат research/samples/pages/*.txt.

    python -m research.samples.extract_pages --dump ~/Загрузки/bokunoheroacademia_pages_current.xml \
        --pages "Kyoka Jiro" "Izuku Midoriya" --subpages Relationships Synopsis

Для каждого персонажа пишет <Name>.txt (основная статья + подстраницы) и <Name>.links.json
(поверхность ссылки -> цель: [[Denki Kaminari|Denki]] даёт "Denki" -> "Denki Kaminari") — бесплатный
entity linking от авторов вики, источник алиасов для ростера.
"""
import argparse
import json
import re
from pathlib import Path

from src.wiki.dump_reader import DumpReader
from src.wiki.wikitext_cleaner import WikiTextCleaner

OUT = Path(__file__).resolve().parent / "pages"
DROP = {"trivia", "references", "gallery", "navigation", "site navigation", "external links", "image gallery",
        "quotes", "appearances", "voice actors"}
_LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")


def link_pairs(wikitext: str) -> dict[str, str]:
    pairs = {}
    for target, surface in _LINK.findall(wikitext):
        target = target.strip()
        if ":" in target:
            continue
        pairs[(surface or target).strip()] = target
    return pairs


def render(title: str, sections) -> str:
    lines = [f"=== PAGE: {title} ==="]
    for s in sections:
        if s.name.strip().lower() in DROP:
            continue
        lines.append(f"== {s.name} ==")
        lines.extend(s.paragraphs)
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", required=True, type=Path)
    ap.add_argument("--pages", nargs="+", required=True)
    ap.add_argument("--subpages", nargs="*", default=["Relationships", "Synopsis"])
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    wanted = {t for p in args.pages for t in [p, *(f"{p}/{s}" for s in args.subpages)]}
    texts = {pg.title: pg.text for pg in DumpReader(args.dump).pages() if pg.title in wanted}
    cleaner = WikiTextCleaner(min_paragraph_words=4)
    args.out.mkdir(parents=True, exist_ok=True)
    for p in args.pages:
        titles = [t for t in [p, *(f"{p}/{s}" for s in args.subpages)] if t in texts]
        if p not in texts:
            print(f"!! not in dump: {p}")
            continue
        body = "\n".join(render(t, cleaner.sections(texts[t])) for t in titles)
        links: dict[str, str] = {}
        for t in titles:
            links.update(link_pairs(texts[t]))
        stem = p.replace(" ", "_").replace("/", "_")
        (args.out / f"{stem}.txt").write_text(body, encoding="utf-8")
        (args.out / f"{stem}.links.json").write_text(json.dumps(links, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{stem}: {len(titles)} pages, {body.count(chr(10))} lines, {len(links)} links")


if __name__ == "__main__":
    main()
