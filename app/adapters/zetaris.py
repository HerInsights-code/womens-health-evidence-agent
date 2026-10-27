"""Zetaris as the data layer. SQL over its REST API."""

from __future__ import annotations

import os
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

TIMEOUT = 60


def _url() -> str:
    return os.environ["ZETARIS_REST_URL"].rstrip("/") + "/sql-editor/sqls/run"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['ZETARIS_API_KEY']}",
        "X-Org-ID": os.environ["ZETARIS_ORG_ID"],
        "X-Request-ID": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


def run_sql(sql: str, limit: int = 500) -> list[dict]:
    """Run one SQL statement. Returns rows as dicts."""
    body = {
        "queryId": str(uuid.uuid4()),
        "sql": sql.strip(),
        "source": "SqlEditor",
        "limit": limit,
    }
    response = requests.post(_url(), headers=_headers(), json=body, timeout=TIMEOUT)
    response.raise_for_status()
    payload = response.json()

    if "msg" in payload:
        raise RuntimeError(f"Zetaris error: {payload['msg'][:200]}")

    headers = payload.get("headers", [])
    return [dict(zip(headers, row)) for row in payload.get("data", [])]


def load_tag_dictionary() -> tuple[set[str], dict[str, list[str]]]:
    """Read the tag dictionary from Zetaris. Returns (flat set, groups)."""
    rows = run_sql("SELECT tag, tag_group FROM herinsights.tag_dictionary")
    groups: dict[str, list[str]] = {}
    for row in rows:
        groups.setdefault(row["tag_group"], []).append(row["tag"])
    return {row["tag"] for row in rows}, groups


def find_articles(tags: list[str], limit: int = 5) -> list[dict]:
    """Articles sharing any of these tags, most overlap first."""
    if not tags:
        return []
    conditions = " OR ".join(
        f"tags LIKE '%{t.replace(chr(39), chr(39) * 2)}%'" for t in tags
    )
    scores = " + ".join(
        f"(CASE WHEN tags LIKE '%{t.replace(chr(39), chr(39) * 2)}%' THEN 1 ELSE 0 END)"
        for t in tags
    )
    return run_sql(
        f"""SELECT title, tags, source_url, published_year, found_in,
                   ({scores}) AS shared
            FROM herinsights.articles
            WHERE {conditions}
            ORDER BY shared DESC
            LIMIT {limit}"""
    )


def status() -> bool:
    try:
        run_sql("SELECT 1", limit=1)
        return True
    except Exception:
        return False