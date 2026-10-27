# Women's Health Evidence Agent

A woman writes what she is experiencing in her own words. The agent works out
what she is describing, tags it against a fixed vocabulary, and returns the
research that matches — with the tags behind every match.

The gap it closes: research is catalogued by condition, but women experience
symptoms. If you have to know you have PCOS before you can find PCOS research,
the evidence is unreachable for the people who need it most. This agent indexes
the research by lived experience instead.

**Team:** HerInsights
**Track:** 02 — The Agent That Can Explain Why

> This tool surfaces published research. It is not medical advice and not a
> diagnosis. If you have health concerns, talk to a qualified clinician. If you
> are in crisis, call or text 988 (US) or contact local emergency services.

## What it does

```bash
python run.py input_examples/input_example_1.json
```

Input: *"I've had really heavy periods for about six months, I'm exhausted all
the time no matter how much I sleep, and my skin keeps breaking out."*

Output: tags `heavy periods`, `tired all day`, `skin changes`, and the top three
papers, each with a plain-language reason it matches. The first covers two of
her three concerns — heavy menstrual bleeding, iron deficiency and iron
deficiency anemia — and says why:

> heavy periods: she said "heavy periods", and the article mentions "heavy menstrual bleeding".
> tired all day: she said "exhausted", and the article is about this.

She never typed "anaemia."

## How it works

1. **Scout Intent** (the Meterless Engine) reads the paragraph before any model
   call. A deterministic trigger scan over the intent registry scores each tag
   group, and the paragraph is routed to the groups above the confidence floor.
2. **Guard.** The same pass checks for prompt injection and for crisis language.
   On a crisis phrase it blocks, routes to support rather than research, and no
   model is called at all.
3. **Clarification.** If confidence is in the low band, or two intents tie, it
   asks rather than guessing.
4. **A signed execution contract** names the tool and the tag groups it may use.
5. **Tagging.** The tagger sends only the tags from the routed groups — typically
   40 of 86 — to NVIDIA Nemotron through Meterless Nightshift. Returned tags are
   validated against the dictionary; anything invented is dropped.
   **Feedback loop 1:** if no tag survives, the tagger is asked once more with
   the full dictionary; if still none, the run returns `status: partial`.
6. **Matching.** Zetaris scores the research corpus by shared tags in SQL and
   returns up to 20 candidates. If Zetaris is unreachable, the agent falls back
   to `data/articles.csv`.
7. **Ranking and explanation.** The top three are ranked by how many of her
   concerns each covers, then by concerns she named in her own words over ones
   the tagger inferred, then by year. Each result says which of her words led to
   each tag ("she said *exhausted*"), where the article supports it ("the
   article mentions *heavy menstrual bleeding*"), which concerns it does not
   cover, and a citation. Each tag carries a confidence: she said it, she said
   something similar, or the agent inferred it.
   **Feedback loop 2:** if nothing matches, the search widens once to related
   tags in the same group (never across conditions), and those results are
   labelled as related.
8. **Evidence check.** **Feedback loop 3:** every quoted phrase must appear in
   her text and every tag must be on the article; anything unsupported is
   removed before the result is returned.

Every step, retry and removed claim is recorded in the run's `steps` and
`retries`. The loop lives in `app/main.py`; ranking, explanation and the
evidence check in `app/explain.py`.

## Architecture

| Layer | What |
|---|---|
| Data | **Zetaris** federates the corpus and the dictionary as Lightning REST tables, exposed as SchemaStore views in the `herinsights` container |
| Build | **Scout Intent** (Meterless Engine) in `app/engines/scout_intent.py` |
| Power | **Meterless Nightshift** as primary AI provider, serving **NVIDIA Nemotron 3.5 Lightning 30B** |

## Folder structure

```
womens-health-evidence-agent/
├── app/
│   ├── __init__.py
│   ├── main.py                 # agent loop: routing, tagging retry, matching, explain
│   ├── tagging.py              # dictionary load, model tagging, validation
│   ├── explain.py              # ranking, explanations, matcher retry, evidence check
│   ├── adapters/
│   │   ├── zetaris.py          # SQL over the Zetaris REST API; article matching
│   │   └── nightshift.py       # Meterless provider: auth, status, chat
│   └── engines/
│       └── scout_intent.py     # Meterless Engine: intent, guard, routing, contracts
├── data/
│   ├── tag_dictionary.json     # 86 tags across 8 groups
│   ├── synonyms.json           # variant phrasings mapped to canonical tags
│   ├── intent_registry.json    # Scout Intent registry (v2), crisis and injection patterns
│   ├── articles.csv            # 79 papers, deduplicated by DOI
│   └── articles_original.csv   # pre-retagging backup
├── scripts/
│   ├── config.py               # search terms per tag
│   ├── common.py               # record normalisation and dedup
│   ├── pull_pubmed.py          # ingestion, PubMed E-utilities
│   ├── pull_europe_pmc.py      # ingestion, Europe PMC REST
│   ├── pull_semantic_scholar.py # ingestion, Semantic Scholar Graph API
│   ├── pull_articles.py        # runs all three, writes data/articles.csv
│   ├── retag_articles.py       # re-tags articles with dictionary tags via Nightshift
│   ├── serve_data.py           # serves data as JSON for Zetaris to register
│   ├── load_zetaris.py         # registers REST tables and SchemaStore views
│   ├── probe_zetaris.py        # capability probe used to find the loading path
│   └── run_all_examples.py     # runs every input example, writes outputs
├── tests/
│   ├── test_tagging.py         # validation, dictionary load, JSON extraction
│   ├── test_nightshift.py      # URL normalisation, auth states, live chat
│   ├── test_scout_intent.py    # Scout Intent conformance against the spec
│   ├── test_explain.py         # ranking, explanations, matcher retry, evidence check
│   └── test_loop.py            # agent loop: tagging retry, partial results, failures
├── demo/
│   ├── build_page.py           # builds the results page from a real run
│   └── results.html            # the results page judges read
├── input_examples/             # 4 sample inputs
├── output_examples/            # matching outputs
├── logs/                       # Nightshift receipt and sample traces
├── run.py                      # entry point
├── smoke_test.py               # Zetaris and Nightshift connection checks
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── .env.example
└── README.md
```

## Data sources

| Source | What we used | How to regenerate |
|---|---|---|
| PubMed (NCBI E-utilities) | 8 searches across women's and LGBTQ+ health topics, relevance-ranked, abstracts required | `python scripts/pull_articles.py` |
| Europe PMC (REST) | Same 8 searches, `HAS_ABSTRACT:y` | same |
| Semantic Scholar (Graph API) | Same searches; heavily rate-limited without a key, so only 4 records came through | same |

`data/articles.csv` holds **79 papers**, deduplicated by DOI, with the sources
that returned each one recorded in `found_in`. Records without an abstract are
skipped rather than padded with the title.

We store bibliographic metadata and abstracts for research discovery. Licence
terms differ per publisher and per record; each row keeps its DOI and source URL
so the original can be checked. We make no licence claim over the underlying
articles.

`data/tag_dictionary.json` holds **86 tags across 8 groups** — sleep, cycle,
mood, body, gut, fertility, care, conditions — written in a woman's own words
rather than clinical terms.

## Setup

**Requirements:** Python 3.10+, Docker Desktop, Zetaris running locally,
Meterless Nightshift running, and an NVIDIA key added in Nightshift's Providers
tab (never in this repo).

```bash
git clone https://github.com/HerInsights-code/womens-health-evidence-agent.git
cd womens-health-evidence-agent
pip install -r requirements.txt
cp .env.example .env     # fill in your Zetaris and Nightshift values
```

Check both services are reachable:

```bash
python smoke_test.py
```

Three PASS lines, with the Nemotron model named on the third.

## Loading the data into Zetaris

Zetaris runs in Docker and cannot read local files, so the data is served over
HTTP and registered as REST tables.

```bash
# terminal 1 — leave running; Zetaris queries through to it
python scripts/serve_data.py

# terminal 2
python scripts/load_zetaris.py
```

This creates the `HERINSIGHTS_REST` Lightning database, the `herinsights`
SchemaStore container, and two views: `herinsights.tag_dictionary` and
`herinsights.articles`. The script verifies both with counts and a group-by.

## Usage

```bash
python run.py input_examples/input_example_1.json
```

All four examples at once:

```bash
python scripts/run_all_examples.py
```

Writes `output_examples/updated_output_from_<input file>.json` for each.

Without Nightshift, pass the tags directly (still validated against the
dictionary):

```bash
python run.py input_examples/input_example_1.json --tags "heavy periods,tired all day,skin changes"
```

The results page, built from a real run using the saved Nemotron tags:

```bash
python demo/build_page.py      # writes demo/results.html
open demo/results.html
```

It shows her words with the phrases behind each tag highlighted, the top three
papers with the reason each one matches, the crisis path, and the run log.

With Docker:

```bash
docker build -t oah-submission .
docker run --rm --env-file .env.docker oah-submission
```

`.env.docker` uses `host.docker.internal` instead of `localhost`, because inside
a container `127.0.0.1` means the container, not your machine. See
`.env.docker.example`.

## Tests

```bash
python -m pytest tests/ -v
```

`tests/test_scout_intent.py` is the engine's conformance suite: registry rules,
the Stage-1 latency budget, confidence bands, multi-intent routing, the four
clarification triggers, injection and crisis blocking, and contract signing,
tampering, expiry and registry drift. `tests/test_explain.py` and
`tests/test_loop.py` cover ranking, explanations, the evidence check and all
three feedback loops with no network calls. Live tests skip cleanly when Zetaris
or Nightshift are not running.

## Sponsor technology

**Zetaris — the data layer**

The research corpus and the tag dictionary are registered as Lightning REST
tables under `HERINSIGHTS_REST` and exposed as SchemaStore views in the
`herinsights` container. The agent queries them with SQL over the Zetaris REST
API — no copy, no pipeline per source. Zetaris does real work here: the matcher
scores 79 articles by shared tag count in SQL, and the loader verifies the data
with a `GROUP BY` across all 86 tags. Neither our server nor our Python performs
those operations. Registration is in `scripts/load_zetaris.py`; the adapter is
`app/adapters/zetaris.py`.

**Meterless Engine — Scout Intent**

We implemented the Scout Intent spec (`engines/scout-intent/AGENTS.md`) in
Python for a health-tagging registry. Implemented: the intent registry with
versioning, Stage-1 deterministic trigger scanning inside the 16ms budget with a
startup self-test, confidence bands, multi-intent routing with spans, the four
clarification triggers, a guard stack covering prompt injection and crisis
language, and signed execution contracts with a 5-minute TTL that are verified
before the tagger runs.

Not implemented, and documented in the module: Stage-2 model rescoring (the spec
permits its absence and degrades to Stage-1), the capability graph's selection
rules (one tool, nothing to select between), model profile routing (one model),
and the learning loop.

What it does for the product: the tagger sees roughly 40 of 86 tags instead of
all of them, so there is less for the model to get wrong. On crisis language the
guard blocks before any model call. On unclear input it asks instead of guessing.
Tests: `tests/test_scout_intent.py`.

**Meterless Nightshift — primary AI provider**

Every model call goes through Nightshift. `app/adapters/nightshift.py` implements
the Meterless provider contract: bearer auth with the Runtime token, base URL
normalisation, and a status check via `/v1/models` that distinguishes
`unauthorized` from `offline`. We read `meterless.routed_model` from every
response so the model that served each request is on the record. Auto Detect,
connect-link parsing, media and 3D routes and streaming are not implemented and
are noted in the module.

**NVIDIA — Nemotron through Nightshift**

`nvidia/nemotron-3.5-lightning-30b-a3b` serves every request, reached through
Nightshift with the NVIDIA key held in Nightshift's Providers tab. It does two
jobs: tagging a woman's paragraph against the dictionary, and tagging all 79
papers with the symptoms they are relevant to. That second job is what makes the
product work — it is how research catalogued by condition becomes findable by
lived experience. A signed Meterless receipt naming the model is committed at
`logs/sample-nightshift-receipt.json`.

**What was unique about our use**

Nemotron is not only answering questions — it is rewriting how the corpus is
indexed, translating clinical abstracts into the words women actually use. Scout
Intent is not a wrapper around that call; it decides what the model is allowed to
see, and refuses to call it at all when someone is in distress.

## Limitations

- **Corpus size.** 79 papers from PubMed and Europe PMC. Semantic Scholar was
  rate-limited and contributed 4. This is a demonstration corpus, not coverage.
- **Tags are model-assigned.** Article tags come from Nemotron reading titles and
  abstracts. They are validated against the dictionary but not clinician-reviewed.
  Two papers returned no tags and kept their original search term.
- **Crisis detection is keyword-based.** It catches common phrasings and
  normalises curly apostrophes, but it will never be complete. It is a safety net,
  not a clinical screen.
- **No Stage-2 rescoring.** Intent confidence comes from deterministic trigger
  matching only, so unusual phrasing may route poorly or fall to clarification.
- **Zetaris queries through to a local server.** The REST tables federate to
  `scripts/serve_data.py`, which must be running. Stopping it breaks the queries.
- **Not built.** A full `SAMPLE_MODE` offline path is described in our plan but
  is not in this submission. `--tags` and the local article fallback cover most
  of it: the agent runs without Nightshift or Zetaris, but not without the
  Python dependencies.
- **Explanations are rule-based.** Phrase attribution finds a tag or one of its
  listed synonyms in her text; phrasing outside the synonym list is marked
  "inferred" rather than quoted. There is no study grading yet, so ties fall
  back to publication year.
- **Not medical advice.** This surfaces published research. It does not diagnose,
  and it does not replace clinical judgment.