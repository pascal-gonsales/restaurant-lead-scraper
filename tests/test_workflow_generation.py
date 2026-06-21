"""Generator (9-node skeleton) tests (7 tests)."""
from __future__ import annotations

import json

import pytest

from .conftest import wfg


def _valid_city():
    return {
        "name": "Demo City",
        "search_location": "Demo City",
        "queries": ["restaurant", "resto bar", "traiteur"],
        "min_reviews": 50,
        "min_rating": 3.5,
        "max_rating": 4.7,
        "sheet_id": "YOUR_GOOGLE_SHEET_ID_HERE",
    }


def test_generate_returns_valid_dict():
    wf = wfg.generate_workflow(_valid_city())
    assert isinstance(wf, dict)
    assert "nodes" in wf and "connections" in wf
    assert wf["settings"] == {"executionOrder": "v1"}


def test_node_count_is_pinned_to_nine():
    wf = wfg.generate_workflow(_valid_city())
    assert len(wf["nodes"]) == 9


def test_no_dangling_node_references():
    wf = wfg.generate_workflow(_valid_city())
    names = {n["name"] for n in wf["nodes"]}
    for source, conn in wf["connections"].items():
        assert source in names
        for output in conn.get("main", []):
            for edge in output:
                assert edge["node"] in names


def test_connections_reference_real_nodes():
    wf = wfg.generate_workflow(_valid_city())
    names = {n["name"] for n in wf["nodes"]}
    expected = {
        "Start", "Webhook Trigger", "Configuration", "Generate Search URLs",
        "Search Page 1", "Extract Page 1", "Quality Filter + Score",
        "Get Details", "Save to Sheet",
    }
    assert names == expected


def test_output_is_json_serializable():
    wf = wfg.generate_workflow(_valid_city())
    blob = json.dumps(wf)
    assert json.loads(blob)["name"]


def test_missing_required_field_raises_keyerror():
    bad = _valid_city()
    del bad["sheet_id"]
    with pytest.raises(KeyError):
        wfg.generate_workflow(bad)


def test_placeholder_credentials_present():
    wf = wfg.generate_workflow(_valid_city())
    blob = json.dumps(wf)
    assert "YOUR_GOOGLE_PLACES_API_KEY_HERE" in blob
    assert "YOUR_GOOGLE_SHEET_ID_HERE" in blob
    assert "YOUR_CREDENTIAL_ID" in blob
