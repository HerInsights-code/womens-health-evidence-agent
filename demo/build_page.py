"""Build the results page a judge reads, from a real pipeline run.

Tags come from a saved tagger output (real Nemotron tags), so the page
builds without Nightshift. Articles come from Zetaris, or data/articles.csv
if Zetaris is not reachable.

Usage:
    python demo/build_page.py
    python demo/build_page.py input_examples/input_example_2.json output_examples/updated_output_from_input_example_2.json
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run import run  # noqa: E402

INPUT = "input_examples/input_example_1.json"
TAGGER_OUTPUT = "output_examples/updated_output_from_input_example_1.json"
CRISIS_INPUT = "input_examples/input_example_4_crisis.json"
OUT = "demo/results.html"

# One colour per tag, used for the tag pill and the highlight in her words.
TAG_COLOURS = ["#f9d5e5", "#d7e8fa", "#fbe3c4", "#dcefd8", "#e6dcf5"]

LABELS = {
    "high": "&#10003; She said it",
    "medium": "&asymp; She said something similar",
    "low": "? The agent inferred it",
}

STYLE = """
  body { background: #fdf8ec; color: #222; font-family: system-ui, -apple-system, Arial, sans-serif; margin: 0; padding: 20px 16px; line-height: 1.6; }
  main { max-width: 720px; margin: 0 auto; }
  h1 { font-size: 26px; margin-bottom: 4px; }
  h2 { font-size: 19px; margin-top: 28px; border-top: 1px solid #ddd0b0; padding-top: 16px; }
  .note { background: #fff7d6; border: 1px solid #e6d48a; padding: 12px 14px; border-radius: 8px; font-size: 14px; }
  .answer { background: #eef6ea; border: 1px solid #b9d1a8; padding: 14px 16px; border-radius: 10px; font-size: 17px; margin: 16px 0; }
  .card { background: #fff; border: 1px solid #e2d9bd; border-radius: 10px; padding: 16px; margin: 14px 0; }
  .tag { display: inline-block; border: 1px solid rgba(0,0,0,.12); border-radius: 20px; padding: 2px 10px; margin: 2px 4px 2px 0; font-size: 14px; }
  .tag.missing { background: #f4f1ea !important; color: #888; text-decoration: line-through; }
  mark { border-radius: 4px; padding: 0 3px; color: inherit; font-style: normal; font-weight: 600; }
  .label { font-size: 14px; color: #444; margin-left: 6px; }
  .rank { font-weight: bold; color: #2f6b2f; }
  .small { font-size: 14px; color: #555; }
  blockquote { margin: 0; padding: 10px 14px; border-left: 4px solid #b9d1a8; background: #fbfaf5; font-size: 17px; }
  .steps { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 14px; margin: 12px 0; }
  .steps span { background: #fff; border: 1px solid #e2d9bd; border-radius: 20px; padding: 3px 10px; }
  .steps b { color: #b9a77a; }
  ul.tags { list-style: none; padding: 0; }
  ul.tags li { margin: 8px 0; }
  details { margin-top: 28px; border-top: 1px solid #ddd0b0; padding-top: 16px; }
  summary { font-size: 19px; font-weight: bold; cursor: pointer; }
  ol.log li { margin-bottom: 6px; }
  code { background: #f0ead6; padding: 1px 5px; border-radius: 4px; }
  a { color: #2f6b2f; }
  nav.topics { position: sticky; top: 0; z-index: 10; background: rgba(253,248,236,.96); backdrop-filter: blur(4px);
    border-bottom: 1px solid #ddd0b0; margin: 0 -16px; padding: 8px 16px; }
  nav.topics .links { display: flex; gap: 4px; overflow-x: auto; white-space: nowrap; font-size: 14px; }
  nav.topics .links a { text-decoration: none; color: #555; padding: 3px 10px; border-radius: 20px; }
  nav.topics .links a.active { background: #2f6b2f; color: #fff; }
  nav.topics .context { font-size: 13px; color: #555; margin-top: 4px; }
  nav.topics .context .tag { font-size: 12px; padding: 0 8px; }
  h2, details { scroll-margin-top: 90px; }
"""

SCROLL_SPY = """
<script>
  const links = [...document.querySelectorAll("nav.topics .links a")];
  const targets = links.map(a => document.querySelector(a.getAttribute("href")));
  function update() {
    let current = 0;
    targets.forEach((t, i) => { if (t && t.getBoundingClientRect().top < 120) current = i; });
    links.forEach((a, i) => a.classList.toggle("active", i === current));
  }
  document.querySelector('a[href="#how"]').addEventListener("click", () => { document.getElementById("how").open = true; });
  document.addEventListener("scroll", update, { passive: true });
  update();
</script>
"""


def colour_map(tags: list[str]) -> dict[str, str]:
    return {t: TAG_COLOURS[i % len(TAG_COLOURS)] for i, t in enumerate(tags)}


def pill(tag: str, colours: dict[str, str], missing: bool = False) -> str:
    cls = "tag missing" if missing else "tag"
    return f'<span class="{cls}" style="background:{colours.get(tag, "#eee")}">{escape(tag)}</span>'


def highlight(query: str, tag_evidence: list[dict], colours: dict[str, str]) -> str:
    """Her text with the words behind each tag highlighted in that tag's colour."""
    spans = []
    for e in tag_evidence:
        if e["user_phrase"]:
            for m in re.finditer(r"\b" + re.escape(e["user_phrase"]) + r"\b", query, re.IGNORECASE):
                spans.append((m.start(), m.end(), e["tag"]))
    spans.sort()

    out, pos = [], 0
    for start, end, tag in spans:
        if start < pos:
            continue
        out.append(escape(query[pos:start]))
        out.append(f'<mark style="background:{colours[tag]}" title="{escape(tag)}">{escape(query[start:end])}</mark>')
        pos = end
    out.append(escape(query[pos:]))
    return "".join(out)


def reason_html(reason: dict, colours: dict[str, str]) -> str:
    said = f'she said "{escape(reason["user_phrase"])}"' if reason["user_phrase"] else "the agent inferred it from her description"
    where = (
        f'the article mentions "{escape(reason["article_phrase"])}"'
        if reason["article_phrase"]
        else "the article is about this"
    )
    return f"<li>{pill(reason['tag'], colours)} {said}, and {where}.</li>"


def result_card(r: dict, all_tags: list[str], colours: dict[str, str]) -> str:
    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(r["rank"], f"{r['rank']}th")
    missing = [t for t in all_tags if t not in r["matched_tags"]]
    covered = " ".join(pill(t, colours) for t in r["matched_tags"])
    not_covered = " ".join(pill(t, colours, missing=True) for t in missing)
    reasons = "".join(reason_html(x, colours) for x in r["reasons"])
    link = f' <a href="{escape(r["url"])}">Read the article</a>' if r["url"] else ""
    return f"""
  <div class="card">
    <p><span class="rank">{ordinal} match</span> - {escape(r['title'])} <span class="small">({escape(str(r['year']))})</span></p>
    <p><strong>Covers {len(r['matched_tags'])} of her {len(all_tags)} concerns:</strong> {covered} {not_covered}</p>
    <p><strong>Why it matches:</strong></p>
    <ul>{reasons}</ul>
    <p class="small">Citation: {escape(r['citation'])}.{link}</p>
  </div>"""


def answer_html(results: list[dict], all_tags: list[str]) -> str:
    if not results:
        return "<strong>What we found:</strong> No research in the dataset matched her concerns yet."
    top = results[0]
    return (
        f"<strong>What we found:</strong> The best match covers {len(top['matched_tags'])} of her "
        f"{len(all_tags)} concerns ({', '.join(escape(t) for t in top['matched_tags'])}): "
        f"<em>{escape(top['title'])}</em> ({escape(str(top['year']))})."
    )


def build(input_path: str, tagger_path: str) -> str:
    query = json.loads(Path(input_path).read_text(encoding="utf-8"))["input"]["query"]
    tagger = json.loads(Path(tagger_path).read_text(encoding="utf-8"))
    out = run(query, tagger["tags"])
    crisis_query = json.loads(Path(CRISIS_INPUT).read_text(encoding="utf-8"))["input"]["query"]
    crisis = run(crisis_query, [])

    tags = out["tags"]
    colours = colour_map(tags)
    tag_list = "".join(
        f"<li>{pill(e['tag'], colours)}<span class=\"label\">{LABELS[e['confidence']]}"
        + (f' ("{escape(e["user_phrase"])}")' if e["user_phrase"] else "")
        + "</span></li>"
        for e in out["tag_evidence"]
    )
    cards = "".join(result_card(r, tags, colours) for r in out["results"]) or (
        '<div class="card">No articles shared these tags. Status: partial.</div>'
    )
    removed = "".join(
        f"<li>Result {c['rank']}: {escape(c['tag'] or '')} - {escape(c['why'])}</li>" for c in out["removed_claims"]
    ) or "<li>None. Every claim was supported.</li>"

    log = [
        f"Scout Intent read the text: intent <code>{escape(out['intent'])}</code>, "
        f"routed to the {', '.join(out['tag_groups'])} tag groups ({out['tags_considered']} tags in those groups).",
        f"Tagger (<code>{escape(tagger.get('model', 'unknown'))}</code> via Meterless Nightshift) picked "
        f"{len(tags)} tags; each was validated against the tag dictionary, {len(out['rejected'])} rejected.",
        f"Candidate articles came from <code>{escape(out['article_source'])}</code>.",
        *[escape(s) for s in out["steps"]],
    ]
    log_html = "".join(f"<li>{s}</li>" for s in log)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tagging: Match and Explain</title>
<style>{STYLE}</style>
</head>
<body>
<main>
  <h1>Tagging feature: Match and Explain</h1>
  <p class="small">Track 02, The Agent That Can Explain Why. Built from a real run on {date.today():%b %d, %Y}.</p>

  <nav class="topics">
    <div class="links">
      <a href="#wrote">What she wrote</a><a href="#concerns">Her concerns</a><a href="#research">Research and why</a><a href="#safety">Safety</a><a href="#how">How it worked</a>
    </div>
    <div class="context">Her concerns: {" ".join(pill(t, colours) for t in tags)}</div>
  </nav>

  <div class="steps">
    <span>She writes</span><b>&rarr;</b><span>Agent tags it</span><b>&rarr;</b><span>Finds research</span><b>&rarr;</b><span>Ranks it</span><b>&rarr;</b><span>Explains why</span>
  </div>

  <div class="note">
    This tool summarizes published research. It is not medical advice. If you have health concerns, talk to a
    qualified clinician. If you are in crisis, call or text 988 (US) or contact local emergency services.
  </div>

  <h2 id="wrote">1. What she wrote</h2>
  <blockquote>{highlight(query, out['tag_evidence'], colours)}</blockquote>
  <p class="small">Highlighted words are what the agent picked up. Sample input from <code>{escape(input_path)}</code>.</p>

  <div class="answer">{answer_html(out['results'], tags)}</div>

  <h2 id="concerns">2. Her concerns, and how the agent knew</h2>
  <ul class="tags">{tag_list}</ul>

  <h2 id="research">3. Matched research, and why</h2>
  <p class="small">Ranked by how many of her concerns each article covers, then concerns she named in her own
  words, then research grade when available, then newest.</p>
  {cards}

  <h2 id="safety">4. Safety path</h2>
  <div class="card">
    <blockquote>{escape(crisis_query)}</blockquote>
    <p><strong>Result:</strong> no research shown. The agent recognised a possible crisis and points to
    support instead (988 in the US). <span class="small">Status <code>{escape(crisis['status'])}</code>.</span></p>
  </div>

  <details id="how">
    <summary>How the agent got here (run log and evidence check)</summary>
    <ol class="log">{log_html}</ol>
    <p><strong>Evidence check.</strong> Before showing results, the agent removes any quoted phrase not in her
    text and any tag not on the article.</p>
    <ul>{removed}</ul>
  </details>
</main>
{SCROLL_SPY}
</body>
</html>
"""


def main() -> None:
    input_path = sys.argv[1] if len(sys.argv) > 1 else INPUT
    tagger_path = sys.argv[2] if len(sys.argv) > 2 else TAGGER_OUTPUT
    Path(OUT).write_text(build(input_path, tagger_path), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
