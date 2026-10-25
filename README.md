# Women's Health Evidence Agent

An agent that takes a woman's own words about what she's experiencing, turns them into clean tags, explains why it picked each tag, and shows matching research with the reason for each match.

**Team:** HerInsights
**Track:** 02, The Agent That Can Explain Why

> This tool summarizes published research. It is not medical advice. If you have health concerns, talk to a qualified clinician. If you are in crisis, call or text 988 (US) or contact local emergency services.

## Team and ownership

| Member | Owns |
|---|---|
| Supra | `app/tagging.py`, `app/engines/scout_intent.py`, `app/adapters/nightshift.py` |
| PP | `app/matching.py`, `scripts/`, `data/`, matcher tests |
| Nima | `app/explain.py`, `run.py`, demo |
| Shared | `app/main.py`, `app/adapters/zetaris.py`, `README.md` |

## How it works

1. A user's paragraph goes into the agent, which creates a run ID and a state object that every step reads and writes.
2. **Tagging:** Scout Intent (a Meterless engine) routes the paragraph to tag groups, then Nemotron, through Meterless Nightshift, picks tags from the dictionary.
3. **Feedback loop 1, tag validation:** each tag is checked against the dictionary, and synonyms are merged. If no valid tags remain, the tagger retries once with the group hints spelled out. If it still returns nothing, the run ends with `status: partial`.
4. **Matching:** the matcher queries Zetaris for articles that share those tags and returns the top 3.
5. **Feedback loop 2, matcher retry:** if nothing matches, the least important tag is dropped and the search runs once more.
6. **Explanations:** the explain layer shows the words behind each tag, a confidence level, and the alternatives considered.
7. **Feedback loop 3, evidence check:** every cited phrase must appear in the paragraph, and every tag must be on the matched article. Claims that fail are removed before the output is returned.
8. Every step, retry, and removed claim is written to the run's trace log.

## Architecture

- **Agent loop:** `app/main.py` runs the steps and the three feedback loops, with a retry limit on each.
- **Data layer:** Zetaris holds the article records and the tag dictionary.
- **Engine:** Scout Intent (Meterless), in the tagging step. Test: `tests/test_scout_intent.py`.
- **Primary AI provider:** Meterless Nightshift, with NVIDIA Nemotron models.
- **Tests:** `tests/test_loop.py` checks the validation, the evidence check, and the partial-result path.

## Folder structure

```
womens-health-evidence-agent/
├── app/
│   ├── __init__.py
│   ├── main.py            # agent loop and feedback loops (shared)
│   ├── tagging.py         # tagger and tag validation (Supra)
│   ├── matching.py        # matcher and matcher retry (PP)
│   ├── explain.py         # explanations and evidence check (Nima)
│   ├── adapters/
│   │   ├── zetaris.py     # data layer (shared)
│   │   └── nightshift.py  # model calls (Supra)
│   └── engines/
│       └── scout_intent.py  # Meterless engine (Supra)
├── data/                  # tag dictionary and article file (PP)
├── scripts/               # ingestion scripts (PP)
├── tests/                 # loop tests, matcher tests, engine test
├── input_examples/        # sample inputs
├── output_examples/       # matching outputs
├── logs/                  # run traces
├── run.py                 # entry point (Nima)
├── requirements.txt
├── Dockerfile
├── .env.example
├── .gitignore
└── README.md
```

## Data sources

| Source | What we used | Licence | How to regenerate |
|---|---|---|---|
| PubMed | <search terms, date range> | <licence> | `python scripts/<script>.py` |
| Europe PMC | <search terms, date range> | <licence> | `python scripts/<script>.py` |
| Semantic Scholar | <search terms, date range> | <licence> | `python scripts/<script>.py` |

The article file in `data/` has <N> records, deduplicated by DOI. The tag dictionary (`data/tag_dictionary.json`) was written by hand by <name> and has <N> tags.

## Setup

**Requirements:** Docker Desktop, Zetaris running locally, Meterless Nightshift running, and your NVIDIA key added in Nightshift's Providers tab.

```bash
git clone https://github.com/HerInsights-code/womens-health-evidence-agent.git
cd womens-health-evidence-agent
cp .env.example .env   # fill in your Zetaris and Nightshift values
```

Never commit `.env`. The NVIDIA key goes in Nightshift, not in the app.

## Usage

```bash
docker build -t oah-submission .
docker run --rm -p 8000:8000 --env-file .env oah-submission
```

Send a request:

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d @input_examples/example_1.json
```

Sample inputs and outputs are in `input_examples/` and `output_examples/`.

## Sample mode

Set `SAMPLE_MODE=true` to use saved outputs, without Zetaris, Nightshift, or network access.

## Logs

Each run writes to stdout and to `logs/trace-<run_id>.jsonl`. The logs show each step, every retry and why it happened, every removed claim, the Zetaris queries, the Meterless engine activity, and which model handled each request. Sample traces are in `logs/`.

## Sponsor technology

- **Zetaris:** The data layer. The article records (from PubMed, Europe PMC, and Semantic Scholar) and the tag dictionary are stored as Zetaris tables. The matcher queries them with SQL through Zetaris's REST API to find articles that share tags with a user's input.
- **Meterless Engine (Scout Intent):** Runs in the tagging step. It routes each paragraph to tag groups (sleep, cycle, mood, body) before the tagger picks specific tags. Test: `tests/test_scout_intent.py`. Result: <pass/fail, date>.
- **Meterless Nightshift:** The primary AI provider. The tagger, and the explain layer if it calls a model, send requests to Nightshift's OpenAI-compatible endpoint using the Runtime URL and token from `.env`. The logs show which model handled each request.
- **NVIDIA:** Nemotron models, served through Nightshift, do the tagging. The model used is <model name from the trace logs>.

## Limitations

- Results depend on the articles in the dataset, which is a small sample of <N> records.
- The tag dictionary covers <N> topics and will miss anything outside it.
- Feedback loops are capped at fixed retry counts, so some inputs will return a partial result.
- Summaries describe published research and do not replace clinical judgment.