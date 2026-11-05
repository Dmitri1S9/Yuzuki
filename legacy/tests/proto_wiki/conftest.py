import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from proto_wiki.domain.schemas import CorefOutput, TripleLLM, TriplesOutput  # noqa: E402
from proto_wiki.infra.ollama_client import LLMError  # noqa: E402

CHARACTER = "Kyoka Jiro"

MAIN_WIKITEXT = """{{Character Infobox
|name = Kyoka Jiro
}}
{{Nihongo|'''Kyoka Jiro'''|耳郎響香|Jirō Kyōka}} is a student in [[Class 1-A]] at [[U.A. High School]]. She is a friend of [[Denki Kaminari|Kaminari]].

==Personality==
Kyoka enjoys [[music]] and plays guitar with her friends every weekend.{{Ref|chap=1}}

==Appearances==
===Anime===
This appearances subtree must never reach the text.

==Gallery==
This gallery section must never reach the text either.

==Trivia==
Her surname contains the kanji for the word ear.

==References==
<references/>
"""

REL_WIKITEXT = """==Family==
===[[Kyotoku Jiro|Kyotoku]] and [[Mika Jiro]]===
[[File:Parents.png|thumb|A younger Kyoka playing music with her parents]]
Kyoka has an excellent relationship with her parents who taught her music.
"""


def make_dump(path: Path) -> Path:
    def page(title, text):
        return (f"<page><title>{title}</title><ns>0</ns><id>1</id>"
                f"<revision><text xml:space=\"preserve\">{text}</text></revision></page>")

    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    xml = ('<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/"><siteinfo/>'
           + page("Someone Else", "Unrelated page text that is long enough.")
           + page(CHARACTER, esc(MAIN_WIKITEXT))
           + page(f"{CHARACTER}/Relationships", esc(REL_WIKITEXT))
           + "</mediawiki>")
    path.write_text(xml, encoding="utf-8")
    return path


def make_params(path: Path) -> Path:
    path.write_text(json.dumps({
        "ordinals": {"intellect": {"definition": "How smart.", "tier_count": 3}},
        "profile": {"body_age": {"definition": "Age.", "values": ["child", "adult"]}},
        "personality": {
            "honest": {"definition": "Tells the truth.", "sort_axis": "liar -> honest"},
            "shy": {"definition": "Is shy.", "sort_axis": "bold -> shy"},
        },
        "weakness": {"has_weak_ear": {"definition": "Ear weakness.", "sort_axis": "none -> critical"}},
    }), encoding="utf-8")
    return path


class FakeLLM:
    """Stands in for OllamaClient. `answers` maps a parameter name to a
    (tier, evidence, reason) tuple or an exception to raise."""

    model = "fake-model"
    ctx = 32768

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = {"coref": 0, "triples": 0, "params": 0}

    def generate(self, system, user, response_model):
        if response_model is CorefOutput:
            self.calls["coref"] += 1
            return CorefOutput(text=user.split("Paragraph:\n", 1)[1].strip())
        if response_model is TriplesOutput:
            self.calls["triples"] += 1
            return TriplesOutput(triples=self._triples(user))
        self.calls["params"] += 1
        name = user.split("Trait: ", 1)[1].split("\n", 1)[0]
        answer = self.answers.get(name, ("unknown", "", "text is silent"))
        if isinstance(answer, Exception):
            raise answer
        tier, evidence, reason = answer
        return response_model(evidence=evidence, reason=reason, tier=tier)

    @staticmethod
    def _triples(user):
        sentences = [line for line in user.splitlines() if line.startswith("[")]
        out = []
        for i, line in enumerate(sentences, 1):
            if "friend of" in line:
                out.append(TripleLLM(sentence_id=i, subject="Jiro", subject_type="Character", relation="friend_of",
                                     object="Kaminari", object_type="Character", item_class="none"))
                out.append(TripleLLM(sentence_id=99, subject="Jiro", subject_type="Character", relation="friend_of",
                                     object="Nobody", object_type="Character", item_class="none"))
            if "enjoys music" in line:
                out.append(TripleLLM(sentence_id=i, subject="Kyoka", subject_type="Character", relation="enjoys",
                                     object="Music", object_type="Activity", item_class="none"))
        return out


@pytest.fixture
def env(tmp_path):
    return {
        "dump": make_dump(tmp_path / "wiki_pages_current.xml"),
        "params": make_params(tmp_path / "parameters.json"),
        "out": tmp_path / "out",
    }


@pytest.fixture
def fake_error():
    return LLMError
