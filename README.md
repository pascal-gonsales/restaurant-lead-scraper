# Restaurant Lead Scraper

A B2B lead-generation pipeline that finds independent restaurants in a city,
filters out chains, scores each prospect on a 0 to 13 quality scale, scrapes a
contact email off the homepage, and appends qualified leads to a Google Sheet.

Built for an agency or operator who sells services to restaurants. The scoring
deliberately targets the "rating sweet spot": venues established enough to have
budget, but not so dominant they need no help.

Two artifacts ship together:

- **`scraper-workflow.json`** - a hand-built, 19-node n8n production workflow.
- **`workflow-generator.py`** - a Python generator that emits a 9-node skeleton
  n8n workflow per city from a single source of truth, plus a pytest suite that
  guarantees the embedded JavaScript thresholds never drift from the Python
  constants.

## What it does

```
Google Places Text Search  ->  normalize + dedup
        |                            |
        v                            v
   pagination (2 pages)   ->   Quality Filter + Score (0..10)
                                     |
                                     v
   Place Details (phone, website, maps)
                                     |
                                     v
   Fetch homepage HTML  ->  Extract + prioritize email
                                     |
                                     v
   Multi-location detection (+3 bonus, final 0..13 tier)
                                     |
                                     v
   Append to Google Sheet  ->  Summary report
```

Data sources: Google Places API (Text Search + Place Details) and restaurant
homepage HTML. Sink: a Google Sheet via OAuth2.

## The scoring algorithm (the IP)

Base score is 0 to 10. A downstream multi-location bonus of +3 lifts the ceiling
to 13.

| Signal | Rule | Points |
| --- | --- | --- |
| Review volume | >=500 / >=300 / >=150 / >=50 (first match wins) | +4 / +3 / +2 / +1 |
| Rating sweet spot | rating in [3.8, 4.5] inclusive | +3 |
| Rating outside | below 3.8 ("struggling") or above 4.5 ("high") | +1 |
| Price level | price_level >= 2 / == 1 | +2 / +1 |
| Multi-service | also a bar / club / delivery / takeaway | +1 |
| Multi-unit | same brand appears 2+ times (downstream) | +3 |

Tiers: `score >= 8 -> HOT`, `score >= 5 -> WARM`, else `COOL`.

Hard pre-filters drop a place before it is ever scored, in order: dedup by
place id, chain-blacklist name match, non-operational business status, too few
reviews, and rating outside the wider [3.5, 4.7] acceptance window. Note the
asymmetry: the acceptance window (3.5 to 4.7) is intentionally wider than the
sweet-spot scoring band (3.8 to 4.5).

It is not a toy scraper. It demonstrates a real scoring algorithm, data hygiene
(a 52-entry chain blacklist, email junk filtering, dedup, multi-location
detection), and cost-aware API batching.

## Single source of truth + a drift catcher (the headline engineering point)

The n8n nodes run JavaScript, but every magic number in that JavaScript is
defined exactly once, in Python, in `workflow-generator.py`. The generator
builds the node JS by interpolating those constants. The test suite then regexes
the numbers back out of the generated JS and asserts they equal the Python
constants.

This structurally eliminates a whole bug class: the "same threshold lives in
three places, two of them say 8 and one says 7, and nobody notices until leads
get mis-tiered" failure. If anyone edits a JS literal by hand, CI goes red. The
drift catcher even checks the hand-built canonical 19-node workflow, so both
tier ternaries (scoring node and final multi-location node) are pinned to the
same `TIER_HOT` / `TIER_WARM` constants.

## How to run

Generate a skeleton workflow per city (standard library only, no install):

```bash
python workflow-generator.py
# OK: Demo City | 9 nodes | ./generated-workflow-demo-city.json
```

Run the tests (pytest is the only dev dependency):

```bash
python -m venv .venv && . .venv/bin/activate
pip install pytest
python -m py_compile workflow-generator.py
python -m pytest tests/ -v
```

To use the production pipeline, import `scraper-workflow.json` into n8n, then
replace the placeholder credentials (`YOUR_GOOGLE_PLACES_API_KEY_HERE`,
`YOUR_GOOGLE_SHEET_ID_HERE`, `YOUR_CREDENTIAL_ID`) with your own Google Places
API key, target Sheet id, and a Google Sheets OAuth2 credential.

## Scope and honest claims

- The generator emits a **9-node skeleton** (config, search, extract, score,
  details, save). The **19-node canonical workflow** adds pagination, homepage
  fetch, email extraction, multi-location detection, and a summary report. Full
  parity between the two is out of scope by design and is documented in the
  generator docstring. A test pins each node count so accidental drift is caught.
- Every value in this repo is synthetic. `examples/sample-output.csv` uses
  obviously-fictional venue names, `555-01xx` phones, and `.fictional-test`
  email domains. There are no real API keys, Sheet ids, or customer data
  anywhere in the repo, and a CI test asserts only placeholders are present.
- No lint or type checker is wired in (no `ruff`, no `mypy`), and CI runs a
  single Python version (3.11). The code targets Python 3.11+.

## License

MIT. See [LICENSE](LICENSE).
