"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.deterministic.footprint_takeoff
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.deterministic.footprint_takeoff import *  # noqa: F401,F403
from bobbytailor.deterministic.footprint_takeoff import (  # noqa: F401
    _axis_dims,
    _parse_feet,
)

import sys as _sys

import bobbytailor.deterministic.footprint_takeoff as _mod

_sys.modules[__name__] = _mod
