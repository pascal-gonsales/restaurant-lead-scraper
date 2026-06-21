#!/usr/bin/env python3
"""
workflow-generator.py - single source of truth for the Restaurant Lead Scraper.

This module owns every magic number in the pipeline: the scoring bands, the
tier thresholds, the default filters, and the chain blacklist. The n8n nodes
run JavaScript, but that JavaScript is *built* here by interpolating these
Python constants into JS strings. Tests then regex the generated JS back out
and assert it matches the constants, so the classic "same threshold in three
places, two values, silent drift" bug class is structurally impossible.

Runtime is standard library only. The pytest suite is the only dev dependency.

What it emits: a 9-node *skeleton* n8n workflow JSON per city in CITIES,
written to generated-workflow-<slug>.json in this script's directory.
The skeleton is deliberately a subset of the canonical 19-node
scraper-workflow.json: it omits the pagination control flow, homepage fetch,
Combine Details, Extract Emails, Multi-Location, and Summary nodes. Full
parity with the hand-built canonical workflow is out of scope by design.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Section 1 - Constants (the single source of truth)
# ---------------------------------------------------------------------------

# Review-volume bands. Evaluated top-down, first match wins.
# Each row: (min_reviews, points, label).
SCORING_REVIEW_THRESHOLDS: list[tuple[int, int, str]] = [
    (500, 4, "reviews_500+"),
    (300, 3, "reviews_300+"),
    (150, 2, "reviews_150+"),
    (50, 1, "reviews_50+"),
]

# Rating "sweet spot": established enough to have budget, not so dominant they
# need no help. Inclusive on both ends.
SCORING_RATING_SWEETSPOT: tuple[float, float] = (3.8, 4.5)
SCORING_RATING_SWEETSPOT_POINTS = 3
SCORING_RATING_OUTSIDE_POINTS = 1  # rating below the sweet spot ("struggling")

# Price level.
SCORING_PRICE_HIGH_THRESHOLD = 2
SCORING_PRICE_HIGH_POINTS = 2
SCORING_PRICE_LOW_POINTS = 1

# Multi-service bonus: a venue that also runs a bar / club / delivery / takeaway.
SCORING_MULTI_SERVICE_TYPES = ["bar", "night_club", "meal_delivery", "meal_takeaway"]
SCORING_MULTI_SERVICE_POINTS = 1

# Multi-unit bonus, applied only downstream in the Multi-Location node.
SCORING_MULTI_UNIT_BONUS = 3

# Tier thresholds, applied to whatever score is current at the node.
TIER_HOT = 8
TIER_WARM = 5

# Default hard-filter values (overridable per city / per webhook call).
DEFAULT_MIN_REVIEWS = 50
DEFAULT_MIN_RATING = 3.5
DEFAULT_MAX_RATING = 4.7
DEFAULT_MIN_PRICE_LEVEL = 1

# Email extraction: junk filters.
JUNK_EMAIL_SUBSTRINGS = [
    "example",
    "domain.com",
    "wixpress",
    "sentry",
    "cloudflare",
    "googleapis",
    "schema.org",
    "wordpress",
    "gravatar",
    "w3.org",
    "noreply",
    "no-reply",
    "webmaster",
    "support@",
]
JUNK_EMAIL_EXTENSIONS = [".png", ".jpg", ".svg", ".js", ".css", ".gif", ".webp"]

# Generic email prefixes that are not owner-reachable. Used to prefer a
# personal address over a role address.
GENERIC_EMAIL_PREFIXES = [
    "info@",
    "contact@",
    "reservation",
    "booking",
    "admin@",
    "hello@",
]

# Chain blacklist (substring, case-insensitive). All entries are well-known
# PUBLIC brand fragments, not client data. Deliberately short fragments to
# catch spelling variants; this aggressiveness is intentional and tested.
# Embedded verbatim into the Configuration node JS via json.dumps(...).
CHAIN_BLACKLIST: list[str] = [
    'mcdonald', 'mcdo', 'burger king', 'kfc', 'kentucky', 'subway', 'pizza hut',
    'domino', 'quick', 'five guys', 'paul', 'starbucks', 'kebab factory',
    'class croute', 'brioche doree', 'la mie caline', 'flunch', 'buffalo grill',
    'hippopotamus', 'courtepaille', 'del arte', 'pizza pai', 'la pataterie',
    'popeyes', 'taco bell', 'wendy', 'dunkin', 'krispy kreme', 'pret a manger',
    'tim hortons', 'a&w', 'harvey', 'st-hubert rotisserie',
    'baton rouge', 'scores', 'pacini', 'mikes', 'pizza pizza', 'pizza nova',
    'thai express', 'manchu wok', 'cultures', 'extreme pita',
    'sushi daily', 'panda express', 'chipotle', 'shake shack',
    'nandos', 'nando', 'la cage', 'cora', 'eggsquis',
]

# Generic place types stripped when deriving the Cuisine label.
GENERIC_PLACE_TYPES = ["restaurant", "food", "point_of_interest", "establishment", "store"]

# Placeholder credentials. NEVER ship a real key / id.
PLACEHOLDER_API_KEY = "YOUR_GOOGLE_PLACES_API_KEY_HERE"
PLACEHOLDER_SHEET_ID = "YOUR_GOOGLE_SHEET_ID_HERE"
PLACEHOLDER_CREDENTIAL_ID = "YOUR_CREDENTIAL_ID"

# Cities to generate skeletons for. The shipped sample is fully generic.
CITIES: list[dict] = [
    {
        "name": "Demo City",
        "search_location": "Demo City",
        "queries": ["restaurant", "resto bar", "traiteur"],
        "min_reviews": DEFAULT_MIN_REVIEWS,
        "min_rating": DEFAULT_MIN_RATING,
        "max_rating": DEFAULT_MAX_RATING,
        "sheet_id": PLACEHOLDER_SHEET_ID,
    },
]

REQUIRED_CITY_KEYS = [
    "name",
    "search_location",
    "queries",
    "min_reviews",
    "min_rating",
    "max_rating",
    "sheet_id",
]


# ---------------------------------------------------------------------------
# Section 2 - Pure-Python helpers (tested mirrors of the JS node logic)
# ---------------------------------------------------------------------------

def is_chain(name: str, blacklist: list[str] | None = None) -> bool:
    """True if name contains any blacklist fragment (case-insensitive)."""
    if not name:
        return False
    bl = CHAIN_BLACKLIST if blacklist is None else blacklist
    low = name.lower()
    return any(fragment in low for fragment in bl)


def score_place(place: dict) -> tuple[int, list[str]]:
    """Score a place on the 0..10 base scale. Returns (score, breakdown_labels).

    Mirrors the JS in build_scoring_js(). The multi-unit +3 bonus is NOT applied
    here; it lives in the downstream Multi-Location node.
    """
    score = 0
    breakdown: list[str] = []

    reviews = int(place.get("reviews", 0) or 0)
    # Review volume: first matching band wins. The defensive else awards the
    # lowest row even below its min (unreachable in production because the
    # upstream filter drops reviews < min_reviews).
    for i, (min_reviews, points, label) in enumerate(SCORING_REVIEW_THRESHOLDS):
        is_last = i == len(SCORING_REVIEW_THRESHOLDS) - 1
        if reviews >= min_reviews or is_last:
            score += points
            breakdown.append(label)
            break

    rating = float(place.get("rating", 0) or 0)
    low, high = SCORING_RATING_SWEETSPOT
    if low <= rating <= high:
        score += SCORING_RATING_SWEETSPOT_POINTS
        breakdown.append("rating_sweetspot")
    elif rating < low:
        score += SCORING_RATING_OUTSIDE_POINTS
        breakdown.append("rating_struggling")
    else:  # rating > high
        score += SCORING_RATING_OUTSIDE_POINTS
        breakdown.append("rating_high")

    price_level = int(place.get("price_level", 0) or 0)
    if price_level >= SCORING_PRICE_HIGH_THRESHOLD:
        score += SCORING_PRICE_HIGH_POINTS
        breakdown.append("price_$$+")
    elif price_level == 1:
        score += SCORING_PRICE_LOW_POINTS
        breakdown.append("price_$")
    # price_level == 0 -> 0 points

    types = [str(t).lower() for t in (place.get("types") or [])]
    if any(t in SCORING_MULTI_SERVICE_TYPES for t in types):
        score += SCORING_MULTI_SERVICE_POINTS
        breakdown.append("multi_service")

    return score, breakdown


def assign_tier(score: int) -> str:
    """HOT / WARM / COOL from the current score using TIER_HOT / TIER_WARM."""
    if score >= TIER_HOT:
        return "HOT"
    if score >= TIER_WARM:
        return "WARM"
    return "COOL"


def is_junk_email(email: str) -> bool:
    """True if the address is junk (reserved domain, telemetry, role, asset)."""
    if not email:
        return True
    low = email.lower()
    if any(sub in low for sub in JUNK_EMAIL_SUBSTRINGS):
        return True
    if any(low.endswith(ext) for ext in JUNK_EMAIL_EXTENSIONS):
        return True
    return False


def pick_best_email(emails: list[str]) -> str:
    """Prefer a personal address over a role address, else first available."""
    if not emails:
        return ""
    personal = next(
        (e for e in emails
         if not any(e.lower().startswith(p) for p in GENERIC_EMAIL_PREFIXES)),
        None,
    )
    generic = next(
        (e for e in emails
         if e.lower().startswith("info@") or e.lower().startswith("contact@")),
        None,
    )
    return personal or generic or emails[0]


# ---------------------------------------------------------------------------
# Section 3 - JS builders (interpolate the constants into node JavaScript)
# ---------------------------------------------------------------------------

def build_config_js(city: dict) -> str:
    """Configuration node JS: read webhook params with city defaults, embed the
    chain blacklist verbatim, set the placeholder API key."""
    blacklist_js = json.dumps(CHAIN_BLACKLIST, indent=2)
    queries_default = ",".join(city["queries"])
    return f"""// Configuration - reads webhook query/params, applies city defaults.
const incoming = $json.query || $json.params || {{}};

const city = incoming.city || {json.dumps(city["search_location"])};
const searchQueries = (incoming.searchQueries || {json.dumps(queries_default)})
  .split(',')
  .map(q => q.trim())
  .filter(q => q.length > 0);

const minReviews = parseInt(incoming.minReviews, 10) || {city["min_reviews"]};
const minRating = parseFloat(incoming.minRating) || {city["min_rating"]};
const maxRating = parseFloat(incoming.maxRating) || {city["max_rating"]};
const minPriceLevel = parseInt(incoming.minPriceLevel, 10) || {DEFAULT_MIN_PRICE_LEVEL};

const chainBlacklist = {blacklist_js};

const apiKey = {json.dumps(PLACEHOLDER_API_KEY)};

return [{{ json: {{
  city,
  searchQueries,
  minReviews,
  minRating,
  maxRating,
  minPriceLevel,
  chainBlacklist,
  apiKey,
}} }}];
"""


def build_scoring_js() -> str:
    """Quality Filter + Score node JS, built entirely from the constants so it
    can never drift from the Python source of truth."""
    # Review-volume if / else-if / else chain from SCORING_REVIEW_THRESHOLDS.
    review_lines = []
    for i, (min_reviews, points, label) in enumerate(SCORING_REVIEW_THRESHOLDS):
        is_first = i == 0
        is_last = i == len(SCORING_REVIEW_THRESHOLDS) - 1
        if is_first:
            review_lines.append(
                f"    if (reviews >= {min_reviews}) {{ score += {points}; "
                f"breakdown.push('{label}'); }}"
            )
        elif is_last:
            review_lines.append(
                f"    else {{ score += {points}; breakdown.push('{label}'); }}"
            )
        else:
            review_lines.append(
                f"    else if (reviews >= {min_reviews}) {{ score += {points}; "
                f"breakdown.push('{label}'); }}"
            )
    review_block = "\n".join(review_lines)

    sweet_low, sweet_high = SCORING_RATING_SWEETSPOT
    multi_service_js = json.dumps(SCORING_MULTI_SERVICE_TYPES)
    blacklist_js = json.dumps(CHAIN_BLACKLIST)

    return f"""// Quality Filter + Score - dedup, hard filters, score, tier. Sort desc.
const input = $input.first().json;
const allPlaces = input.allPlaces || [];
const config = input.config || {{}};

const minReviews = config.minReviews || {DEFAULT_MIN_REVIEWS};
const minRating = config.minRating || {DEFAULT_MIN_RATING};
const maxRating = config.maxRating || {DEFAULT_MAX_RATING};
const chainBlacklist = config.chainBlacklist || {blacklist_js};
const multiServiceTypes = {multi_service_js};

const seen = new Set();
const scored = [];

for (const place of allPlaces) {{
  // 1. Dedup by place_id.
  if (seen.has(place.place_id)) continue;
  seen.add(place.place_id);

  // 2. Chain blacklist (substring, case-insensitive).
  const lowName = (place.name || '').toLowerCase();
  if (chainBlacklist.some(c => lowName.includes(c))) continue;

  // 3. Must be operational if status is present.
  if (place.business_status && place.business_status !== 'OPERATIONAL') continue;

  // 4. Minimum review volume.
  const reviews = place.reviews || 0;
  if (reviews < minReviews) continue;

  // 5. Rating window (note: wider than the sweet-spot scoring band).
  const rating = place.rating || 0;
  if (rating < minRating || rating > maxRating) continue;

  // ---- score ----
  let score = 0;
  const breakdown = [];

{review_block}

    if (rating >= {sweet_low} && rating <= {sweet_high}) {{ score += {SCORING_RATING_SWEETSPOT_POINTS}; breakdown.push('rating_sweetspot'); }}
    else if (rating < {sweet_low}) {{ score += {SCORING_RATING_OUTSIDE_POINTS}; breakdown.push('rating_struggling'); }}
    else {{ score += {SCORING_RATING_OUTSIDE_POINTS}; breakdown.push('rating_high'); }}

    const priceLevel = place.price_level || 0;
    if (priceLevel >= {SCORING_PRICE_HIGH_THRESHOLD}) {{ score += {SCORING_PRICE_HIGH_POINTS}; breakdown.push('price_$$+'); }}
    else if (priceLevel === 1) {{ score += {SCORING_PRICE_LOW_POINTS}; breakdown.push('price_$'); }}

    const types = (place.types || []).map(t => String(t).toLowerCase());
    if (types.some(t => multiServiceTypes.includes(t))) {{ score += {SCORING_MULTI_SERVICE_POINTS}; breakdown.push('multi_service'); }}

  const tier = score >= {TIER_HOT} ? 'HOT' : score >= {TIER_WARM} ? 'WARM' : 'COOL';

  scored.push({{ ...place, score, breakdown, tier }});
}}

scored.sort((a, b) => b.score - a.score);
return scored.map(s => ({{ json: s }}));
"""


def build_email_extraction_js() -> str:
    """Extract Emails node JS: regex, junk filter, dedup, prioritize."""
    junk_subs_js = json.dumps(JUNK_EMAIL_SUBSTRINGS)
    junk_ext_js = json.dumps(JUNK_EMAIL_EXTENSIONS)
    generic_js = json.dumps(GENERIC_EMAIL_PREFIXES)
    return f"""// Extract Emails - regex, junk filter, dedup, prioritize.
const item = $json;
const html = item.body || item.data || '';
const info = item;

const junkSubstrings = {junk_subs_js};
const junkExtensions = {junk_ext_js};
const genericPrefixes = {generic_js};

let email = '';
let allEmails = [];

if (html.length > 100 && info.hasWebsite) {{
  const regex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{{2,}}/gi;
  const matches = html.match(regex) || [];

  const cleaned = [];
  const seen = new Set();
  for (const raw of matches) {{
    const low = raw.toLowerCase();
    if (junkSubstrings.some(s => low.includes(s))) continue;
    if (junkExtensions.some(ext => low.endsWith(ext))) continue;
    if (seen.has(low)) continue;
    seen.add(low);
    cleaned.push(raw);
  }}
  allEmails = cleaned;

  const personal = cleaned.find(e => !genericPrefixes.some(p => e.toLowerCase().startsWith(p)));
  const generic = cleaned.find(e => e.toLowerCase().startsWith('info@') || e.toLowerCase().startsWith('contact@'));
  email = personal || generic || cleaned[0] || '';
}}

let emailSource;
if (email) emailSource = 'homepage';
else if (info.hasWebsite) emailSource = 'not_found';
else emailSource = 'no_website';

return [{{ json: {{ ...item, email, emailSource, allEmails }} }}];
"""


# ---------------------------------------------------------------------------
# Section 4 - Workflow assembly (9-node skeleton)
# ---------------------------------------------------------------------------

def _build_generate_urls_js() -> str:
    return """// Generate Search URLs - one Places Text Search URL per query.
const input = $input.first().json;
const config = input;
return config.searchQueries.map(searchQuery => {
  const q = encodeURIComponent(searchQuery + ' in ' + config.city);
  const searchUrl =
    'https://maps.googleapis.com/maps/api/place/textsearch/json' +
    '?query=' + q + '&type=restaurant&key=' + config.apiKey;
  return { json: { searchUrl, searchQuery, city: config.city, config } };
});
"""


def _build_extract_page1_js() -> str:
    return """// Extract Page 1 - normalize results, collect next_page_token.
const items = $input.all();
const allPlaces = [];
const page2Urls = [];
let config = {};

for (const item of items) {
  const data = item.json.data || item.json;
  config = item.json.config || config;
  const results = (data.results || []);
  for (const r of results) {
    allPlaces.push({
      place_id: r.place_id,
      name: r.name,
      address: r.formatted_address,
      rating: r.rating,
      reviews: r.user_ratings_total,
      price_level: r.price_level,
      types: r.types || [],
      business_status: r.business_status,
      searchQuery: item.json.searchQuery,
    });
  }
  if (data.next_page_token) {
    page2Urls.push(
      'https://maps.googleapis.com/maps/api/place/textsearch/json' +
      '?pagetoken=' + data.next_page_token + '&key=' + config.apiKey
    );
  }
}

return [{ json: { allPlaces, page2Urls, config } }];
"""


def generate_workflow(city: dict) -> dict:
    """Assemble a 9-node skeleton n8n workflow for a city.

    Raises KeyError listing any missing required city fields. Runs a post-build
    self-check that every connection endpoint references a real node name.
    """
    missing = [k for k in REQUIRED_CITY_KEYS if k not in city]
    if missing:
        raise KeyError(f"city is missing required field(s): {missing}")

    nodes = [
        {
            "name": "Start",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [200, 400],
            "parameters": {},
        },
        {
            "name": "Webhook Trigger",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2,
            "position": [200, 600],
            "webhookId": "scrape-v2-wh",
            "parameters": {
                "httpMethod": "GET",
                "path": "scrape-restaurants-v2",
                "responseMode": "lastNode",
            },
        },
        {
            "name": "Configuration",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [500, 500],
            "parameters": {"jsCode": build_config_js(city)},
        },
        {
            "name": "Generate Search URLs",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [720, 500],
            "parameters": {"jsCode": _build_generate_urls_js()},
        },
        {
            "name": "Search Page 1",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [940, 500],
            "parameters": {
                "url": "={{ $json.searchUrl }}",
                "options": {
                    "batching": {"batch": {"batchSize": 1, "batchInterval": 2500}},
                    "timeout": 15000,
                },
            },
        },
        {
            "name": "Extract Page 1",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1160, 500],
            "parameters": {"jsCode": _build_extract_page1_js()},
        },
        {
            "name": "Quality Filter + Score",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1380, 500],
            "parameters": {"jsCode": build_scoring_js()},
        },
        {
            "name": "Get Details",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1600, 500],
            "parameters": {
                "url": (
                    "=https://maps.googleapis.com/maps/api/place/details/json"
                    "?place_id={{ $json.place_id }}"
                    "&fields=formatted_phone_number,website,opening_hours,price_level,url"
                    f"&key={PLACEHOLDER_API_KEY}"
                ),
                "options": {
                    "batching": {"batch": {"batchSize": 5, "batchInterval": 1000}},
                    "timeout": 10000,
                },
            },
        },
        {
            "name": "Save to Sheet",
            "type": "n8n-nodes-base.googleSheets",
            "typeVersion": 4.5,
            "position": [1820, 500],
            "parameters": {
                "operation": "append",
                "documentId": {"__rl": True, "value": city["sheet_id"], "mode": "id"},
                "sheetName": {"__rl": True, "value": "gid=0", "mode": "id"},
                "options": {},
            },
            "credentials": {
                "googleSheetsOAuth2Api": {
                    "id": PLACEHOLDER_CREDENTIAL_ID,
                    "name": "Google Sheets account (placeholder)",
                }
            },
        },
    ]

    connections = {
        "Start": {"main": [[{"node": "Configuration", "type": "main", "index": 0}]]},
        "Webhook Trigger": {"main": [[{"node": "Configuration", "type": "main", "index": 0}]]},
        "Configuration": {"main": [[{"node": "Generate Search URLs", "type": "main", "index": 0}]]},
        "Generate Search URLs": {"main": [[{"node": "Search Page 1", "type": "main", "index": 0}]]},
        "Search Page 1": {"main": [[{"node": "Extract Page 1", "type": "main", "index": 0}]]},
        "Extract Page 1": {"main": [[{"node": "Quality Filter + Score", "type": "main", "index": 0}]]},
        "Quality Filter + Score": {"main": [[{"node": "Get Details", "type": "main", "index": 0}]]},
        "Get Details": {"main": [[{"node": "Save to Sheet", "type": "main", "index": 0}]]},
    }

    workflow = {
        "name": f"Restaurant Lead Scraper (skeleton) - {city['name']}",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }

    # Post-build self-check: every connection endpoint references a real node.
    node_names = {n["name"] for n in nodes}
    for source, conn in connections.items():
        assert source in node_names, f"connection source not a node: {source}"
        for output in conn.get("main", []):
            for edge in output:
                assert edge["node"] in node_names, (
                    f"connection target not a node: {edge['node']}"
                )

    return workflow


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def main() -> int:
    here = Path(__file__).resolve().parent
    for city in CITIES:
        wf = generate_workflow(city)
        out = here / f"generated-workflow-{_slug(city['name'])}.json"
        out.write_text(json.dumps(wf, indent=2) + "\n", encoding="utf-8")
        print(f"OK: {city['name']} | {len(wf['nodes'])} nodes | {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
