"""Match and explain: rank articles against a person's tags, explain each
match in plain language, and run the evidence check (feedback loop 3).

Pure logic, no network calls. Articles come from data/articles.csv until
the Zetaris adapter is wired in.
"""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

TOP_N = 3


def load_articles(path: str = "data/articles.csv") -> list[dict]:
    """Read the article file into a list of dicts."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def tag_terms(tag: str, synonyms: dict) -> list[str]:
    """The tag itself plus every synonym that maps to it."""
    return [tag] + [phrase for phrase, canonical in synonyms.items() if canonical == tag]


def find_phrase(text: str, phrases: list[str]) -> str | None:
    """Return the first phrase that appears in text as whole words, as written in text."""
    for phrase in phrases:
        match = re.search(r"\b" + re.escape(phrase) + r"\b", text, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def article_tag_evidence(article: dict, tags: list[str], synonyms: dict) -> dict[str, dict]:
    """For each person tag, how the article supports it.

    A tag is on the article if the article's own tag field carries it
    (after synonym mapping), or the title or summary mentions it.
    """
    own_tags = {
        synonyms.get(t.strip().lower(), t.strip().lower())
        for t in re.split(r"[;|]", article.get("tags") or "")
        if t.strip()
    }
    text = f"{article.get('title', '')} {article.get('summary', '')}"

    evidence: dict[str, dict] = {}
    for tag in tags:
        if tag in own_tags:
            evidence[tag] = {"source": "article tag", "phrase": None}
            continue
        phrase = find_phrase(text, tag_terms(tag, synonyms))
        if phrase:
            evidence[tag] = {"source": "article text", "phrase": phrase}
    return evidence


def _grade_key(article: dict) -> tuple[float, int]:
    """Tie-breaker: PP's relevance score when graded, then publication year."""
    try:
        relevance = float(article.get("relevance_score") or 0)
    except ValueError:
        relevance = 0.0
    try:
        year = int(article.get("published_year") or 0)
    except ValueError:
        year = 0
    return relevance, year


CONFIDENCE_WEIGHT = {"high": 3, "medium": 2, "low": 1}


def rank_articles(
    tags: list[str],
    articles: list[dict],
    synonyms: dict,
    top_n: int = TOP_N,
    weights: dict[str, int] | None = None,
) -> tuple[list[dict], int]:
    """Score articles by tag overlap, break ties by grade, return (top matches, candidates considered).

    Ties on overlap go first to tags she stated outright (weights), then to
    the grade. Each match is {"article", "evidence", "score"}. Articles that
    share no tags are left out.
    """
    weights = weights or {}
    scored = []
    for article in articles:
        evidence = article_tag_evidence(article, tags, synonyms)
        if evidence:
            scored.append({
                "article": article,
                "evidence": evidence,
                "score": len(evidence),
                "weight": sum(weights.get(t, 1) for t in evidence),
            })

    scored.sort(key=lambda m: (m["score"], m["weight"], *_grade_key(m["article"])), reverse=True)
    log.info("matched %d of %d articles, keeping top %d", len(scored), len(articles), top_n)
    return scored[:top_n], len(scored)


def user_phrases(query: str, tags: list[str], synonyms: dict) -> dict[str, str | None]:
    """The words in the person's own text behind each tag, or None if none were found."""
    return {tag: find_phrase(query, tag_terms(tag, synonyms)) for tag in tags}


def tag_confidence(tag: str, phrase: str | None) -> str:
    """high: her words name the tag; medium: a known synonym; low: the model inferred it."""
    if phrase is None:
        return "low"
    return "high" if phrase.lower() == tag else "medium"


def explain_match(match: dict, rank: int, phrases: dict[str, str | None], all_tags: list[str]) -> dict:
    """Plain-language explanation and citation for one ranked match."""
    article = match["article"]
    evidence = match["evidence"]
    matched = list(evidence)
    missing = [t for t in all_tags if t not in evidence]

    reasons = []
    for tag in matched:
        said = phrases.get(tag)
        you = f'you said "{said}"' if said else "the tagger picked this from your description"
        found = evidence[tag]
        where = (
            "the article is tagged with it"
            if found["source"] == "article tag"
            else f'the article mentions "{found["phrase"]}"'
        )
        reasons.append({"tag": tag, "user_phrase": said, "article_phrase": found["phrase"], "text": f"{tag}: {you}, and {where}."})

    why = f"Shares {len(matched)} of your {len(all_tags)} tags ({', '.join(matched)})."
    if missing:
        why += f" It does not cover {', '.join(missing)}."

    doi = article.get("doi", "").strip()
    citation = f"{article.get('title', '').strip()} ({article.get('published_year', '')}). {article.get('found_in', '')}."
    if doi:
        citation += f" doi:{doi}"

    return {
        "rank": rank,
        "title": article.get("title", "").strip(),
        "year": article.get("published_year", ""),
        "matched_tags": matched,
        "why": why,
        "reasons": reasons,
        "citation": citation,
        "url": article.get("source_url", ""),
        "doi": doi,
    }


def evidence_check(results: list[dict], query: str, matches: list[dict]) -> tuple[list[dict], list[dict]]:
    """Feedback loop 3: remove any claim the inputs do not support.

    A cited user phrase must appear in the query, and every matched tag must
    be on the article. Results left with no supported tags are dropped.
    Returns (checked results, removed claims).
    """
    removed: list[dict] = []
    checked: list[dict] = []
    lowered = query.lower()

    for result, match in zip(results, matches):
        kept = []
        for reason in result["reasons"]:
            if reason["tag"] not in match["evidence"]:
                removed.append({"rank": result["rank"], "tag": reason["tag"], "why": "tag not on article"})
                continue
            if reason["user_phrase"] and reason["user_phrase"].lower() not in lowered:
                removed.append({"rank": result["rank"], "tag": reason["tag"], "why": "cited phrase not in user text"})
                reason = {**reason, "user_phrase": None}
            kept.append(reason)

        if not kept:
            removed.append({"rank": result["rank"], "tag": None, "why": "no supported tags left, result dropped"})
            continue
        checked.append({**result, "reasons": kept, "matched_tags": [r["tag"] for r in kept]})

    for claim in removed:
        log.info("evidence check removed: %s", claim)
    return checked, removed


def match_and_explain(query: str, tags: list[str], articles: list[dict], synonyms: dict) -> dict:
    """Rank, explain, and evidence-check. Returns results plus a step log."""
    steps = []
    phrases = user_phrases(query, tags, synonyms)
    weights = {t: CONFIDENCE_WEIGHT[tag_confidence(t, p)] for t, p in phrases.items()}

    matches, considered = rank_articles(tags, articles, synonyms, weights=weights)
    steps.append(f"Compared {len(tags)} tags against {len(articles)} articles; {considered} shared at least one tag.")
    steps.append(
        "Ranked by number of shared tags, then tags stated in her own words over inferred ones, "
        "then relevance score if graded, then newest year."
    )

    results = [explain_match(m, i + 1, phrases, tags) for i, m in enumerate(matches)]
    steps.append(f"Wrote an explanation and citation for the top {len(results)}.")

    results, removed = evidence_check(results, query, matches)
    steps.append(f"Evidence check: {len(removed)} unsupported claims removed.")

    return {
        "tag_evidence": [
            {"tag": t, "user_phrase": p, "confidence": tag_confidence(t, p)} for t, p in phrases.items()
        ],
        "results": results,
        "articles_considered": considered,
        "removed_claims": removed,
        "steps": steps,
    }
