"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.scrape.linked_sheets
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.scrape.linked_sheets import *  # noqa: F401,F403

import sys as _sys

import bobbytailor.scrape.linked_sheets as _mod

_sys.modules[__name__] = _mod
