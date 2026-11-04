import random

from research.exp import methods
from research.exp.llm import FakeLLM
from research.exp.pages import Paragraph, load_pages, page_owner, parse_pages
from research.exp.ratings import components, fit
from research.exp.roster import Entity, Roster
from research.exp.run import ROSTERS, rel_golds
from research.exp.score import load_gold, score_relations, score_traits

OWNER = "Kyoka Jiro"


def roster() -> Roster:
    return Roster.load(ROSTERS / "my_hero_academia.yaml", owner=OWNER)


def test_parse_pages_ids():
    ps = parse_pages("=== PAGE: A/Relationships ===\n== B C ==\nfirst\nsecond\n== D ==\nthird\n")
    assert [p.id for p in ps] == ["A/Relationships|B C|0", "A/Relationships|B C|1", "A/Relationships|D|0"]
    assert page_owner(ps) == "A"


def test_gold_ids_exist_in_pages():
    for gold in rel_golds():
        ids = {p.id for p in load_pages(gold["page_file"])}
        assert [g["id"] for g in gold["paragraphs"] if g["id"] not in ids] == []
        assert set(gold["targets"]) <= {n for g in gold["paragraphs"] for n in g["links"]}, gold["page_owner"]
    traits = load_gold("traits.yaml")
    for name, ch in traits["characters"].items():
        tids = {p.id for p in load_pages(name.replace(" ", "_"))}
        assert set(ch["paragraphs"]) <= tids, name


def test_gold_names_are_detectable_by_roster():
    """Каждое имя эталона находится кодом в своём абзаце -> у anchored-методов нет потолка recall."""
    for gold in rel_golds():
        owner = gold["page_owner"]
        r = Roster.load(ROSTERS / f"{gold['roster']}.yaml", owner=owner)
        ps = {p.id: p for p in load_pages(gold["page_file"])}
        for g in gold["paragraphs"]:
            cands = set(methods.candidates(ps[g["id"]], r, owner))
            assert set(g["links"]) <= cands, g["id"]
            assert set(g.get("optional") or []) <= cands | {owner}, g["id"]


def test_roster_aliases_and_owner_tokens():
    r = roster()
    assert r.mentions("Kyoka and Jiro met Denki and Present Mic.") == [OWNER, "Denki Kaminari", "Hizashi Yamada"]
    assert r.mentions("Kyotoku and Mika Jiro") == ["Kyotoku Jiro", "Mika Jiro"]
    assert r.mentions("Denki's room") == ["Denki Kaminari"]
    assert r.resolve("Momo") == "Momo Yaoyorozu" and r.resolve("Batman") is None
    assert r.mark("Denki and Kyoka Jiro") == "[Denki](Denki Kaminari) and [Kyoka Jiro]"


def test_ambiguous_token_dropped_without_owner():
    r = Roster([Entity("Ann Lee", "character"), Entity("Bob Lee", "character")], owner=None)
    assert r.mentions("Lee said hi to Ann") == ["Ann Lee"]


def test_anchored_schema_closes_names():
    """Схема M1: ключи = ровно кандидаты из кода; посторонний ключ ответа игнорируется."""
    seen = {}

    def responder(system, user, schema):
        seen["schema"] = schema
        return {"Denki Kaminari": {"evidence": "x", "linked": True, "type": "friend", "affinity": "positive"},
                "Batman": {"evidence": "x", "linked": True, "type": "enemy", "affinity": "negative"}}

    p = Paragraph("Kyoka Jiro/Relationships", "Denki Kaminari", 0, "The two are friends with Momo.")
    rec = methods.rel_anchored([p], roster(), FakeLLM(responder), OWNER)[0]
    assert rec["candidates"] == ["Denki Kaminari", "Momo Yaoyorozu"]
    assert set(seen["schema"]["properties"]) == {"Denki Kaminari", "Momo Yaoyorozu"}
    assert seen["schema"]["additionalProperties"] is False
    assert [r["canonical"] for r in rec["relations"]] == ["Denki Kaminari"]


def test_anchored_skips_llm_when_no_candidates():
    llm = FakeLLM(lambda *a: {})
    methods.rel_anchored([Paragraph("Kyoka Jiro", "Appearance", 0, "She is petite.")], roster(), llm, OWNER)
    assert llm.stats.calls == 0


def test_free_method_hallucination_is_measured():
    p = Paragraph("Kyoka Jiro/Relationships", "Denki Kaminari", 0, "The two are friends.")
    llm = FakeLLM(lambda *a: {"relations": [{"name": "Denki", "relation": "friend"},
                                            {"name": "Shoto Todoroki", "relation": "classmate"}]})
    recs = methods.rel_free([p], roster(), llm, OWNER)
    gold = {"page_owner": OWNER, "targets": {}, "paragraphs": [
        {"id": p.id, "links": {"Denki Kaminari": {"affinity": ["positive"]}}}]}
    s = score_relations(recs, gold, roster(), {p.id: (p.section, p.text)})
    assert s["hallucinated"] == 0.5  # Shoto не упомянут в абзаце
    assert s["link_R"] == 1.0 and s["link_P"] == 0.5


def test_verify_drops_unsupported_links():
    def responder(system, user, schema):
        if "answer" in schema["properties"]:
            return {"answer": "no"}
        return {k: {"evidence": "", "linked": True, "type": "friend", "affinity": "positive"}
                for k in schema["properties"]}

    p = Paragraph("Kyoka Jiro/Relationships", "Denki Kaminari", 0, "The two are friends.")
    rec = methods.rel_verify([p], roster(), FakeLLM(responder), OWNER)[0]
    assert rec["relations"] == []


def test_traits_status_filters_apparent():
    gold = {"paragraphs": ["x|Personality|0"], "traits": [{"span": "organized", "pole": "C+"}], "not_traits": ["cold"]}
    recs = [{"id": "x|Personality|0", "traits": [
        {"span": "organized", "pole": "C+", "status": "actual"},
        {"span": "cold", "pole": "A-", "status": "apparent"}]}]
    s = score_traits(recs, gold)
    assert s["trait_P"] == 1.0 and s["not_trait_hits"] == 0


def test_lexicon_baseline_runs():
    p = Paragraph("Kyoka Jiro", "Personality", 0, "She is organized but comes off as cold.")
    rec = methods.traits_lexicon([p], roster(), None, OWNER)[0]
    assert {(t["span"], t["pole"]) for t in rec["traits"]} == {("organized", "C+"), ("cold", "A-")}


def test_bradley_terry_recovers_order_and_ties():
    rng = random.Random(0)
    true = {"A": 2.0, "B": 1.0, "C": 0.0, "D": -1.0}
    games = []
    names = list(true)
    for _ in range(400):
        a, b = rng.sample(names, 2)
        pa = 1 / (1 + 2.718 ** (true[b] - true[a]))
        games.append((a, b, False) if rng.random() < pa else (b, a, False))
    games += [("A", "B", True)] * 5
    theta, nu = fit(games)
    assert sorted(theta, key=theta.get, reverse=True) == ["A", "B", "C", "D"]
    assert nu > 0


def test_components_split_universes():
    games = [("A", "B", False), ("C", "D", False)]
    assert sorted(map(sorted, components({"A", "B", "C", "D"}, games))) == [["A", "B"], ["C", "D"]]


def test_traits_anchored_span_enum_and_dedupe():
    seen = {}

    def responder(system, user, schema):
        seen["enum"] = schema["properties"]["traits"]["items"]["properties"]["span"]["enum"]
        t = {"span": "blunt", "pole": "A-", "status": "actual"}
        return {"traits": [t, t]}

    p = Paragraph("Kyoka Jiro", "Personality", 0, "She is blunt and very organized.")
    rec = methods.traits_anchored([p], roster(), FakeLLM(responder), OWNER)[0]
    assert "blunt" in seen["enum"] and "organized" in seen["enum"] and "very" not in seen["enum"]
    assert rec["traits"] == [{"span": "blunt", "pole": "A-", "status": "actual"}]


def test_stats_tests_and_bootstrap():
    from research.exp import stats

    assert "t-тест" in stats.paired_test([0.5, 0.6, 0.55, 0.7, 0.62], [0.7, 0.81, 0.74, 0.9, 0.83]) or \
        "Wilcoxon" in stats.paired_test([0.5, 0.6, 0.55, 0.7, 0.62], [0.7, 0.81, 0.74, 0.9, 0.83])
    da = {i: i % 2 == 0 for i in range(40)}
    db = {i: True for i in range(40)}
    assert "только B прав: 20, только A прав: 0" in stats.mcnemar(da, db)
    rows = [("x", 1, 0, 0, 0), ("x", 0, 1, 0, 1)] * 10
    ci = stats.bootstrap(rows, stats.rel_metrics)
    assert 0.0 <= ci["P"][0] <= 0.5 <= ci["P"][1] <= 1.0
