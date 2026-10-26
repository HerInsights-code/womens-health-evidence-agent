# Agent rules for this project

## What this is
A tagging and research-matching agent for the Open Agent Hackathon 2026,
Track 02 ("The Agent That Can Explain Why"). A woman writes what she is
experiencing in her own words; the agent assigns tags, explains why it
chose each one, and returns matching research with the reason for each match.

## Hard rules
- Never print, log, or commit secrets. Mask tokens in error messages.
- All config comes from `.env` via python-dotenv. Never hardcode URLs or keys.
- The NVIDIA key lives only in Nightshift's Providers tab, never in this repo.
- All model calls go through Meterless Nightshift. No other provider.
- All data queries go through Zetaris. No direct database access.
- Tags come only from `data/tag_dictionary.json`. Never invent tags.

## Config (names are fixed, do not rename)
METERLESS_BASE_URL, METERLESS_RUNTIME_TOKEN, METERLESS_MODEL
ZETARIS_REST_URL, ZETARIS_ORG_ID, ZETARIS_API_KEY
NCBI_API_KEY, SEMANTIC_SCHOLAR_API_KEY
SAMPLE_MODE, LOG_LEVEL, PORT

## Layout
app/adapters/nightshift.py   model calls through Meterless
app/adapters/zetaris.py      SQL over Zetaris REST
app/engines/scout_intent.py  Meterless Engine — routes paragraphs to tag groups
app/tagging.py               paragraph → validated tags
app/matching.py              tags → matched articles
app/explain.py               explanations + evidence check
app/main.py                  agent loop and feedback loops
scripts/                     data ingestion
data/                        tag dictionary, synonyms, articles.csv
tests/                       unit and integration tests
logs/                        run traces

## Integration conventions
- Zetaris REST: POST {ZETARIS_REST_URL}/sql-editor/sqls/run with headers
  Authorization: Bearer {ZETARIS_API_KEY}, X-Org-ID: {ZETARIS_ORG_ID},
  X-Request-ID: a fresh uuid4 per call. One SQL statement per request.
- Nightshift: OpenAI-compatible chat completions, plus headers
  meterless-app: womens-health-evidence-agent and meterless-scope: user.
  Log `meterless.routed_model` from every response — it is our evidence
  that a Nemotron model served the request.
- The model is a reasoning model, so parse responses defensively. Extract
  the JSON payload rather than assuming the whole reply is JSON.
- Timeouts: 30s on Zetaris, 90s on Nightshift. Cap every retry loop.

## Agent loop
The flow is not a fixed chain. It validates its own output and retries:
- Tagging: drop tags not in the dictionary; retry once if none are valid.
- Matching: if no articles match, drop the weakest tag and search once more.
- Explanations: every cited phrase must appear in the user's text and every
  tag must be on the matched article; remove anything unsupported.
Log every step, every retry with its reason, and every removed claim.

## Testing
- Every new function gets a test in `tests/` before it is considered done.
- Run the tests and show the output. Do not report a feature as working
  without a passing run.
- Pure logic (validation, matching, evidence checks) gets real unit tests
  with no network calls.
- Code that calls Zetaris or Nightshift gets one integration test, marked
  so it can be skipped when the services are not running.
- The Meterless Engine must keep a passing test — it is a submission
  requirement and the README points at it.
- When a test fails, fix the code, not the test.

## Health content
This surfaces published research. It is not medical advice and must not
read as diagnosis. Keep the disclaimer intact. If a user's input suggests
crisis, the response points to support rather than research.

## Working style
Dry-run before creating or changing files. Show the plan and wait for
approval. Keep changes scoped to the file under discussion.