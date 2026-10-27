"""Serve the dictionary and articles as JSON so Zetaris can register them
as REST tables. Zetaris runs in Docker and cannot read local files, but it
can reach this server at host.docker.internal.
"""

import csv
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = 8900
ROOT = Path(__file__).resolve().parent.parent


def tags_payload():
    groups = json.loads((ROOT / "data/tag_dictionary.json").read_text())
    rows = [
        {"tag": tag, "tag_group": group}
        for group, tags in groups.items()
        for tag in tags
    ]
    return {"rows": rows}


def articles_payload():
    path = ROOT / "data/articles.csv"
    if not path.exists():
        return {"rows": []}
    with path.open(encoding="utf-8") as handle:
        rows = []
        for row in csv.DictReader(handle):
            rows.append({
                "record_key": row["record_key"],
                "doi": row["doi"],
                "title": row["title"],
                "summary": row["summary"][:2000],
                "published_year": row["published_year"],
                "found_in": row["found_in"],
                "source_url": row["source_url"],
                "tags": row["tags"],
            })
    return {"rows": rows}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/tags"):
            payload = tags_payload()
        elif self.path.startswith("/articles"):
            payload = articles_payload()
        else:
            self.send_error(404)
            return
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"serving on http://0.0.0.0:{PORT}  (/tags, /articles)")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()