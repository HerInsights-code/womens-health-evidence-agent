"""Entry point. Runs the agent (app/main.py) on one input file.

Scout Intent routes the paragraph to tag groups, the tagger assigns tags
from only those groups via Nemotron through Meterless Nightshift (retrying
once with the full dictionary if none are valid), Zetaris returns the
research sharing those tags (widening once to related tags if none match),
and match and explain ranks the top results and says why each one matches.

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
from pathlib import Path

from app.main import run_agent


def run(query: str, given_tags: list[str] | None = None) -> dict:
    return run_agent(query, given_tags)


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
