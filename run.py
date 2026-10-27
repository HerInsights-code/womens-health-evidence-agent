"""Entry point. Runs the full pipeline on one input file.

Scout Intent routes the paragraph to tag groups, the tagger assigns tags
from only those groups via Nemotron through Meterless Nightshift, Zetaris
returns the research sharing those tags, and match and explain ranks the
top results and says why each one matches.

Usage:
    python run.py input_examples/input_example_1.json
    python run.py input_examples/input_example_1.json --tags "heavy periods,skin changes"

--tags skips the model call and uses the given tags (still validated against
the dictionary), so the demo runs without Nightshift. If Zetaris is not
reachable, articles come from data/articles.csv instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.engines.scout_intent import ScoutIntent
from app.explain import load_articles, match_and_explain
from app.tagging import load_dictionary, load_synonyms, tag_paragraph, validate_tags

CANDIDATE_LIMIT = 20


def fetch_candidates(tags: list[str]) -> tuple[list[dict], str]:
    """Articles sharing any tag, from Zetaris, or the local file if Zetaris is down."""
    try:
        from app.adapters import zetaris
        return zetaris.find_articles(tags, limit=CANDIDATE_LIMIT), "zetaris"
    except Exception as error:
        print(f"[warn] Zetaris match failed: {type(error).__name__}, using data/articles.csv", file=sys.stderr)
        return load_articles(), "data/articles.csv"


def run(query: str, given_tags: list[str] | None = None) -> dict:
    scout = ScoutIntent()
    decision = scout.decide(query, surface="api")

    if decision.risk.level == "block":
        return {
            "status": "blocked",
            "reason": decision.risk.reason,
            "flags": decision.risk.flags,
            "trace_id": decision.trace_id,
        }

    if decision.clarification:
        return {
            "status": "needs_clarification",
            "question": decision.clarification.question,
            "options": decision.clarification.options,
            "trigger": decision.clarification.trigger,
            "trace_id": decision.trace_id,
        }

    dictionary, groups = load_dictionary()
    synonyms = load_synonyms()
    candidates = {tag for g in decision.tag_groups for tag in groups.get(g, [])}

    if given_tags is None:
        raw, routed_model = tag_paragraph(query, candidates)
    else:
        raw, routed_model = given_tags, "none (tags given with --tags)"
    tags, rejected = validate_tags(raw, dictionary, synonyms)

    articles, article_source = fetch_candidates(tags)
    matched = match_and_explain(query, tags, articles, synonyms)

    return {
        "status": "success" if matched["results"] else "partial",
        "intent": decision.primary,
        "confidence": decision.confidence,
        "tag_groups": decision.tag_groups,
        "tags_considered": len(candidates),
        "tags": tags,
        "rejected": rejected,
        "article_source": article_source,
        "matches": matched["results"],
        **matched,
        "model": routed_model,
        "trace_id": decision.trace_id,
        "contract_id": decision.contract["contractId"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input_file")
    parser.add_argument("--tags", help="comma-separated tags; skips the model call")
    args = parser.parse_args()

    payload = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
    given = [t.strip() for t in args.tags.split(",")] if args.tags else None
    print(json.dumps(run(payload["input"]["query"], given), indent=2))


if __name__ == "__main__":
    main()
