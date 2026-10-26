"""Paragraph tagging: dictionary load, model tagging, and tag validation."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from app.adapters import nightshift

SYSTEM_PROMPT = (
    "You tag what a woman says about her health using a fixed vocabulary.\n"
    "Return ONLY a JSON array of tag strings, nothing else.\n"
    "Use only tags from the list given. Never invent a tag.\n"
    "Pick every tag the text supports, usually two to five.\n"
    "If nothing in the list fits, return []."
)


def load_dictionary(path: str = "data/tag_dictionary.json") -> tuple[set[str], dict]:
    """Read grouped tag JSON and return (flat tag set, original group mapping)."""
    with Path(path).open(encoding="utf-8") as handle:
        groups_dict = json.load(handle)
    flat_set = {tag for tags in groups_dict.values() for tag in tags}
    return flat_set, groups_dict


def load_synonyms(path: str = "data/synonyms.json") -> dict:
    """Read the synonym map. Returns an empty map if the file is absent."""
    try:
        with Path(path).open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}


def extract_json_array(text: str) -> list:
    """Pull the first JSON array out of a reply that may contain reasoning text."""
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def tag_paragraph(paragraph: str, candidate_tags) -> tuple[list, str]:
    """Ask the model for tags from candidate_tags.

    Returns (raw_tags, routed_model). The tags are unvalidated — pass them
    through validate_tags before using them.
    """
    user_prompt = (
        f"Available tags:\n{json.dumps(sorted(candidate_tags))}\n\n"
        f"What she wrote:\n{paragraph}\n\n"
        "JSON array of tags:"
    )
    reply, routed_model = nightshift.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    return extract_json_array(reply), routed_model


def validate_tags(raw_tags, dictionary, synonyms) -> tuple[list[str], list[str]]:
    """Normalize raw tags, map synonyms, and split into valid vs rejected."""
    valid: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()

    for raw in raw_tags:
        normalized = str(raw).lower().strip()
        if not normalized:
            continue
        canonical = synonyms.get(normalized, normalized)
        if canonical in dictionary:
            if canonical not in seen:
                seen.add(canonical)
                valid.append(canonical)
        else:
            rejected.append(raw)

    return valid, rejected


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python -m app.tagging "her paragraph here"')
        raise SystemExit(1)

    paragraph = " ".join(sys.argv[1:])
    dictionary, _groups = load_dictionary()
    synonyms = load_synonyms()

    raw, routed_model = tag_paragraph(paragraph, dictionary)
    valid, rejected = validate_tags(raw, dictionary, synonyms)

    print(f"model:    {routed_model}")
    print(f"proposed: {raw}")
    print(f"tags:     {valid}")
    if rejected:
        print(f"dropped:  {rejected}")


if __name__ == "__main__":
    main()