import sys

import yaml

from research.exp.pages import parse_pages
from research.samples import build_roster, extract_pages
from src.wiki.dump_reader import DumpReader
from src.wiki.wikitext_cleaner import WikiTextCleaner

PAGES = {
    "Kyoka Jiro": "{{Infobox|name=Kyoka}}\nKyoka is a student of [[Class 1-A]].\n== Personality ==\n"
                  "She teases [[Denki Kaminari|Denki]] a lot in class.<ref>ch. 3</ref>\n"
                  "== Trivia ==\nShe likes rock music very much.\n[[Category:Characters]]",
    "Kyoka Jiro/Relationships": "== Denki Kaminari ==\nThe two are good friends and talk often.",
    "Denki Kaminari": "Denki is a student of class A here.\n[[Category:Characters]]",
    "Class 1-A": "A class of hero students at school.\n[[Category:Organizations]]",
    "Chargebolt": "#REDIRECT [[Denki Kaminari]]",
}


def _dump(tmp_path):
    body = "".join(f"<page><title>{t}</title><ns>0</ns><revision><text>{x.replace('&', '&amp;').replace('<', '&lt;')}"
                   f"</text></revision></page>" for t, x in PAGES.items())
    p = tmp_path / "dump.xml"
    p.write_text(f'<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">{body}</mediawiki>', encoding="utf-8")
    return p


def test_dump_reader_and_cleaner(tmp_path):
    pages = {p.title: p.text for p in DumpReader(_dump(tmp_path)).pages()}
    assert set(pages) == set(PAGES)
    secs = WikiTextCleaner().sections(pages["Kyoka Jiro"])
    assert [s.name for s in secs] == ["Introduction", "Personality", "Trivia"]
    assert secs[1].paragraphs == ("She teases Denki a lot in class.",)


def test_extract_pages_roundtrip(tmp_path, monkeypatch):
    dump, out = _dump(tmp_path), tmp_path / "pages"
    monkeypatch.setattr(sys, "argv", ["x", "--dump", str(dump), "--pages", "Kyoka Jiro", "--out", str(out)])
    extract_pages.main()
    ps = parse_pages((out / "Kyoka_Jiro.txt").read_text())
    assert [p.id for p in ps] == ["Kyoka Jiro|Introduction|0", "Kyoka Jiro|Personality|0",
                                  "Kyoka Jiro/Relationships|Denki Kaminari|0"]  # Trivia dropped
    assert extract_pages.link_pairs(PAGES["Kyoka Jiro"])["Denki"] == "Denki Kaminari"


def test_build_roster(tmp_path, monkeypatch):
    out = tmp_path / "r.yaml"
    monkeypatch.setattr(sys, "argv", ["x", "--dump", str(_dump(tmp_path)), "--out", str(out)])
    build_roster.main()
    data = yaml.safe_load(out.read_text())
    chars = {c["name"]: c["aliases"] for c in data["characters"]}
    assert chars == {"Denki Kaminari": ["Chargebolt", "Denki"], "Kyoka Jiro": []}
    assert [g["name"] for g in data["groups"]] == ["Class 1-A"]
