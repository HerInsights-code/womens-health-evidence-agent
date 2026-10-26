import os
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

from common import add_record
from config import TAG_QUERIES, PER_QUERY

load_dotenv()
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
API_KEY = os.getenv("NCBI_API_KEY")
DELAY = 0.15 if API_KEY else 0.4  # NCBI allows more requests per second with a key


def _params(extra):
    p = {"db": "pubmed", **extra}
    if API_KEY:
        p["api_key"] = API_KEY
    return p


def search(query):
    r = requests.get(f"{BASE}/esearch.fcgi", timeout=20, params=_params({
        "term": query, "retmax": PER_QUERY, "retmode": "json", "sort": "relevance",
    }))
    r.raise_for_status()
    return r.json()["esearchresult"]["idlist"]


def summaries(ids):
    r = requests.get(f"{BASE}/esummary.fcgi", timeout=20, params=_params({
        "id": ",".join(ids), "retmode": "json",
    }))
    r.raise_for_status()
    return r.json()["result"]


def abstracts(ids):
    r = requests.get(f"{BASE}/efetch.fcgi", timeout=20, params=_params({
        "id": ",".join(ids), "retmode": "xml", "rettype": "abstract",
    }))
    r.raise_for_status()
    out = {}
    root = ET.fromstring(r.content)
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//PMID")
        parts = ["".join(t.itertext()).strip() for t in art.findall(".//Abstract/AbstractText")]
        parts = [p for p in parts if p]
        if pmid and parts:
            out[pmid] = " ".join(parts)
    return out


def doi_from(doc):
    for aid in doc.get("articleids", []):
        if aid.get("idtype") == "doi":
            return aid.get("value")
    loc = doc.get("elocationid", "")
    if loc.lower().startswith("doi:"):
        return loc[4:].strip()
    return None


def run():
    for tag, query in TAG_QUERIES.items():
        try:
            ids = search(query)
            time.sleep(DELAY)
            if not ids:
                print(f"PubMed {tag}: no results")
                continue
            docs = summaries(ids)
            time.sleep(DELAY)
            abs_map = abstracts(ids)
            time.sleep(DELAY)

            added = 0
            for pmid in ids:
                doc = docs.get(pmid)
                if not doc:
                    continue
                added += add_record(
                    source="PubMed",
                    external_id=pmid,
                    title=doc.get("title"),
                    summary=abs_map.get(pmid),
                    year=(doc.get("pubdate") or "")[:4],
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    tag=tag,
                    doi=doi_from(doc),
                )
            print(f"PubMed {tag}: {added} records with abstracts")
        except Exception as e:
            print(f"PubMed {tag} failed: {e}")