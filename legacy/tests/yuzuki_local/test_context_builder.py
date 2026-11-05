from pathlib import Path

import pytest

from yuzuki_local.entities.settings import ContextSettings
from yuzuki_local.external.dump_reader import DumpReader
from yuzuki_local.workers.context_builder import ContextBuilder, SubjectNotFound
from yuzuki_local.workers.wikitext_cleaner import WikiTextCleaner

MAIN = """{{Character Infobox
|name = Kyoka Jiro
|hair = Dark
}}
'''Kyoka Jiro''' is a student in [[Class 1-A]] who plays the guitar in her free time.

==Personality==
Kyoka is calm and sarcastic but loyal to her friends and classmates.

==Gallery==
<gallery>
Kyoka Portrait.png
</gallery>
{{Navbox Heroes}}
"""
RELATIONSHIPS = "==Momo Yaoyorozu==\nKyoka Jiro and Momo Yaoyorozu are close friends who often study together after school.\n"
SYNOPSIS = ("==Entrance Exam Arc==\nKyoka Jiro passed the entrance exam by destroying robots with her heartbeat jacks. "
            "She later met her future classmates. " * 4 + "\n\n==Sports Festival Arc==\nKyoka Jiro fought in the cavalry battle "
            "and lost in the first round to another student from the class. " * 4 + "\n")
OTHER = "Denki Kaminari asked Kyoka Jiro to play the guitar during the school festival because she was very good.\n"
BATTLE = "Kyoka Jiro fought a hard battle against a villain in the forest during the training camp.\n"


def _dump(tmp_path: Path) -> Path:
    pages = {"Kyoka Jiro": MAIN, "Kyoka Jiro/Relationships": RELATIONSHIPS, "Kyoka Jiro/Synopsis": SYNOPSIS,
             "School Festival": OTHER, "Kyoka Jiro vs. Villain": BATTLE, "Unrelated": "Nothing about her here at all, sorry.\n"}
    body = "".join(f"<page><title>{t}</title><ns>0</ns><revision><text>{x.replace('&', '&amp;').replace('<', '&lt;')}"
                   "</text></revision></page>" for t, x in pages.items())
    path = tmp_path / "dump.xml"
    path.write_text(f"<mediawiki>{body}</mediawiki>", encoding="utf-8")
    return path


def _builder(tmp_path, budget=62000):
    s = ContextSettings(char_budget=budget, shrink_step=0.12, max_calibrations=5, synopsis_share=0.7,
                        fragments_per_page=3, fragment_max_chars=900, min_paragraph_words=4, tail_headroom_tokens=900)
    return ContextBuilder(DumpReader(_dump(tmp_path)), WikiTextCleaner(4), s)


def test_context_has_page_relationships_synopsis_and_mentions_but_no_infobox_navbox_gallery(tmp_path):
    ctx = _builder(tmp_path).build("Kyoka Jiro")
    t = ctx.text
    for wanted in ("plays the guitar in her free time", "calm and sarcastic", "close friends who often study",
                   "heartbeat jacks", "cavalry battle", "school festival", "training camp"):
        assert wanted in t, wanted
    for unwanted in ("hair = Dark", "Navbox", "Portrait.png", "gallery", "Nothing about her"):
        assert unwanted not in t, unwanted


def test_context_fits_budget_and_records_coverage(tmp_path):
    small = _builder(tmp_path, budget=900).build("Kyoka Jiro")
    full = _builder(tmp_path).build("Kyoka Jiro")
    assert small.chars < full.chars
    cut = [s for s in small.sections if s.chars_kept < s.chars_total]
    assert cut and all(s.chars_kept > 0 for s in small.sections if s.origin == "synopsis")
    assert full.context_hash != small.context_hash


def test_same_input_same_hash_and_unknown_subject(tmp_path):
    b = _builder(tmp_path)
    assert b.build("Kyoka Jiro").context_hash == b.build("Kyoka Jiro").context_hash
    with pytest.raises(SubjectNotFound):
        b.build("Nobody Here")
