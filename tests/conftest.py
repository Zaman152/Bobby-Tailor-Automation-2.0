"""
Session-level module registration to prevent sys.modules pollution.

test_pipeline_parity.py sets up module-level stubs via sys.modules.setdefault()
at import time. If real modules are already registered in sys.modules before
those stubs are applied, setdefault() becomes a no-op and the real modules are
preserved for all other test modules in the same pytest session.

Root cause: when pytest collects test_pipeline_parity.py first (alphabetical),
its module-level code runs sys.modules.setdefault("capture_manifest", MagicMock()).
Later, test_scraper_pipeline.py does `from capture_manifest import RunManifest, ...`
and gets MagicMock attributes. RunManifest(…) returns a MagicMock whose .pages
attribute is non-iterable, so scraper sees zero pages and returns all_sheets_failed.

Fix: conftest.py is loaded before any test file; pre-importing capture_manifest
ensures the real class is in sys.modules before parity stubs can displace it.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

# Phase 21 transition (V3-STRUCT-01): modules live in src/bobbytailor/ with
# root-level import shims. Ensure the repo root (shims) is importable, and
# fall back to a direct src/ path insert when the bobbytailor package is not
# installed (e.g. fresh checkout without `pip install -e .`).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
try:
    import bobbytailor  # noqa: F401
except ImportError:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

# Keep unit tests on 3-pass floor_plan unless explicitly testing high-accuracy mode.
os.environ.setdefault("TAKEOFF_ACCURACY_MODE", "standard")

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


# Pre-register modules that test_pipeline_parity stubs at module level via
# sys.modules.setdefault(). Both are pure-Python with only stdlib dependencies,
# so these imports are always safe in any test environment.
#
#   capture_manifest — needed by test_scraper_pipeline.py and test_scraper_*.py
#   linked_sheets    — needed by test_linked_sheets.py
_ensure_real("capture_manifest")
_ensure_real("linked_sheets")
