"""Re-tag articles with dictionary tags, so the matcher can score them
against tags the tagger actually produces.

Reads data/articles.csv, asks Nemotron through Nightshift for tags from the
dictionary, validates them the same way the tagger does, and writes the file
back. Keeps the original search term in a new `topic` column.
"""

import csv
import json
import time
from pathlib import Path

from app.adapters import nightshift
from app.tagging import (
    extract_json_array,
    load_dictionary,
    load_synonyms,
    validate_tags,
)

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/articles.csv"
OUT = ROOT / "data/articles.csv"

SYSTEM = (
    "You tag medical research papers with the symptoms and experiences they "
    "are relevant to, using a fixed vocabulary.\n"
    "Return ONLY a JSON array of tag strings from the list given.\n"
    "Pick the tags a woman experiencing those things would search with. "
    "Usually two to four. Never invent a tag."
)


def main() -> None:
    dictionary, _groups = load_dictionary()
    synonyms = load_synonyms()
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    print(f"re-tagging {len(rows)} articles against {len(dictionary)} tags\n")

    for i, row in enumerate(rows, 1):
        prompt = (
            f"Available tags:\n{json.dumps(sorted(dictionary))}\n\n"
            f"Title: {row['title']}\n"
            f"Abstract: {row['summary'][:1200]}\n\n"
            "JSON array of tags:"
        )
        try:
            reply, _model = nightshift.chat(
                [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt},
                ]
            )
            raw = extract_json_array(reply)
            tags, _rejected = validate_tags(raw, dictionary, synonyms)
        except Exception as error:
            print(f"  {i:>3} FAILED {type(error).__name__}")
            tags = []

        row["topic"] = row["tags"]          # keep the original search term
        row["tags"] = ";".join(tags) if tags else row["tags"]
        print(f"  {i:>3} {row['title'][:42]:<42} -> {tags}")
        time.sleep(0.3)

    fields = list(rows[0].keys())
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nwrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()