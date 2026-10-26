"""Entry point. Runs Scout Intent and the tagger on one input file.

Usage:
    python run.py input_examples/example_1.json
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

    raw, routed_model = tag_paragraph(query, candidates)
    tags, rejected = validate_tags(raw, dictionary, synonyms)

    return {
        "status": "success",
        "intent": decision.primary,
        "confidence": decision.confidence,
        "tag_groups": decision.tag_groups,
        "tags_considered": len(candidates),
        "tags": tags,
        "rejected": rejected,
        "model": routed_model,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python run.py input_examples/example_1.json")
        raise SystemExit(1)

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(run(payload["input"]["query"]), indent=2))


if __name__ == "__main__":
    main()