"""
Session-level module registration to prevent sys.modules pollution.

test_pipeline_parity.py (and test_takeoff_pipeline.py / test_sheet_pass_matrix.py)
set up module-level stubs via sys.modules.setdefault() at import time for
solo-run hermeticity. If the real modules are already registered in sys.modules
before those stubs are applied, setdefault() becomes a no-op and the real
modules are preserved for all other test modules in the same pytest session.

Root cause example: when pytest collects test_pipeline_parity.py before a real
module is imported, its sys.modules.setdefault(
"bobbytailor.scrape.capture_manifest", MagicMock()) wins. Later,
test_scraper_pipeline.py does
`from bobbytailor.scrape.capture_manifest import RunManifest, ...` and gets
MagicMock attributes. RunManifest(…) returns a MagicMock whose .pages attribute
is non-iterable, so scraper sees zero pages and returns all_sheets_failed.

Fix: conftest.py is loaded before any test file; pre-importing every module the
stub blocks target ensures the real modules are in sys.modules before any stub
can displace them.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile

# Keep unit tests on 3-pass floor_plan unless explicitly testing high-accuracy mode.
os.environ.setdefault("TAKEOFF_ACCURACY_MODE", "standard")

# Phase 21 learning store (21-09): the verify/scale/measurements endpoints now
# capture corrections into the learning DB in-request. LEARNING_DB_PATH is read
# once at bobbytailor.learning.store import time, so isolate the WHOLE test
# session onto a throwaway DB — endpoint tests must never touch the real
# output/learning.db. Tests needing per-test isolation additionally monkeypatch
# store.LEARNING_DB_PATH (see tests/test_learning_store.py fixture).
os.environ.setdefault(
    "LEARNING_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="bt-test-learning-"), "learning.db"),
)

# Make model routing deterministic regardless of test import order. Some test
# modules mock `config` via sys.modules.setdefault(); if the real config is
# imported first (by any earlier test), those mocks become no-ops. Setting the
# env here ensures the REAL config yields the same distinct Haiku/Sonnet values
# the mocks expect, so model-routing assertions pass under any collection order.
os.environ.setdefault("CLAUDE_MODEL", "claude-haiku-4-5")
os.environ.setdefault("CLAUDE_MODEL_SCHEDULES", "claude-sonnet-4-5")

# Phase 21 MODEL_ROUTING v2 slugs (21-05). Distinct throwaway values so routing
# tests can tell every route apart (semantic vs dense vs classify vs default)
# under any collection order. CLASSIFY gets a suffixed value because its real
# default equals CLAUDE_MODEL — identical pins would make the routes
# indistinguishable in assertions.
os.environ.setdefault("CLAUDE_MODEL_SEMANTIC", "claude-sonnet-5")
os.environ.setdefault("CLAUDE_MODEL_DENSE", "claude-opus-4-8")
os.environ.setdefault("CLAUDE_MODEL_ESCALATION", "claude-fable-5")
os.environ.setdefault("CLAUDE_MODEL_CLASSIFY", "claude-haiku-4-5-classify")

# Phase 21 ensemble voting + budget guard (21-11). Pin N=3 and the default
# $10 cap so run_ensemble fan-out counts and ensemble_settings() assertions
# are deterministic under any collection order / developer .env content.
os.environ.setdefault("ENSEMBLE_N", "3")
os.environ.setdefault("API_BUDGET_PER_RUN_USD", "10.0")


def _ensure_real(name: str) -> None:
    """Import *name* into sys.modules if it is not already registered.

    Uses importlib rather than a bare import so that optional or
    environment-specific modules can fail silently without breaking the
    test session startup.
    """
    if name not in sys.modules:
        try:
            importlib.import_module(name)
        except Exception:
            # Module may be unavailable in certain CI environments;
            # parity stubs will fill the gap as intended.
            pass


# Pre-register the real package modules that test_pipeline_parity /
# test_takeoff_pipeline / test_sheet_pass_matrix stub at module level via
# sys.modules.setdefault() (solo-run hermeticity). Pre-importing the real
# modules here makes every one of those setdefault() calls a no-op under
# full-suite collection, so no stub can leak into other test modules
# regardless of collection order. _ensure_real swallows import errors, so
# environment-dependent modules (config crash-fails on missing env vars,
# browser needs playwright) degrade gracefully to the stubs when absent.
for _name in (
    "bobbytailor.config",
    "bobbytailor.vision.claude_analyzer",
    "bobbytailor.scrape.capture_manifest",
    "bobbytailor.scrape.linked_sheets",
    "bobbytailor.scrape.browser",
    "bobbytailor.scrape.sheet_preview",
    "bobbytailor.stores.stackct_store",
    "bobbytailor.pipeline.cross_references",
    "bobbytailor.pipeline.reporter",
):
    _ensure_real(_name)
