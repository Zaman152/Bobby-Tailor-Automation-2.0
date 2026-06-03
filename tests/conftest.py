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
import sys


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
