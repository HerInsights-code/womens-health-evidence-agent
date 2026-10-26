import json
import os

from common import write_csv
from config import TAG_QUERIES
import pull_pubmed
import pull_europe_pmc
import pull_semantic_scholar


def check_dictionary():
    path = os.path.join("data", "tag_dictionary.json")
    if not os.path.exists(path):
        print("No tag dictionary yet, skipping the tag check")
        return
    with open(path, encoding="utf-8") as f:
        dictionary = set(json.load(f))
    missing = [t for t in TAG_QUERIES if t not in dictionary]
    if missing:
        print("Warning: these tags are not in the dictionary:", missing)


def main():
    check_dictionary()
    for module in (pull_pubmed, pull_europe_pmc, pull_semantic_scholar):
        module.run()
    total = write_csv()
    print(f"Wrote {total} unique records to data/articles.csv")


if __name__ == "__main__":
    main()