"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.scrape.sheet_preview
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.scrape.sheet_preview import *  # noqa: F401,F403
from bobbytailor.scrape.sheet_preview import (  # noqa: F401
    _match_png_to_page_id,
    _normalize_sheet_key,
)

import sys as _sys

import bobbytailor.scrape.sheet_preview as _mod

_sys.modules[__name__] = _mod
