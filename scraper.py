"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.scrape.scraper
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.scrape.scraper import *  # noqa: F401,F403
from bobbytailor.scrape.scraper import (  # noqa: F401
    _discover_and_add_linked_sheets,
    _safe_sheet_filename,
)

import sys as _sys

import bobbytailor.scrape.scraper as _mod

_sys.modules[__name__] = _mod
