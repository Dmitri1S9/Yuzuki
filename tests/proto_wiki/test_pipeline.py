import json
import logging

from proto_wiki import cli
from proto_wiki.domain.schemas import ResolvedParagraph
from proto_wiki.infra.ollama_client import LLMError
from proto_wiki.services.params.step import evidence_found

from conftest import CHARACTER, FakeLLM

FILES = ["step1_coref.json", "step2_triples.json", "graph.json", "graph.html", "step3_params.json", "report.md"]
QUOTE = "Kyoka enjoys music and plays guitar"


def run(env, llm, *extra):
    return cli.main(["--input", str(env["dump"]), "--character", CHARACTER, "--params", str(env["params"]),
                     "--out", str(env["out"]), *extra], llm=llm)


def load(env, name):
    return json.loads((env["out"] / name).read_text(encoding="utf-8"))


def section(report, title_prefix):
    parts = report.split("\n## ")
    return next(p for p in parts if p.startswith(title_prefix))


def test_full_run_creates_all_files_and_logs_param_counts(env, caplog):
    caplog.set_level(logging.INFO, logger="proto_wiki")
    assert run(env, FakeLLM({"honest": ("T3", QUOTE, "r")})) == 0
    assert all((env["out"] / f).exists() for f in FILES)
    assert "флагов 3, ординалов 1" in caplog.text  # matches parameters.json

    step1 = load(env, "step1_coref.json")["paragraphs"]
    assert {"section", "original", "resolved", "coref_ok"} <= set(step1[0])
    step2 = load(env, "step2_triples.json")
    assert step2["dropped"] == {"sentence_id_out_of_range": 1}
    friend = next(t for t in step2["triples"] if t["relation"] == "friend_of")
    assert friend["evidence"].startswith("She is a friend of") and friend["section"] == "Introduction"
    graph = load(env, "graph.json")
    assert graph["center"] == CHARACTER
    assert {n["id"] for n in graph["nodes"]} >= {CHARACTER, "Denki Kaminari", "Music"}


def test_call_failure_lands_in_errors_not_unknown(env):
    llm = FakeLLM({"honest": ("T3", QUOTE, "r"), "shy": LLMError("после 3 ретраев: boom")})
    assert run(env, llm) == 0
    shy = next(r for r in load(env, "step3_params.json")["results"] if r["name"] == "shy")
    assert shy["status"] == "error" and shy["tier"] is None

    report = (env["out"] / "report.md").read_text(encoding="utf-8")
    assert "shy" in section(report, "ERRORS") and "boom" in section(report, "ERRORS")
    for title in ("Флаги: да", "Флаги: нет", "Флаги: не знает", "Ординалы"):
        assert "shy" not in section(report, title)


def test_quote_missing_from_text_gives_evidence_not_found(env):
    llm = FakeLLM({"honest": ("T3", "She never once lied to anybody in her life", "r"),
                   "intellect": ("T2", "invented sentence that is not in the article", "r")})
    run(env, llm)
    results = {r["name"]: r for r in load(env, "step3_params.json")["results"]}
    assert results["honest"]["status"] == "evidence_not_found"
    assert results["intellect"]["status"] == "evidence_not_found"
    report = (env["out"] / "report.md").read_text(encoding="utf-8")
    dont_know = section(report, "Флаги: не знает")
    assert "honest" in dont_know and "evidence_not_found" in dont_know
    assert "honest" not in section(report, "Флаги: да")


def test_report_lists(env):
    llm = FakeLLM({"honest": ("T3", QUOTE, "r"), "shy": ("T1", "Her surname contains the kanji", "r"),
                   "has_weak_ear": ("T2", "Kyoka has an excellent relationship", "r"),
                   "intellect": ("T3", "Her surname contains the kanji for the word ear", "r")})
    run(env, llm)
    report = (env["out"] / "report.md").read_text(encoding="utf-8")
    assert "honest" in section(report, "Флаги: да") and "«" in section(report, "Флаги: да")
    assert "shy" in section(report, "Флаги: нет")
    assert "has_weak_ear" in section(report, "Флаги: не знает") and "T2" in section(report, "Флаги: не знает")
    assert "intellect" in section(report, "Ординалы") and "T3" in section(report, "Ординалы")


def test_unknown_tier_is_a_normal_answer_without_quote(env):
    run(env, FakeLLM())  # every param defaults to unknown
    results = load(env, "step3_params.json")["results"]
    assert {r["status"] for r in results} == {"ok"} and {r["tier"] for r in results} == {"unknown"}


def test_second_run_uses_cache_and_fresh_recomputes(env):
    first = FakeLLM({"honest": ("T3", QUOTE, "r")})
    run(env, first)
    assert first.calls["coref"] > 0 and first.calls["triples"] > 0 and first.calls["params"] == 4

    second = FakeLLM({"honest": ("T3", QUOTE, "r")})
    run(env, second)
    assert second.calls == {"coref": 0, "triples": 0, "params": 0}

    third = FakeLLM()
    run(env, third, "--fresh")
    assert third.calls["coref"] > 0 and third.calls["params"] == 4


def test_rerun_asks_again_only_for_failed_params(env):
    run(env, FakeLLM({"shy": LLMError("boom")}))
    again = FakeLLM({"shy": ("T1", "Her surname contains the kanji", "r")})
    run(env, again)
    assert again.calls == {"coref": 0, "triples": 0, "params": 1}
    shy = next(r for r in load(env, "step3_params.json")["results"] if r["name"] == "shy")
    assert shy["status"] == "ok" and shy["tier"] == "T1"


def test_coref_output_outside_length_range_is_rejected(env, caplog):
    class ShrinkingLLM(FakeLLM):
        def generate(self, system, user, response_model):
            from proto_wiki.domain.schemas import CorefOutput
            if response_model is CorefOutput:
                return CorefOutput(text="Short.")
            return super().generate(system, user, response_model)

    run(env, ShrinkingLLM())
    paragraphs = load(env, "step1_coref.json")["paragraphs"]
    assert all(p["coref_ok"] is False and p["resolved"] == p["original"] for p in paragraphs)
    assert "REJECTED" in caplog.text


def test_coref_call_failure_is_reported_as_error(env):
    class FailingCoref(FakeLLM):
        def generate(self, system, user, response_model):
            from proto_wiki.domain.schemas import CorefOutput
            if response_model is CorefOutput:
                raise LLMError("coref boom")
            return super().generate(system, user, response_model)

    run(env, FailingCoref())
    report = (env["out"] / "report.md").read_text(encoding="utf-8")
    assert "шаг 1" in section(report, "ERRORS") and "coref boom" in section(report, "ERRORS")


def test_evidence_matching_ignores_case_and_punctuation_and_needs_10_chars():
    paras = [ResolvedParagraph(section="s", original="Kyoka, the girl, is HONEST!", resolved="Kyoka Jiro is honest.",
                               coref_ok=True)]
    assert evidence_found("kyoka jiro IS honest", paras)
    assert evidence_found("the girl is honest", paras)  # found in the original text
    assert not evidence_found("is honest", paras)  # shorter than 10 characters
    assert not evidence_found("", paras)


def test_repeated_triples_within_one_answer_are_dropped(env):
    from proto_wiki.domain.schemas import TriplesOutput

    class Repeating(FakeLLM):
        def generate(self, system, user, response_model):
            out = super().generate(system, user, response_model)
            if response_model is TriplesOutput:
                return TriplesOutput(triples=out.triples * 3)
            return out

    run(env, Repeating())
    step2 = load(env, "step2_triples.json")
    assert sum(t["relation"] == "friend_of" for t in step2["triples"]) == 1
    assert step2["dropped"]["duplicate_in_answer"] == 4  # 2 paragraphs with a triple, 3 copies each -> 2 dropped per paragraph
