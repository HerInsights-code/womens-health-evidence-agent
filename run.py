"""Entry point. Runs the full pipeline on one input file.

Scout Intent routes the paragraph to tag groups, the tagger assigns tags
from only those groups via Nemotron through Meterless Nightshift, and
Zetaris returns the research matching those tags.

Usage:
    python run.py input_examples/input_example_1.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.engines.scout_intent import ScoutIntent
from app.tagging import load_dictionary, load_synonyms, tag_paragraph, validate_tags


def run(query: str) -> dict:
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

    raw, routed_model = tag_paragraph(query, candidates)
    tags, rejected = validate_tags(raw, dictionary, synonyms)

    try:
        from app.adapters import zetaris
        matches = zetaris.find_articles(tags, limit=5)
    except Exception as error:
        print(f"[warn] Zetaris match failed: {type(error).__name__}")
        matches = []

    return {
        "status": "success",
        "intent": decision.primary,
        "confidence": decision.confidence,
        "tag_groups": decision.tag_groups,
        "tags_considered": len(candidates),
        "tags": tags,
        "rejected": rejected,
        "matches": [
            {
                "title": m["title"],
                "tags": m["tags"],
                "shared_tags": m["shared"],
                "year": m["published_year"],
                "source": m["found_in"],
                "url": m["source_url"],
            }
            for m in matches
        ],
        "model": routed_model,
        "trace_id": decision.trace_id,
        "contract_id": decision.contract["contractId"],
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python run.py input_examples/input_example_1.json")
        raise SystemExit(1)

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(run(payload["input"]["query"]), indent=2))


if __name__ == "__main__":
    main()