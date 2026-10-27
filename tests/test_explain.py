"""Unit tests for match and explain. No network calls."""

from app.explain import (
    article_tag_evidence,
    evidence_check,
    explain_match,
    load_articles,
    match_and_explain,
    rank_articles,
    tag_confidence,
    user_phrases,
)
from app.tagging import load_synonyms

SYNONYMS = {"heavy menstrual bleeding": "heavy periods", "acne": "skin changes", "ppd": "postpartum depression"}


def article(title, summary="", tags="", year="2020", relevance=None):
    a = {"title": title, "summary": summary, "tags": tags, "published_year": year,
         "doi": "10.1/x", "found_in": "PubMed", "source_url": "https://example.org"}
    if relevance is not None:
        a["relevance_score"] = relevance
    return a


def test_tag_field_counts_after_synonym_mapping():
    ev = article_tag_evidence(article("Any", tags="ppd"), ["postpartum depression"], SYNONYMS)
    assert ev == {"postpartum depression": {"source": "article tag", "phrase": None}}


def test_text_mention_counts_and_quotes_phrase():
    a = article("Treating heavy menstrual bleeding")
    ev = article_tag_evidence(a, ["heavy periods"], SYNONYMS)
    assert ev["heavy periods"]["phrase"] == "heavy menstrual bleeding"


def test_partial_word_does_not_match():
    a = article("Acnestis study")
    assert article_tag_evidence(a, ["skin changes"], SYNONYMS) == {}


def test_more_shared_tags_ranks_first():
    one = article("Heavy periods only", year="2025")
    two = article("Heavy periods and acne", year="2010")
    ranked, considered = rank_articles(["heavy periods", "skin changes"], [one, two], SYNONYMS)
    assert [m["article"]["title"] for m in ranked] == ["Heavy periods and acne", "Heavy periods only"]
    assert considered == 2


def test_tie_broken_by_relevance_then_year():
    old_graded = article("Heavy periods A", year="2001", relevance="0.9")
    new_ungraded = article("Heavy periods B", year="2024")
    newer = article("Heavy periods C", year="2025")
    ranked, _ = rank_articles(["heavy periods"], [new_ungraded, newer, old_graded], SYNONYMS)
    assert [m["article"]["title"] for m in ranked] == ["Heavy periods A", "Heavy periods C", "Heavy periods B"]


def test_stated_tag_beats_inferred_tag_on_tie():
    inferred = article("Acne study", year="2026")
    stated = article("Heavy periods study", year="2000")
    ranked, _ = rank_articles(["heavy periods", "skin changes"], [inferred, stated], SYNONYMS,
                              weights={"heavy periods": 3, "skin changes": 1})
    assert ranked[0]["article"]["title"] == "Heavy periods study"


def test_unmatched_articles_left_out_and_top_n_capped():
    arts = [article(f"Heavy periods {i}") for i in range(5)] + [article("Unrelated")]
    ranked, considered = rank_articles(["heavy periods"], arts, SYNONYMS)
    assert len(ranked) == 3 and considered == 5


def test_user_phrases_and_confidence():
    phrases = user_phrases("I get acne and heavy periods", ["heavy periods", "skin changes", "pcos"], SYNONYMS)
    assert phrases == {"heavy periods": "heavy periods", "skin changes": "acne", "pcos": None}
    assert tag_confidence("heavy periods", "heavy periods") == "high"
    assert tag_confidence("skin changes", "acne") == "medium"
    assert tag_confidence("pcos", None) == "low"


def test_explanation_names_missing_tags_and_cites_doi():
    match = {"article": article("Heavy periods review"), "evidence": {"heavy periods": {"source": "article text", "phrase": "Heavy periods"}}}
    result = explain_match(match, 1, {"heavy periods": "heavy periods"}, ["heavy periods", "skin changes"])
    assert "does not cover skin changes" in result["why"]
    assert "doi:10.1/x" in result["citation"]
    assert 'you said "heavy periods"' in result["reasons"][0]["text"]


def test_evidence_check_removes_phrase_not_in_text():
    match = {"article": article("x"), "evidence": {"heavy periods": {"source": "article tag", "phrase": None}}}
    result = {"rank": 1, "reasons": [{"tag": "heavy periods", "user_phrase": "bleeding a lot", "article_phrase": None, "text": ""}]}
    checked, removed = evidence_check([result], "my periods are heavy", [match])
    assert checked[0]["reasons"][0]["user_phrase"] is None
    assert removed[0]["why"] == "cited phrase not in user text"


def test_evidence_check_drops_result_with_no_supported_tags():
    match = {"article": article("x"), "evidence": {}}
    result = {"rank": 1, "reasons": [{"tag": "pcos", "user_phrase": None, "article_phrase": None, "text": ""}]}
    checked, removed = evidence_check([result], "anything", [match])
    assert checked == []
    assert removed[-1]["why"] == "no supported tags left, result dropped"


def test_real_data_example_1_returns_results():
    query = ("I've had really heavy periods for about six months, I'm exhausted all the time no matter "
             "how much I sleep, and my skin keeps breaking out like I'm a teenager again")
    out = match_and_explain(query, ["heavy periods", "skin changes", "tired all day"], load_articles(), load_synonyms())
    assert out["results"], "expected at least one match from data/articles.csv"
    assert all(r["matched_tags"] for r in out["results"])
