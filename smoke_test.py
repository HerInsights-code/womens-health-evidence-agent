#!/usr/bin/env python3
"""Smoke checks for the Data (Zetaris) and Power (Meterless) layers."""

from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

TIMEOUT_SECONDS = 30
ERROR_LIMIT = 150
SECRET_ENV_KEYS = (
    "ZETARIS_API_KEY",
    "METERLESS_RUNTIME_TOKEN",
)


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing {name}")
    return value


def redact(text: str) -> str:
    for key in SECRET_ENV_KEYS:
        secret = os.environ.get(key, "").strip()
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


def truncate(text: str) -> str:
    text = redact(text).replace("\n", " ").strip()
    if len(text) <= ERROR_LIMIT:
        return text
    return text[:ERROR_LIMIT]


def join_url(base: str, path: str) -> str:
    return base.rstrip("/") + path


def request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, bytes]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            payload = response.read()
    except HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {truncate(err_body)}") from exc
    except URLError as exc:
        raise RuntimeError(str(exc.reason or exc)) from exc

    if status < 200 or status >= 300:
        raise RuntimeError(f"HTTP {status} {truncate(payload.decode('utf-8', errors='replace'))}")
    return status, payload


def check_zetaris_web() -> str:
    request("GET", "http://localhost:3000")
    return "Data: Zetaris web"


def check_zetaris_sql() -> str:
    url = join_url(env("ZETARIS_REST_URL"), "/sql-editor/sqls/run")
    headers = {
        "Authorization": f"Bearer {env('ZETARIS_API_KEY')}",
        "X-Org-ID": env("ZETARIS_ORG_ID"),
        "X-Request-ID": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }
    body = {
        "queryId": str(uuid.uuid4()),
        "sql": "SELECT 1",
        "source": "SqlEditor",
        "limit": 1,
    }
    _, payload = request("POST", url, headers=headers, body=body)
    parsed = json.loads(payload.decode("utf-8"))
    try:
        cell = parsed["data"][0][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("response JSON missing data[0][0]") from exc
    if cell != "1":
        raise RuntimeError(f'data[0][0] != "1" (got {cell!r})')
    return "Data: SQL run"


def check_meterless() -> str:
    url = join_url(env("METERLESS_BASE_URL"), "/chat/completions")
    headers = {
        "Authorization": f"Bearer {env('METERLESS_RUNTIME_TOKEN')}",
        "meterless-app": "womens-health-evidence-agent",
        "meterless-scope": "user",
        "Content-Type": "application/json",
    }
    body = {
        "model": env("METERLESS_MODEL"),
        "messages": [
            {"role": "user", "content": "Reply with the single word ready."},
        ],
    }
    _, payload = request("POST", url, headers=headers, body=body)
    parsed = json.loads(payload.decode("utf-8"))
    try:
        reply = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("response JSON missing choices[0].message.content") from exc
    if not str(reply).strip():
        raise RuntimeError("empty reply")
    routed = parsed.get("meterless") or {}
    routed_model = routed.get("routed_model") if isinstance(routed, dict) else None
    if not routed_model:
        routed_model = "unknown"
    return f"Power: chat completions (routed_model={routed_model})"


CHECKS = (
    ("Data: Zetaris web", check_zetaris_web),
    ("Data: SQL run", check_zetaris_sql),
    ("Power: chat completions", check_meterless),
)


def main() -> int:
    load_dotenv()
    failed = False
    for label, check in CHECKS:
        try:
            print(f"PASS {check()}")
        except Exception as exc:
            failed = True
            print(f"FAIL {label} — {truncate(str(exc))}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
