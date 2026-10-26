import json

from app.tagging import load_dictionary, validate_tags

DICTIONARY = {"pcos", "insomnia"}
SYNONYMS = {"polycystic ovary syndrome": "pcos", "endo": "endometriosis"}


def test_unknown_tag_is_rejected():
    valid, rejected = validate_tags(["not-a-tag"], DICTIONARY, SYNONYMS)
    assert valid == []
    assert rejected == ["not-a-tag"]


def test_rejected_keeps_original_raw_tag():
    valid, rejected = validate_tags(["  Endo  "], DICTIONARY, SYNONYMS)
    assert valid == []
    assert rejected == ["  Endo  "]


def test_synonym_maps_to_canonical_form():
    valid, rejected = validate_tags(
        ["polycystic ovary syndrome"], DICTIONARY, SYNONYMS
    )
    assert valid == ["pcos"]
    assert rejected == []


def test_duplicates_collapse_preserving_order():
    valid, rejected = validate_tags(["pcos", "PCOS"], DICTIONARY, SYNONYMS)
    assert valid == ["pcos"]
    assert rejected == []


def test_case_and_whitespace_are_handled():
    valid, rejected = validate_tags(["  PCOS  "], DICTIONARY, SYNONYMS)
    assert valid == ["pcos"]
    assert rejected == []


def test_empty_and_whitespace_tags_are_skipped():
    valid, rejected = validate_tags(["", "   ", "\t"], DICTIONARY, SYNONYMS)
    assert valid == []
    assert rejected == []


def test_empty_input_returns_two_empty_lists():
    valid, rejected = validate_tags([], DICTIONARY, SYNONYMS)
    assert valid == []
    assert rejected == []


def test_load_dictionary_flat_set_and_groups(tmp_path):
    groups = {
        "sleep": ["bad sleep", "tired all day"],
        "cycle": ["pcos"],
    }
    path = tmp_path / "tag_dictionary.json"
    path.write_text(json.dumps(groups), encoding="utf-8")

    flat_set, groups_dict = load_dictionary(str(path))

    assert flat_set == {"bad sleep", "tired all day", "pcos"}
    assert groups_dict == groups
