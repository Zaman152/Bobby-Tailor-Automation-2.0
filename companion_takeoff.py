"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.devtools.companion_takeoff
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.devtools.companion_takeoff import *  # noqa: F401,F403
from bobbytailor.devtools.companion_takeoff import (  # noqa: F401
    _parse_legend_from_text,
    _table_to_rows,
)

import sys as _sys

import bobbytailor.devtools.companion_takeoff as _mod

_sys.modules[__name__] = _mod
