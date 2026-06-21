"""
pytest config: load the hyphenated workflow-generator.py as module `wfg`.

The generator lives at the repo root with a hyphen in its name, so it cannot
be imported on the normal path. Load it explicitly here so every test module
can do `from .conftest import wfg`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "wfg",
    _REPO_ROOT / "workflow-generator.py",
)
assert _SPEC is not None and _SPEC.loader is not None, "could not load workflow-generator.py"
wfg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(wfg)
