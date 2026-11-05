from pathlib import Path

import numpy as np
import pytest
from conftest import FakeEmbedder, FakeLLM

from yuzuki_local.entities.anchors import Anchor, AnchorSet
from yuzuki_local.entities.flag import FlagSet
from yuzuki_local.entities.ordinal import OrdinalSet
from yuzuki_local.entities.results import SubjectContext
from yuzuki_local.entities.settings import RelationSettings
from yuzuki_local.external.ollama import LLMError, PromptTooLong
from yuzuki_local.workers.anchor_matcher import AnchorMatcher
from yuzuki_local.workers.flag_asker import FlagAsker
from yuzuki_local.workers.group_typer import GroupType, GroupTyper
from yuzuki_local.workers.occupation_worker import OccupationQuestion, OccupationWorker
from yuzuki_local.workers.ordinal_rater import OrdinalRater
from yuzuki_local.workers.prompt_renderer import PromptRenderer
from yuzuki_local.workers.quote_verifier import QuoteVerifier
from yuzuki_local.workers.relation_classifier import RelationClassifier
from yuzuki_local.workers.relation_extractor import RelationExtractor

PKG = Path(__file__).resolve().parents[2] / "src" / "yuzuki_local"
GUITAR = "She plays the guitar every weekend"
PUNCH = "She punched Bakugo in the face during the battle trial"


@pytest.fixture
def ctx(context_text):
    return SubjectContext("Kyoka Jiro", context_text, "h", 1000, ())


@pytest.fixture
def verifier(context_text):
    return QuoteVerifier(context_text, 90, 15)


@pytest.fixture
def flag():
    return FlagSet.load(PKG / "flags" / "flags.yaml").flags[0]


def test_flag_yes_with_real_quote_stays_yes(ctx, verifier, flag):
    llm = FakeLLM(dict(flag=flag.id, answer="yes", quotes=[GUITAR]))
    a = FlagAsker(llm, PromptRenderer(), "MHA").ask(ctx, flag, verifier)
    assert (a.answer_raw, a.answer_final, a.quote_valid) == ("yes", "yes", True)
    assert llm.prompts[0].index(ctx.text) < llm.prompts[0].index("PROPERTY:")     # context first, flag last


def test_flag_yes_with_invented_quote_is_downgraded_to_no_data(ctx, verifier, flag):
    llm = FakeLLM(dict(flag=flag.id, answer="yes", quotes=["She secretly leads a gang of thieves in Tokyo"]))
    a = FlagAsker(llm, PromptRenderer(), "MHA").ask(ctx, flag, verifier)
    assert (a.answer_raw, a.answer_final, a.quote_valid) == ("yes", "no_data", False)


def test_flag_yes_without_quotes_is_no_data_invalid(ctx, verifier, flag):
    a = FlagAsker(FakeLLM(dict(flag=flag.id, answer="no", quotes=[])), PromptRenderer(), "MHA").ask(ctx, flag, verifier)
    assert (a.answer_final, a.quote_valid) == ("no_data", False)


def test_flag_no_data_keeps_valid_null(ctx, verifier, flag):
    a = FlagAsker(FakeLLM(dict(flag=flag.id, answer="no_data", quotes=[])), PromptRenderer(), "MHA").ask(ctx, flag, verifier)
    assert (a.answer_final, a.quote_valid) == ("no_data", None)


def test_flag_llm_error_is_recorded_not_raised_but_prompt_too_long_is(ctx, verifier, flag):
    asker = FlagAsker(FakeLLM(LLMError("boom", raw="{")), PromptRenderer(), "MHA")
    a = asker.ask(ctx, flag, verifier)
    assert a.status == "error" and a.answer_final is None
    with pytest.raises(PromptTooLong):
        FlagAsker(FakeLLM(PromptTooLong("x")), PromptRenderer(), "MHA").ask(ctx, flag, verifier)


def test_ordinal_tier_zero_and_bad_tier_and_invalid_quote(ctx, verifier):
    scale = OrdinalSet.load(PKG / "ordinals" / "ordinals.yaml").scales[0]
    rater = lambda reply: OrdinalRater(FakeLLM(reply), PromptRenderer(), "MHA").ask(ctx, scale, verifier)
    ok = rater(dict(ordinal=scale.id, tier=3, quotes=[PUNCH]))
    assert ok.tier_final == 3 and ok.quote_valid
    zero = rater(dict(ordinal=scale.id, tier=0, quotes=[]))
    assert zero.tier_final is None and zero.quote_valid is None and zero.status == "ok"
    fake = rater(dict(ordinal=scale.id, tier=5, quotes=["She can lift an entire skyscraper with one hand"]))
    assert (fake.tier_raw, fake.tier_final, fake.quote_valid) == (5, None, False)
    assert rater(dict(ordinal=scale.id, tier=scale.max_tier + 1, quotes=[PUNCH])).status == "error"


def _matcher(embedder=None):
    anchors = AnchorSet("t", tuple(Anchor(i, i, (i * 3,) * 5) for i in ("fight", "love", "teach")))
    return AnchorMatcher(embedder or FakeEmbedder(), anchors)


def test_anchor_matcher_top_and_ambiguity():
    m = _matcher()
    sims = m.similarities(m.embed(["fight fight fight", "love and teach"]))
    assert m.top(sims[0], 1)[0].anchor_id == "fight"
    assert m.is_ambiguous(sims[1], margin=0.1) and not m.is_ambiguous(sims[0], margin=0.1)
    assert set(m.sims_dict(sims[0])) == {"fight", "love", "teach"}


def test_occupation_embeds_only_a_verified_answer(ctx, verifier):
    q = OccupationQuestion("current", "What now?")
    worker = lambda reply: OccupationWorker(FakeLLM(reply), PromptRenderer(), _matcher(), "MHA", 2)
    good = worker(dict(answer="fight teacher", quotes=[GUITAR])).ask(ctx, q, verifier)
    assert good.answer_text == "fight teacher" and len(good.top_anchors) == 2 and good.embedding
    bad = worker(dict(answer="astronaut", quotes=["She flies the space shuttle to the moon every week"])).ask(ctx, q, verifier)
    assert bad.answer_text is None and bad.embedding is None and bad.quote_valid is False
    nd = worker(dict(answer="no_data", quotes=[])).ask(ctx, q, verifier)
    assert nd.answer_text is None and nd.quote_valid is None


def test_group_type_is_a_closed_choice(ctx, verifier):
    types = (GroupType("education", "school"), GroupType("criminal", "gang"))
    typer = GroupTyper(FakeLLM(dict(group_type="education", quotes=[GUITAR])), PromptRenderer(), "MHA", types)
    assert typer.ask(ctx, verifier).group_type == "education"
    schema = typer._schema.model_json_schema()
    assert set(schema["properties"]["group_type"]["enum"]) == {"education", "criminal", "no_data"}
    llm = FakeLLM(dict(group_type="education", quotes=["nothing like this in the context at all"]))
    a = GroupTyper(llm, PromptRenderer(), "MHA", types).ask(ctx, verifier)
    assert a.type_raw == "education" and a.group_type is None


SETTINGS = RelationSettings(max_partners=3, min_quotes=3, max_quotes=2, num_predict=100, histogram_temperature=0.1)


def test_partners_drop_self_duplicates_and_cap(ctx):
    llm = FakeLLM(dict(partners=["Kyoka Jiro", "Momo", "momo", "Bakugo", "Kaminari", "Iida"]))
    names = RelationExtractor(llm, PromptRenderer(), "MHA", SETTINGS).partners(ctx)
    assert names == ["Momo", "Bakugo", "Kaminari"]


def test_edge_events_are_directed_capped_validated_and_victories_separate(ctx, verifier):
    reply = dict(
        interactions=[
            dict(actor="Kyoka Jiro", target="Bakugo", quote=PUNCH),
            dict(actor="kyoka jiro", target="Bakugo", quote=PUNCH),                        # duplicate
            dict(actor="Bakugo", target="Kyoka Jiro", quote="He invented this sentence that is not in the text"),
            dict(actor="Kyoka Jiro", target="Deku", quote=GUITAR),                          # stranger: dropped
            dict(actor="Kyoka Jiro", target="Bakugo", quote=GUITAR),
            dict(actor="Kyoka Jiro", target="Bakugo", quote="She is a student in Class 1-A"),   # over the cap of 2
        ],
        victories=[dict(winner="Kyoka Jiro", loser="Bakugo", quote=PUNCH)])
    edge = RelationExtractor(FakeLLM(reply), PromptRenderer(), "MHA", SETTINGS).edge(ctx, "Bakugo", verifier)
    kinds = [(e.kind, e.source, e.target, e.quote_valid) for e in edge.events]
    assert kinds == [("interaction", "Kyoka Jiro", "Bakugo", True),
                     ("interaction", "Bakugo", "Kyoka Jiro", False),
                     ("interaction", "Kyoka Jiro", "Bakugo", True),
                     ("victory", "Kyoka Jiro", "Bakugo", True)]
    assert edge.dropped == 3


def test_classifier_uses_only_verified_interactions_and_counts_wins():
    events = [
        dict(id=1, source="A", target="B", kind="interaction", quote="fight fight", quote_valid=True),
        dict(id=2, source="A", target="B", kind="interaction", quote="love love", quote_valid=True),
        dict(id=3, source="A", target="B", kind="interaction", quote="teach teach", quote_valid=False),
        dict(id=4, source="A", target="B", kind="victory", quote="fight won", quote_valid=True),
    ]
    classified, edges = RelationClassifier(_matcher()).classify(events, temperature=0.1)
    assert [c.top_type for c in classified] == ["fight", "love"]
    (edge,) = edges
    assert (edge.n_events, edge.wins) == (2, 1)
    # soft histogram: near-1.0 probability mass on the matching anchor for each of the 2 events, not a
    # hard count -- the two clearly-separated fake embeddings still saturate softmax at this temperature
    assert edge.histogram["fight"] == pytest.approx(1.0, abs=0.01)
    assert edge.histogram["love"] == pytest.approx(1.0, abs=0.01)
    assert edge.histogram.get("teach", 0.0) < 0.01
