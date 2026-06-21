"""Chain-blacklist filtering tests (8 tests)."""
from __future__ import annotations

from .conftest import wfg


def test_filters_north_american_chain_variants():
    assert wfg.is_chain("McDonald's Demo City")
    assert wfg.is_chain("Subway Demo Plaza")
    assert wfg.is_chain("Tim Hortons #402")
    assert wfg.is_chain("Pizza Pizza Demo")


def test_filters_french_quebec_chain_variants():
    assert wfg.is_chain("Buffalo Grill Demo")
    assert wfg.is_chain("La Cage Demo Sports Bar")
    assert wfg.is_chain("Cora Demo Breakfast")
    assert wfg.is_chain("Brioche Doree Demo")


def test_does_not_filter_independent_names():
    assert not wfg.is_chain("Northstar Demo Bistro")
    assert not wfg.is_chain("Halcyon Demo Bakery")
    assert not wfg.is_chain("Riverbend Demo Diner")


def test_case_insensitive_matching():
    assert wfg.is_chain("STARBUCKS DEMO")
    assert wfg.is_chain("starbucks demo")
    assert wfg.is_chain("StArBuCks Demo")


def test_handles_empty_and_none():
    assert wfg.is_chain("") is False
    assert wfg.is_chain(None) is False


def test_substring_aggressiveness_is_intentional():
    # Short fragments intentionally catch variants/superstrings. "mcdo" hits
    # "McDo" and a longer brand string alike; "scores" is a substring match.
    assert wfg.is_chain("McDo Demo Express")
    assert wfg.is_chain("Scores Demo Grill")
    assert len(wfg.CHAIN_BLACKLIST) == 52


def test_custom_blacklist_override():
    custom = ["northstar"]
    assert wfg.is_chain("Northstar Demo Bistro", blacklist=custom)
    # A real chain is NOT filtered when the custom list omits it.
    assert not wfg.is_chain("McDonald's Demo", blacklist=custom)


def test_default_blacklist_unchanged_by_override_call():
    custom = ["northstar"]
    wfg.is_chain("Northstar Demo Bistro", blacklist=custom)
    # Default list still works after an override call (no mutation).
    assert wfg.is_chain("McDonald's Demo")
    assert "mcdonald" in wfg.CHAIN_BLACKLIST
