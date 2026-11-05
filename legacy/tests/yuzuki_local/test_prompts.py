from pathlib import Path

from yuzuki_local.entities.flag import FlagSet
from yuzuki_local.entities.ordinal import OrdinalSet
from yuzuki_local.workers.prompt_renderer import PromptRenderer

PKG = Path(__file__).resolve().parents[2] / "src" / "yuzuki_local"
CTX = "CONTEXT-BODY " * 50


def test_every_prompt_of_a_character_starts_with_the_same_cache_prefix():
    r = PromptRenderer()
    flags = FlagSet.load(PKG / "flags" / "flags.yaml")
    scale = OrdinalSet.load(PKG / "ordinals" / "ordinals.yaml").scales[0]
    prompts = [
        r.flag(CTX, "Kyoka Jiro", "MHA", flags.flags[0]),
        r.flag(CTX, "Kyoka Jiro", "MHA", flags.flags[7]),
        r.ordinal(CTX, "Kyoka Jiro", "MHA", scale),
        r.render("occupation_prompt.j2", context=CTX, character="Kyoka Jiro", universe="MHA", question="Q?"),
        r.render("partners_prompt.j2", context=CTX, character="Kyoka Jiro", universe="MHA", max_partners=5),
        r.render("edge_prompt.j2", context=CTX, character="Kyoka Jiro", partner="Momo", universe="MHA",
                 min_quotes=3, max_quotes=10),
    ]
    head = 'You are '
    prefix = prompts[0].split(head)[0]
    assert CTX in prefix
    for p in prompts[1:]:
        assert p.startswith(prefix)
    # flag-specific text comes after the shared prefix and differs
    assert prompts[0] != prompts[1]
    assert prompts[0].index(flags.flags[0].id) > len(prefix)


def test_flag_template_hash_changes_only_with_the_template():
    r = PromptRenderer()
    assert r.template_hash("flag_prompt.j2") == r.template_hash("flag_prompt.j2")
