"""Scoring + tiering tests, including JS<->Python drift catchers (9 tests)."""
from __future__ import annotations

import re

from .conftest import wfg


def test_scoring_constants_exported():
    assert wfg.TIER_HOT == 8
    assert wfg.TIER_WARM == 5
    assert wfg.SCORING_RATING_SWEETSPOT == (3.8, 4.5)
    assert wfg.SCORING_MULTI_UNIT_BONUS == 3
    assert wfg.DEFAULT_MIN_REVIEWS == 50
    assert [row[0] for row in wfg.SCORING_REVIEW_THRESHOLDS] == [500, 300, 150, 50]


def test_score_place_max_possible_is_ten():
    place = {
        "reviews": 800,
        "rating": 4.2,          # in [3.8, 4.5]
        "price_level": 3,       # >= 2
        "types": ["restaurant", "bar"],  # multi-service
    }
    score, breakdown = wfg.score_place(place)
    assert score == 10
    assert breakdown == ["reviews_500+", "rating_sweetspot", "price_$$+", "multi_service"]


def test_score_place_minimum_threshold_case():
    # Just above the hard filters; lowest band, struggling rating, no price/service.
    place = {"reviews": 50, "rating": 3.5, "price_level": 0, "types": ["restaurant"]}
    score, breakdown = wfg.score_place(place)
    # reviews_50+ (+1) + rating 3.5 < 3.8 -> rating_struggling (+1); price 0 (0).
    assert score == 2
    assert "reviews_50+" in breakdown
    assert "rating_struggling" in breakdown


def test_review_thresholds_evaluated_top_down():
    # 600 reviews must score the 500+ band, not 300+/150+/50+.
    score, breakdown = wfg.score_place({"reviews": 600, "rating": 4.0, "price_level": 0, "types": []})
    assert "reviews_500+" in breakdown
    assert "reviews_300+" not in breakdown
    # 350 reviews -> 300+ band.
    _, b2 = wfg.score_place({"reviews": 350, "rating": 4.0, "price_level": 0, "types": []})
    assert "reviews_300+" in b2 and "reviews_500+" not in b2
    # 200 -> 150+, 80 -> 50+.
    _, b3 = wfg.score_place({"reviews": 200, "rating": 4.0, "price_level": 0, "types": []})
    assert "reviews_150+" in b3
    _, b4 = wfg.score_place({"reviews": 80, "rating": 4.0, "price_level": 0, "types": []})
    assert "reviews_50+" in b4


def test_rating_sweetspot_inclusive_bounds():
    # Both 3.8 and 4.5 are inside the sweet spot and score 3.
    s_low, b_low = wfg.score_place({"reviews": 60, "rating": 3.8, "price_level": 0, "types": []})
    s_high, b_high = wfg.score_place({"reviews": 60, "rating": 4.5, "price_level": 0, "types": []})
    assert "rating_sweetspot" in b_low
    assert "rating_sweetspot" in b_high
    # reviews_50+ (1) + rating_sweetspot (3) = 4 each.
    assert s_low == 4
    assert s_high == 4


def test_assign_tier_boundaries():
    assert wfg.assign_tier(8) == "HOT"
    assert wfg.assign_tier(7) == "WARM"
    assert wfg.assign_tier(5) == "WARM"
    assert wfg.assign_tier(4) == "COOL"
    assert wfg.assign_tier(0) == "COOL"


def test_drift_js_tier_thresholds_match_python():
    js = wfg.build_scoring_js()
    m = re.search(
        r"(?:final[Ss]core|score)\s*>=\s*(\d+)\s*\?\s*'HOT'\s*:\s*"
        r"(?:final[Ss]core|score)\s*>=\s*(\d+)\s*\?\s*'WARM'",
        js,
    )
    assert m is not None, "tier ternary not found in generated scoring JS"
    assert int(m.group(1)) == wfg.TIER_HOT
    assert int(m.group(2)) == wfg.TIER_WARM


def test_drift_js_review_thresholds_match_python():
    js = wfg.build_scoring_js()
    # Pull the (min_reviews -> points) pairs out of the if/else-if chain.
    pairs = re.findall(r"reviews >= (\d+)\) \{ score \+= (\d+);", js)
    js_map = {int(a): int(b) for a, b in pairs}
    # The last band is an `else` with no `reviews >=` guard; add it from JS.
    else_pts = re.search(r"else \{ score \+= (\d+); breakdown\.push\('reviews_50\+'\)", js)
    assert else_pts is not None
    js_map[50] = int(else_pts.group(1))
    py_map = {mr: pts for mr, pts, _ in wfg.SCORING_REVIEW_THRESHOLDS}
    assert js_map == py_map


def test_drift_js_blacklist_matches_python():
    js = wfg.build_config_js(wfg.CITIES[0])
    for fragment in wfg.CHAIN_BLACKLIST:
        assert fragment in js, f"blacklist fragment missing from generated config JS: {fragment}"
    assert len(wfg.CHAIN_BLACKLIST) == 52
