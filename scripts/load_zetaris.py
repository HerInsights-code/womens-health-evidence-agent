"""Register the tag dictionary and articles in Zetaris as REST tables,
then flatten them into schemastore views.

Zetaris runs in Docker and cannot read local files, so scripts/serve_data.py
exposes our data over HTTP and Zetaris reaches it at host.docker.internal.

Run scripts/serve_data.py in another terminal first.
"""

import os
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

URL = os.environ["ZETARIS_REST_URL"].rstrip("/") + "/sql-editor/sqls/run"
HEADERS = {
    "Authorization": f"Bearer {os.environ['ZETARIS_API_KEY']}",
    "X-Org-ID": os.environ["ZETARIS_ORG_ID"],
    "Content-Type": "application/json",
}

DATA_HOST = "http://host.docker.internal:8900"


def run(sql: str):
    body = {
        "queryId": str(uuid.uuid4()),
        "sql": sql.strip(),
        "source": "SqlEditor",
        "limit": 200,
    }
    headers = {**HEADERS, "X-Request-ID": str(uuid.uuid4())}
    response = requests.post(URL, headers=headers, json=body, timeout=120)
    ok = response.status_code == 200 and '"msg"' not in response.text[:20]
    first_line = sql.strip().splitlines()[0][:66]
    print(f"{'PASS' if ok else 'SKIP'}  {first_line}")
    if not ok:
        print(f"      {response.text[:220]}\n")
    return response


STATEMENTS = [
    'CREATE LIGHTNING DATABASE HERINSIGHTS_REST '
    'DESCRIBE BY "HerInsights local data - tags and articles"',

    "CREATE SCHEMASTORE CONTAINER herinsights",

    f'''CREATE LIGHTNING REST TABLE tag_source FROM HERINSIGHTS_REST REQUEST(
        endpoint "{DATA_HOST}/tags",
        method "get",
        response_type "json",
        http_encoding "URLENCODED"
    ) HEADER (
    ) BODY ()''',

    f'''CREATE LIGHTNING REST TABLE article_source FROM HERINSIGHTS_REST REQUEST(
        endpoint "{DATA_HOST}/articles",
        method "get",
        response_type "json",
        http_encoding "URLENCODED"
    ) HEADER (
    ) BODY ()''',

    '''CREATE OR REPLACE SCHEMASTORE VIEW tag_dictionary WITH CONTAINER herinsights AS
        SELECT r.tag, r.tag_group
        FROM herinsights_rest.tag_source
        LATERAL VIEW explode(rows) AS r''',

    '''CREATE OR REPLACE SCHEMASTORE VIEW articles WITH CONTAINER herinsights AS
        SELECT
            r.record_key,
            r.doi,
            r.title,
            r.summary,
            r.published_year,
            r.found_in,
            r.source_url,
            r.tags
        FROM herinsights_rest.article_source
        LATERAL VIEW explode(rows) AS r''',
]

VERIFY = [
    "SELECT COUNT(*) AS tag_count FROM herinsights.tag_dictionary",
    "SELECT tag_group, COUNT(*) AS n FROM herinsights.tag_dictionary "
    "GROUP BY tag_group ORDER BY n DESC",
    "SELECT COUNT(*) AS article_count FROM herinsights.articles",
    "SELECT title, tags FROM herinsights.articles LIMIT 3",
]

if __name__ == "__main__":
    print("--- registering ---")
    for sql in STATEMENTS:
        run(sql)

    print("\n--- verifying ---")
    for sql in VERIFY:
        response = run(sql)
        print(f"      {response.text[:320]}\n")