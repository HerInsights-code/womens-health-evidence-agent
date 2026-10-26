import json

from app.tagging import extract_json_array, load_dictionary, validate_tags

DICTIONARY = {"pcos", "insomnia"}
SYNONYMS = {"polycystic ovary syndrome": "pcos", "endo": "endometriosis"}


# --- validate_tags ---------------------------------------------------------


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


# --- load_dictionary -------------------------------------------------------


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


# --- extract_json_array ----------------------------------------------------


def test_extract_plain_array():
    assert extract_json_array('["pcos", "bad sleep"]') == ["pcos", "bad sleep"]


def test_extract_array_wrapped_in_reasoning():
    reply = (
        "Let me think. She mentions heavy bleeding and tiredness, so those "
        'map to the cycle and sleep groups.\n\n["heavy periods", "tired all day"]'
    )
    assert extract_json_array(reply) == ["heavy periods", "tired all day"]


def test_extract_array_in_markdown_fence():
    reply = 'Here are the tags:\n```json\n["pcos"]\n```'
    assert extract_json_array(reply) == ["pcos"]


def test_extract_empty_array():
    assert extract_json_array("Nothing fits. []") == []


def test_extract_no_array_returns_empty():
    assert extract_json_array("I could not find any matching tags.") == []


def test_extract_malformed_json_returns_empty():
    assert extract_json_array('["pcos", ') == []


def test_extract_array_nested_in_object():
    """A model that wraps its answer in an object still gives usable tags."""
    assert extract_json_array('{"tags": ["pcos"]}') == ["pcos"]