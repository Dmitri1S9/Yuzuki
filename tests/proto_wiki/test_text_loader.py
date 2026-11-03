import pytest

from proto_wiki.errors import LoaderError, ParamsFormatError
from proto_wiki.services.parsing.params_loader import load_params
from proto_wiki.services.parsing.text_loader import load_document

from conftest import CHARACTER, MAIN_WIKITEXT, REL_WIKITEXT


def _sections(doc):
    return [p.section for p in doc.paragraphs]


def test_load_from_xml_dump(env):
    doc = load_document(env["dump"], CHARACTER)
    text = " ".join(p.text for p in doc.paragraphs)
    assert "Kyoka Jiro is a student in Class 1-A" in text  # Nihongo template keeps the name
    assert "must never reach" not in text and "gallery section" not in text
    assert "Unrelated page" not in text
    assert "thumb" not in text and "Parents.png" not in text
    assert "Relationships / Kyotoku and Mika Jiro" in _sections(doc)


def test_load_from_folder_with_dump(env):
    assert load_document(env["dump"].parent, CHARACTER).paragraphs


def test_load_from_wikitext_file(tmp_path):
    f = tmp_path / "jiro.wiki"
    f.write_text(MAIN_WIKITEXT + "\n" + REL_WIKITEXT, encoding="utf-8")
    doc = load_document(f, CHARACTER)
    assert {"Introduction", "Personality", "Trivia"} <= set(_sections(doc))
    assert doc.aliases["Kaminari"] == "Denki Kaminari"


def test_load_from_plain_text(tmp_path):
    f = tmp_path / "jiro.txt"
    f.write_text("Kyoka Jiro is a student at UA. She likes music.\n\nHer friend is Kaminari and they talk a lot.",
                 encoding="utf-8")
    doc = load_document(f, CHARACTER)
    assert len(doc.paragraphs) == 2
    assert {p.section for p in doc.paragraphs} == {"Text"}
    assert doc.aliases == {CHARACTER: CHARACTER}


def test_alias_dict_uses_link_targets_as_canonical_ids(env):
    aliases = load_document(env["dump"], CHARACTER).aliases
    assert aliases["Kaminari"] == "Denki Kaminari"
    assert aliases["Denki Kaminari"] == "Denki Kaminari"
    assert aliases["Kyotoku"] == "Kyotoku Jiro"
    assert "Parents.png" not in " ".join(aliases)


def test_missing_character_page_is_an_error(env):
    with pytest.raises(LoaderError, match="нет страницы"):
        load_document(env["dump"], "Nobody Here")


def test_params_counts_and_tiers(env):
    params = load_params(env["params"])
    assert sum(not p.ordinal for p in params) == 3
    assert sum(p.ordinal for p in params) == 1
    assert next(p for p in params if p.name == "intellect").tiers == ["T1", "T2", "T3", "unknown"]
    assert next(p for p in params if p.name == "honest").tiers == ["T1", "T2", "T3", "unknown"]


def test_ordinal_without_tiers_defaults_to_t1_t5(tmp_path):
    import json
    f = tmp_path / "p.json"
    f.write_text(json.dumps({"ordinals": {"x": {"definition": "d"}}, "flags": {"a": {"definition": "d"}}}))
    x = next(p for p in load_params(f) if p.ordinal)
    assert x.tiers == ["T1", "T2", "T3", "T4", "T5", "unknown"]


@pytest.mark.parametrize("content", [
    "[]",
    '{"flags": {"a": {"definition": "d"}}}',                       # no ordinals
    '{"ordinals": {"x": {"definition": "d"}}}',                    # no flag category
    '{"ordinals": {"x": {"definition": "d"}}, "cat": {"a": 5}}',   # entry is not an object
    '{"ordinals": {"x": {"definition": "d", "tier_count": 1}}, "cat": {"a": {"definition": "d"}}}',
])
def test_unrecognized_params_structure_fails_loudly(tmp_path, content):
    f = tmp_path / "p.json"
    f.write_text(content)
    with pytest.raises(ParamsFormatError):
        load_params(f)


def test_real_parameters_json_is_recognized():
    from pathlib import Path
    real = Path(__file__).resolve().parents[2] / "src" / "domain" / "parameters.json"
    params = load_params(real)
    assert sum(p.ordinal for p in params) == 6
    assert sum(not p.ordinal for p in params) == 51
