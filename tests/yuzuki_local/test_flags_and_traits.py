from pathlib import Path

from yuzuki_local.entities.flag import FlagSet
from yuzuki_local.workers.trait_aggregator import TraitAggregator

PKG = Path(__file__).resolve().parents[2] / "src" / "yuzuki_local"


def test_flag_set_has_v2_flags_plus_three_new():
    flags = FlagSet.load(PKG / "flags" / "flags.yaml")
    ids = {f.id for f in flags.flags}
    assert len(flags.flags) == 64
    assert {"exploits_affection", "envies_others", "ingratiates_with_powerful"} <= ids
    assert all(a in ids and b in ids for a, b in flags.conflict_pairs())


def test_flag_prompt_j2_is_the_original():
    text = (PKG / "flags" / "flag_prompt.j2").read_text(encoding="utf-8")
    assert text.startswith("=== CHARACTER CONTEXT ===\n{{ context }}\n=== END CONTEXT ===")


def _flags(tmp_path, body):
    p = tmp_path / "f.yaml"
    p.write_text("version: '1'\nflags:\n" + body, encoding="utf-8")
    return FlagSet.load(p)


ITEM = "  - {{id: {id}, type: behavior, question: q, look_for: l, not_this: n, trait: {trait}}}\n"


def test_score_is_signed_mean_of_yes_no_and_coverage_counts_answered(tmp_path):
    body = (ITEM.format(id="a", trait="[[hh, 1]]") + ITEM.format(id="b", trait="[[hh, -1]]")
            + ITEM.format(id="c", trait="[[hh, 1]]") + ITEM.format(id="d", trait="[[hh, 1]]"))
    agg = TraitAggregator(_flags(tmp_path, body))
    (t,) = agg.aggregate({"a": "yes", "b": "yes", "c": "no_data", "d": None})
    assert (t.score, t.coverage, t.n_answered, t.n_items) == (0.0, 0.5, 2, 4)   # (+1 and -1) / 2


def test_all_no_data_gives_no_score_and_null_trait_is_not_aggregated(tmp_path):
    body = ITEM.format(id="a", trait="[[hh, 1]]") + ITEM.format(id="solo", trait="null")
    (t,) = TraitAggregator(_flags(tmp_path, body)).aggregate({"a": "no_data", "solo": "yes"})
    assert t.score is None and t.coverage == 0.0
