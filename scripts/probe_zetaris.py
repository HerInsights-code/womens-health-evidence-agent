"""Find out what SQL this Zetaris install accepts, so we know how to load data."""

import json
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


def run(sql: str):
    body = {
        "queryId": str(uuid.uuid4()),
        "sql": sql,
        "source": "SqlEditor",
        "limit": 50,
    }
    headers = {**HEADERS, "X-Request-ID": str(uuid.uuid4())}
    try:
        response = requests.post(URL, headers=headers, json=body, timeout=60)
        ok = response.status_code == 200
        return ok, response.text[:300]
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"


""" PROBES = [
    ("A1 create db plain", "CREATE LIGHTNING DATABASE herinsights"),
    ("A2 show dbs", "SHOW LIGHTNING DATABASES"),

    ("B1 create schemastore", "CREATE SCHEMASTORE CONTAINER herinsights"),
    ("B2 show schemastore", "SHOW SCHEMASTORE CONTAINERS"),

    ("C1 show namespaces", "SHOW NAMESPACES"),
    ("C2 current schema", "SELECT current_schema()"),
    ("C3 show tables", "SHOW TABLES"),

    ("D1 create table bare", "CREATE TABLE tag_dictionary (tag STRING, tag_group STRING)"),
    ("D2 insert bare", "INSERT INTO tag_dictionary VALUES ('bad sleep', 'sleep')"),
    ("D3 select bare", "SELECT * FROM tag_dictionary"),

    ("E1 create in container", "CREATE TABLE herinsights.tag_dictionary (tag STRING, tag_group STRING)"),
    ("E2 insert in container", "INSERT INTO herinsights.tag_dictionary VALUES ('bad sleep', 'sleep')"),
    ("E3 select in container", "SELECT * FROM herinsights.tag_dictionary"),

    ("F1 select literal", "SELECT 'bad sleep' AS tag, 'sleep' AS tag_group"),
] """



PROBES = [
    ("G1 tables in container", "SHOW TABLES IN herinsights"),

    ("H1 view qualified", """CREATE SCHEMASTORE VIEW herinsights.tag_dictionary AS
        SELECT 'bad sleep' AS tag, 'sleep' AS tag_group
        UNION ALL SELECT 'tired all day', 'sleep'
        UNION ALL SELECT 'heavy periods', 'cycle'"""),
    ("H2 select it", "SELECT * FROM herinsights.tag_dictionary"),

    ("I1 view bare", """CREATE SCHEMASTORE VIEW tag_dictionary_2 AS
        SELECT 'bad sleep' AS tag, 'sleep' AS tag_group"""),
    ("I2 select bare", "SELECT * FROM tag_dictionary_2"),
    ("I3 select via container", "SELECT * FROM herinsights.tag_dictionary_2"),

    ("J1 tables in container again", "SHOW TABLES IN herinsights"),
]


for name, sql in PROBES:
    ok, detail = run(sql)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"      {detail}\n")