"""Meterless Runtime as an OpenAI-compatible provider.

Not implemented: Auto Detect port scanning, connect-link parsing,
media and 3D routes, streaming.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

APP_ID = "womens-health-evidence-agent"
PLACEHOLDER_TOKEN = "rt-local"
STATUS_TIMEOUT_SECONDS = 10
CHAT_TIMEOUT_SECONDS = 180


def normalize_base_url(url: str) -> str:
    """Normalise a pasted Meterless URL to <scheme>://<host>[:port]/v1."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("missing METERLESS_BASE_URL")
    raw = raw.split("#", 1)[0].strip()
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    if not parsed.netloc:
        raise ValueError("invalid METERLESS_BASE_URL")
    path = (parsed.path or "").rstrip("/")
    lowered = path.lower()
    for suffix in ("/chat/completions", "/models", "/healthz"):
        if lowered.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            lowered = path.lower()
            break
    parts = [part for part in path.split("/") if part]
    while parts and parts[-1].lower() == "v1":
        parts.pop()
    parts.append("v1")
    return f"{parsed.scheme}://{parsed.netloc}/{'/'.join(parts)}"


def _redact(text: str) -> str:
    token = os.environ.get("METERLESS_RUNTIME_TOKEN", "").strip()
    if token and token != PLACEHOLDER_TOKEN:
        text = text.replace(token, "[redacted]")
    return text


def _token() -> str:
    load_dotenv()
    token = os.environ.get("METERLESS_RUNTIME_TOKEN", "").strip()
    if not token or token == PLACEHOLDER_TOKEN:
        raise ValueError("placeholder token rt-local is rejected")
    return token


def _base_url() -> str:
    load_dotenv()
    return normalize_base_url(os.environ.get("METERLESS_BASE_URL", ""))


def _headers(*, chat: bool = False) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {_token()}",
        "meterless-app": APP_ID,
    }
    if chat:
        headers["meterless-scope"] = "user"
        headers["Content-Type"] = "application/json"
    return headers


def _has_meterless_ids(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    models = payload.get("data")
    if not isinstance(models, list):
        return False
    for item in models:
        if isinstance(item, dict) and str(item.get("id", "")).startswith("meterless/"):
            return True
        if isinstance(item, str) and item.startswith("meterless/"):
            return True
    return False


def _reply_text(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("response missing choices[0].message.content") from exc
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
        content = "".join(parts)
    text = "" if content is None else str(content).strip()
    if not text:
        raise RuntimeError("empty reply")
    return text


def status() -> str:
    """Return online, unauthorized, or offline from GET /v1/models."""
    try:
        url = _base_url() + "/models"
        response = requests.get(
            url, headers=_headers(), timeout=STATUS_TIMEOUT_SECONDS
        )
    except ValueError:
        raise
    except requests.RequestException:
        return "offline"
    if response.status_code in (401, 403):
        return "unauthorized"
    if response.status_code == 200:
        try:
            payload = response.json()
        except ValueError:
            return "offline"
        if _has_meterless_ids(payload):
            return "online"
    return "offline"


def chat(messages, model=None) -> tuple[str, str]:
    """POST /v1/chat/completions. Returns (reply_text, routed_model)."""
    load_dotenv()
    if model is None:
        model = os.environ.get("METERLESS_MODEL", "").strip()
    if not model:
        raise ValueError("missing METERLESS_MODEL")
    url = _base_url() + "/chat/completions"
    body = {"model": model, "messages": messages}
    try:
        response = requests.post(
            url,
            headers=_headers(chat=True),
            json=body,
            timeout=CHAT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        snippet = _redact((exc.response.text if exc.response is not None else str(exc))[:150])
        raise RuntimeError(f"HTTP {exc.response.status_code if exc.response is not None else '?'} {snippet}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(_redact(str(exc))) from exc
    except ValueError as exc:
        if str(exc).startswith("placeholder"):
            raise
        raise RuntimeError("response was not JSON") from exc

    reply = _reply_text(payload)
    meterless = payload.get("meterless") if isinstance(payload, dict) else None
    routed = None
    if isinstance(meterless, dict):
        routed = meterless.get("routed_model")
    return reply, routed or "unknown"
