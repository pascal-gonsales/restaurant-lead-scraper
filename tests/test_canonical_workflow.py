"""Canonical 19-node scraper-workflow.json tests (7 tests)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from .conftest import wfg

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CANONICAL = _REPO_ROOT / "scraper-workflow.json"

# Drift extractor: pull (HOT, WARM) thresholds out of any tier ternary,
# whether it reads `score` or `finalScore`.
_TIER_RX = re.compile(
    r"(?:final[Ss]core|score)\s*>=\s*(\d+)\s*\?\s*'HOT'\s*:\s*"
    r"(?:final[Ss]core|score)\s*>=\s*(\d+)\s*\?\s*'WARM'"
)


@pytest.fixture(scope="module")
def canonical_workflow():
    assert _CANONICAL.exists(), "scraper-workflow.json missing"
    return json.loads(_CANONICAL.read_text(encoding="utf-8"))


def test_canonical_file_exists(canonical_workflow):
    assert canonical_workflow["name"] == "Restaurant Lead Scraper v2"
    assert canonical_workflow["settings"] == {"executionOrder": "v1"}


def test_canonical_node_count_is_nineteen(canonical_workflow):
    assert len(canonical_workflow["nodes"]) == 19


def test_canonical_expected_node_names(canonical_workflow):
    names = [n["name"] for n in canonical_workflow["nodes"]]
    expected = [
        "Start", "Webhook Trigger", "Configuration", "Generate Search URLs",
        "Search Page 1", "Extract Page 1", "Has Page 2?", "Wait for Page 2",
        "Prep Page 2 URLs", "Search Page 2", "Merge Pages",
        "Quality Filter + Score", "Get Details", "Combine Details",
        "Fetch Homepage", "Extract Emails", "Multi-Location + Format",
        "Save to Sheet", "Summary Report",
    ]
    assert names == expected


def _node_js(workflow, name):
    for n in workflow["nodes"]:
        if n["name"] == name:
            return n.get("parameters", {}).get("jsCode", "")
    raise AssertionError(f"node not found: {name}")


def test_quality_filter_tiers_match_python(canonical_workflow):
    js = _node_js(canonical_workflow, "Quality Filter + Score")
    m = _TIER_RX.search(js)
    assert m is not None
    assert int(m.group(1)) == wfg.TIER_HOT
    assert int(m.group(2)) == wfg.TIER_WARM


def test_multi_location_final_tiers_match_python(canonical_workflow):
    js = _node_js(canonical_workflow, "Multi-Location + Format")
    m = _TIER_RX.search(js)
    assert m is not None
    assert int(m.group(1)) == wfg.TIER_HOT
    assert int(m.group(2)) == wfg.TIER_WARM


def test_no_tier_ternary_anywhere_drifts(canonical_workflow):
    # Every tier ternary in every code node must equal the Python constants.
    found_any = False
    for node in canonical_workflow["nodes"]:
        js = node.get("parameters", {}).get("jsCode", "")
        for m in _TIER_RX.finditer(js):
            found_any = True
            assert int(m.group(1)) == wfg.TIER_HOT, node["name"]
            assert int(m.group(2)) == wfg.TIER_WARM, node["name"]
    assert found_any, "expected at least one tier ternary in the canonical workflow"


def test_no_real_credentials_only_placeholders(canonical_workflow):
    blob = json.dumps(canonical_workflow)
    assert "YOUR_GOOGLE_PLACES_API_KEY_HERE" in blob
    assert "YOUR_GOOGLE_SHEET_ID_HERE" in blob
    assert "YOUR_CREDENTIAL_ID" in blob
    # No raw Google key prefix anywhere.
    assert "AIza" not in blob
