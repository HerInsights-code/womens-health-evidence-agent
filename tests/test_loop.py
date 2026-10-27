"""Agent loop tests: tagging retry, partial results, matcher retry wiring. No network calls."""

import app.main as main

QUERY = ("I've had really heavy periods for about six months, I'm exhausted all the time no matter "
         "how much I sleep, and my skin keeps breaking out like I'm a teenager again")


def fake_tagger(replies):
    """Returns each reply in turn and records which tag list it was offered."""
    offered = []

    def tag_paragraph(query, allowed):
        offered.append(set(allowed))
        if isinstance(replies[len(offered) - 1], Exception):
            raise replies[len(offered) - 1]
        return replies[len(offered) - 1], "test-model"

    return tag_paragraph, offered


def local_fetch(tags):
    return main.load_articles(), "data/articles.csv"


def test_valid_first_attempt_no_retry(monkeypatch):
    tagger, offered = fake_tagger([["heavy periods"]])
    monkeypatch.setattr(main, "tag_paragraph", tagger)
    out = main.run_agent(QUERY, fetch=local_fetch)
    assert len(offered) == 1
    assert out["tags"] == ["heavy periods"]
    assert not [r for r in out["retries"] if r["step"] == "tagging"]


def test_invalid_first_attempt_retries_with_full_dictionary(monkeypatch):
    tagger, offered = fake_tagger([["iron deficiency"], ["heavy periods"]])
    monkeypatch.setattr(main, "tag_paragraph", tagger)
    out = main.run_agent(QUERY, fetch=local_fetch)
    dictionary, _ = main.load_dictionary()
    assert len(offered) == 2 and offered[1] == dictionary
    assert out["tags"] == ["heavy periods"]
    assert out["rejected"] == ["iron deficiency"]
    assert out["retries"][0]["step"] == "tagging"
    assert out["status"] == "success"


def test_still_invalid_after_retry_returns_partial(monkeypatch):
    tagger, offered = fake_tagger([["made up"], ["also made up"]])
    monkeypatch.setattr(main, "tag_paragraph", tagger)
    out = main.run_agent(QUERY, fetch=local_fetch)
    assert len(offered) == 2
    assert out["status"] == "partial" and out["tags"] == []


def test_tagger_failure_returns_partial_not_crash(monkeypatch):
    tagger, offered = fake_tagger([RuntimeError("HTTP 503")])
    monkeypatch.setattr(main, "tag_paragraph", tagger)
    out = main.run_agent(QUERY, fetch=local_fetch)
    assert out["status"] == "partial"
    assert any("Tagger call failed" in s for s in out["steps"])


def test_given_tags_skip_model(monkeypatch):
    def boom(*args):
        raise AssertionError("model should not be called")

    monkeypatch.setattr(main, "tag_paragraph", boom)
    out = main.run_agent(QUERY, ["heavy periods", "tired all day"], fetch=local_fetch)
    assert out["results"][0]["matched_tags"] == ["heavy periods", "tired all day"]


def test_crisis_blocked_before_tagging(monkeypatch):
    def boom(*args):
        raise AssertionError("model should not be called")

    monkeypatch.setattr(main, "tag_paragraph", boom)
    out = main.run_agent("honestly some days I don't want to be here any more", fetch=local_fetch)
    assert out["status"] == "blocked"
