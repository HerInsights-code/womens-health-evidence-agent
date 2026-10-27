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

STYLE = """
  body { background: #fdf8ec; color: #222; font-family: system-ui, -apple-system, Arial, sans-serif; margin: 0; padding: 20px 16px; line-height: 1.6; }
  main { max-width: 720px; margin: 0 auto; }
  h1 { font-size: 26px; margin-bottom: 4px; }
  h2 { font-size: 19px; margin-top: 28px; border-top: 1px solid #ddd0b0; padding-top: 16px; }
  .note { background: #fff7d6; border: 1px solid #e6d48a; padding: 12px 14px; border-radius: 8px; }
  .card { background: #fff; border: 1px solid #e2d9bd; border-radius: 10px; padding: 16px; margin: 14px 0; }
  .tag { display: inline-block; background: #eaf2e3; border: 1px solid #b9d1a8; border-radius: 20px; padding: 2px 10px; margin: 2px 4px 2px 0; font-size: 14px; }
  .tag.missing { background: #f4f1ea; border-color: #d8d0bd; color: #777; }
  .conf { font-size: 12px; color: #555; margin-left: 4px; }
  .rank { font-weight: bold; color: #2f6b2f; }
  .small { font-size: 14px; color: #555; }
  blockquote { margin: 0; padding: 8px 14px; border-left: 4px solid #b9d1a8; background: #fbfaf5; font-style: italic; }
  ol.log li { margin-bottom: 6px; }
  code { background: #f0ead6; padding: 1px 5px; border-radius: 4px; }
  a { color: #2f6b2f; }
"""


def tags_html(tags, missing=()):
    return " ".join(
        f'<span class="tag{" missing" if t in missing else ""}">{escape(t)}</span>' for t in tags
    )


def result_card(r: dict, all_tags: list[str]) -> str:
    ordinal = {1: "1st", 2: "2nd", 3: "3rd"}.get(r["rank"], f"{r['rank']}th")
    missing = [t for t in all_tags if t not in r["matched_tags"]]
    reasons = "".join(f"<li>{escape(x['text'])}</li>" for x in r["reasons"])
    link = f' <a href="{escape(r["url"])}">Read the article</a>' if r["url"] else ""
    return f"""
  <div class="card">
    <p><span class="rank">{ordinal} match</span> - {escape(r['title'])} <span class="small">({escape(str(r['year']))})</span></p>
    <p><strong>Matches your tags:</strong> {tags_html(r['matched_tags'])}
       {('<br><strong>Does not cover:</strong> ' + tags_html(missing, missing)) if missing else ''}</p>
    <p><strong>Why it matches:</strong> {escape(r['why'])}</p>
    <ul>{reasons}</ul>
    <p class="small">Citation: {escape(r['citation'])}.{link}</p>
  </div>"""


def build(input_path: str, tagger_path: str) -> str:
    query = json.loads(Path(input_path).read_text(encoding="utf-8"))["input"]["query"]
    tagger = json.loads(Path(tagger_path).read_text(encoding="utf-8"))
    out = run(query, tagger["tags"])
    crisis_query = json.loads(Path(CRISIS_INPUT).read_text(encoding="utf-8"))["input"]["query"]
    crisis = run(crisis_query, [])

    tags = out["tags"]
    evidence = "".join(
        f"<li>{tags_html([e['tag']])}<span class=\"conf\">{e['confidence']} confidence</span> - "
        + (f"from your words \"{escape(e['user_phrase'])}\"" if e["user_phrase"]
           else "inferred by the tagger; no exact phrase in your text")
        + "</li>"
        for e in out["tag_evidence"]
    )
    cards = "".join(result_card(r, tags) for r in out["results"]) or (
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
        "Safety check: a crisis message is routed to support before any research is shown (see below).",
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

  <div class="note">
    This tool summarizes published research. It is not medical advice. If you have health concerns, talk to a
    qualified clinician. If you are in crisis, call or text 988 (US) or contact local emergency services.
  </div>

  <h2>1. What she wrote</h2>
  <div class="card">
    <blockquote>{escape(query)}</blockquote>
    <p class="small">Sample input from <code>{escape(input_path)}</code>.</p>
  </div>

  <h2>2. Her tags, and why each was chosen</h2>
  <div class="card"><ul>{evidence}</ul></div>

  <h2>3. Matched research</h2>
  <p class="small">Ranked by how many of her tags each article shares, then tags she stated in her own words,
  then research grade when available, then newest.</p>
  {cards}

  <h2>4. Evidence check</h2>
  <div class="card">
    <p>Before showing results, the agent removes any quoted phrase not in her text and any tag not on the article.</p>
    <ul>{removed}</ul>
  </div>

  <h2>5. Run log (how the agent reached this)</h2>
  <ol class="log">{log_html}</ol>

  <h2>6. Safety path</h2>
  <div class="card">
    <blockquote>{escape(crisis_query)}</blockquote>
    <p><strong>Status:</strong> <code>{escape(crisis['status'])}</code> - {escape(crisis.get('reason', ''))}.
    No research is shown; the person is pointed to support (988 in the US).</p>
  </div>
</main>
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
