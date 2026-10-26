import time

import requests

from common import add_record
from config import TAG_QUERIES, PER_QUERY

URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def search(query):
    r = requests.get(URL, timeout=20, params={
        "query": f"({query}) AND HAS_ABSTRACT:y",
        "format": "json",
        "pageSize": PER_QUERY,
        "resultType": "core",
    })
    r.raise_for_status()
    return r.json().get("resultList", {}).get("result", [])


def run():
    for tag, query in TAG_QUERIES.items():
        try:
            results = search(query)
            added = 0
            for res in results:
                pmid = res.get("pmid")
                doi = res.get("doi")
                ident = pmid or res.get("id") or res.get("pmcid")
                if not ident:
                    continue
                if pmid:
                    url = f"https://europepmc.org/article/MED/{pmid}"
                elif doi:
                    url = f"https://doi.org/{doi}"
                else:
                    url = ""
                added += add_record(
                    source="Europe PMC",
                    external_id=ident,
                    title=res.get("title"),
                    summary=res.get("abstractText"),
                    year=res.get("pubYear"),
                    url=url,
                    tag=tag,
                    doi=doi,
                )
            print(f"Europe PMC {tag}: {added} records with abstracts")
        except Exception as e:
            print(f"Europe PMC {tag} failed: {e}")
        time.sleep(0.5)