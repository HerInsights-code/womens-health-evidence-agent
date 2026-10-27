"""Entry point. Runs Scout Intent, the tagger, then match and explain on one input file.

Usage:
    python run.py input_examples/input_example_1.json
    python run.py input_examples/input_example_1.json --tags "heavy periods,skin changes"

--tags skips the model call and uses the given tags (still validated against
the dictionary), so the demo runs without Nightshift.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.engines.scout_intent import ScoutIntent
from app.explain import load_articles, match_and_explain
from app.tagging import load_dictionary, load_synonyms, tag_paragraph, validate_tags


def run(query: str, given_tags: list[str] | None = None) -> dict:
    scout = ScoutIntent()
    decision = scout.decide(query, surface="api")

    if decision.risk.level == "block":
        return {
            "status": "blocked",
            "reason": decision.risk.reason,
            "flags": decision.risk.flags,
        }

    if decision.clarification:
        return {
            "status": "needs_clarification",
            "question": decision.clarification.question,
            "options": decision.clarification.options,
        }

    dictionary, groups = load_dictionary()
    synonyms = load_synonyms()
    candidates = {tag for g in decision.tag_groups for tag in groups.get(g, [])}

    if given_tags is None:
        raw, routed_model = tag_paragraph(query, candidates)
    else:
        raw, routed_model = given_tags, "none (tags given with --tags)"
    tags, rejected = validate_tags(raw, dictionary, synonyms)

    matched = match_and_explain(query, tags, load_articles(), synonyms)

    return {
        "status": "success" if matched["results"] else "partial",
        "intent": decision.primary,
        "confidence": decision.confidence,
        "tag_groups": decision.tag_groups,
        "tags_considered": len(candidates),
        "tags": tags,
        "rejected": rejected,
        "model": routed_model,
        **matched,
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
