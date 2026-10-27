"""Agent loop: Scout Intent, tagging with retry, matching with retry, explain.

Each step reads and writes one state dict. Every retry is capped at one
attempt and recorded with its reason in state["retries"] and state["steps"].
"""

from __future__ import annotations

import logging
import sys

from app.engines.scout_intent import ScoutIntent
from app.explain import load_articles, match_with_retry
from app.tagging import load_dictionary, load_synonyms, tag_paragraph, validate_tags

log = logging.getLogger(__name__)

CANDIDATE_LIMIT = 20


def fetch_candidates(tags: list[str]) -> tuple[list[dict], str]:
    """Articles sharing any tag, from Zetaris, or the local file if Zetaris is down."""
    try:
        from app.adapters import zetaris
        return zetaris.find_articles(tags, limit=CANDIDATE_LIMIT), "zetaris"
    except Exception as error:
        print(f"[warn] Zetaris match failed: {type(error).__name__}, using data/articles.csv", file=sys.stderr)
        return load_articles(), "data/articles.csv"


def tag_with_retry(query: str, candidates: set[str], dictionary: set[str], synonyms: dict, state: dict) -> None:
    """Tagging feedback loop: if no tag survives validation, retry once with the full dictionary.

    Writes tags, rejected and model into state. A tagger failure (Nightshift
    down, bad reply) is recorded and leaves tags empty rather than crashing.
    """
    attempts = [("tag groups from Scout Intent", candidates), ("full tag dictionary", dictionary)]
    state["rejected"] = []

    for i, (label, allowed) in enumerate(attempts):
        try:
            raw, model = tag_paragraph(query, allowed)
        except Exception as error:
            state["steps"].append(f"Tagger call failed ({type(error).__name__}); no tags.")
            state["tags"], state["model"] = [], None
            return

        tags, rejected = validate_tags(raw, dictionary, synonyms)
        state["model"] = model
        state["rejected"] += rejected
        state["steps"].append(
            f"Tagging attempt {i + 1} ({label}, {len(allowed)} tags): "
            f"{len(tags)} valid, {len(rejected)} rejected{' (' + ', '.join(map(str, rejected)) + ')' if rejected else ''}."
        )
        if tags:
            state["tags"] = tags
            return
        if i == 0:
            reason = "no valid tags from the routed groups; retrying once with the full dictionary"
            state["retries"].append({"step": "tagging", "reason": reason})
            log.info("tagger retry: %s", reason)

    state["tags"] = []


def run_agent(query: str, given_tags: list[str] | None = None, fetch=fetch_candidates) -> dict:
    """Run the full agent on one paragraph. given_tags skips the model call."""
    decision = ScoutIntent().decide(query, surface="api")

    if decision.risk.level == "block":
        return {
            "status": "blocked",
            "reason": decision.risk.reason,
            "flags": decision.risk.flags,
            "trace_id": decision.trace_id,
        }

    if decision.clarification:
        return {
            "status": "needs_clarification",
            "question": decision.clarification.question,
            "options": decision.clarification.options,
            "trigger": decision.clarification.trigger,
            "trace_id": decision.trace_id,
        }

    dictionary, groups = load_dictionary()
    synonyms = load_synonyms()
    candidates = {tag for g in decision.tag_groups for tag in groups.get(g, [])}
    state: dict = {"steps": [], "retries": []}

    if given_tags is None:
        tag_with_retry(query, candidates, dictionary, synonyms, state)
    else:
        state["tags"], state["rejected"] = validate_tags(given_tags, dictionary, synonyms)
        state["model"] = "none (tags given with --tags)"
        state["steps"].append(f"Tags given directly: {len(state['tags'])} valid, {len(state['rejected'])} rejected.")

    tags = state["tags"]
    if not tags:
        return {
            "status": "partial",
            "reason": "no valid tags after retry",
            "intent": decision.primary,
            "tag_groups": decision.tag_groups,
            "tags": [],
            "rejected": state["rejected"],
            "matches": [],
            "results": [],
            "steps": state["steps"],
            "retries": state["retries"],
            "model": state["model"],
            "trace_id": decision.trace_id,
            "contract_id": decision.contract["contractId"],
        }

    sources: list[str] = []

    def fetch_and_record(search_tags: list[str]) -> list[dict]:
        articles, source = fetch(search_tags)
        sources.append(source)
        return articles

    matched = match_with_retry(query, tags, fetch_and_record, synonyms, groups)

    return {
        "status": "success" if matched["results"] else "partial",
        "intent": decision.primary,
        "confidence": decision.confidence,
        "tag_groups": decision.tag_groups,
        "tags_considered": len(candidates),
        "tags": tags,
        "rejected": state["rejected"],
        "article_source": sources[-1] if sources else None,
        "matches": matched["results"],
        **matched,
        "steps": state["steps"] + matched["steps"],
        "retries": state["retries"] + matched["retries"],
        "model": state["model"],
        "trace_id": decision.trace_id,
        "contract_id": decision.contract["contractId"],
    }
