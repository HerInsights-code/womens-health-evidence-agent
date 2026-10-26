import os
import time

import requests
from dotenv import load_dotenv

from common import add_record
from config import TAG_QUERIES, PER_QUERY, MIN_CITATIONS

load_dotenv()
URL = "https://api.semanticscholar.org/graph/v1/paper/search"
HEADERS = {}
if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
    HEADERS["x-api-key"] = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
FIELDS = "paperId,title,url,abstract,year,externalIds,citationCount"


def search(query, retries=5):
    params = {
        "query": query,
        "limit": PER_QUERY,
        "fields": FIELDS,
        "minCitationCount": MIN_CITATIONS,
    }
    for attempt in range(retries):
        r = requests.get(URL, params=params, headers=HEADERS, timeout=20)
        if r.status_code == 429:
            wait = 2 ** attempt
            print(f"Semantic Scholar rate limited, waiting {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json().get("data", [])
    print(f"Semantic Scholar gave up on: {query}")
    return []


def run():
    for tag, query in TAG_QUERIES.items():
        try:
            papers = search(query)
            added = 0
            for paper in papers:
                doi = (paper.get("externalIds") or {}).get("DOI")
                added += add_record(
                    source="Semantic Scholar",
                    external_id=paper.get("paperId"),
                    title=paper.get("title"),
                    summary=paper.get("abstract"),
                    year=str(paper.get("year") or ""),
                    url=paper.get("url"),
                    tag=tag,
                    doi=doi,
                )
            print(f"Semantic Scholar {tag}: {added} records with abstracts")
        except Exception as e:
            print(f"Semantic Scholar {tag} failed: {e}")
        time.sleep(3)