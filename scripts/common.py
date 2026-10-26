import csv
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "data", "articles.csv")
FIELDS = ["record_key", "doi", "title", "summary", "published_year",
          "found_in", "source_url", "tags", "tag_method"]

_store = {}


def _norm_title(title):
    return re.sub(r"[^a-z0-9]", "", title.lower())


def add_record(source, external_id, title, summary, year, url, tag, doi=None):
    title = (title or "").strip()
    summary = (summary or "").strip()
    if not title or not summary:
        return False  # skip records without an abstract; never fill it with the title

    doi = (doi or "").strip().lower() or None
    key = f"doi:{doi}" if doi else f"title:{_norm_title(title)}"

    rec = _store.get(key)
    if rec is None:
        rec = {
            "record_key": key,
            "doi": doi or "",
            "title": title,
            "summary": summary,
            "published_year": year or "",
            "found_in": set(),
            "source_url": url or "",
            "tags": set(),
            "tag_method": "query",
        }
        _store[key] = rec

    rec["found_in"].add(source)
    rec["tags"].add(tag)
    return True


def write_csv():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for rec in _store.values():
            writer.writerow({
                **rec,
                "found_in": ";".join(sorted(rec["found_in"])),
                "tags": ";".join(sorted(rec["tags"])),
            })
    return len(_store)