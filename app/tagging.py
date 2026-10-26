"""Paragraph tagging helpers: dictionary load and tag validation."""

from __future__ import annotations

import json
from pathlib import Path


def load_dictionary(path: str = "data/tag_dictionary.json") -> tuple[set[str], dict]:
    """Read grouped tag JSON and return (flat tag set, original group mapping)."""
    with Path(path).open(encoding="utf-8") as handle:
        groups_dict = json.load(handle)
    flat_set = {tag for tags in groups_dict.values() for tag in tags}
    return flat_set, groups_dict


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
