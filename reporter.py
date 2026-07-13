"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.pipeline.reporter
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.pipeline.reporter import *  # noqa: F401,F403
from bobbytailor.pipeline.reporter import (  # noqa: F401
    _normalize_calculated,
    _write_calculated_csv,
    _write_takeoff_summary_csv,
)

import sys as _sys

import bobbytailor.pipeline.reporter as _mod

_sys.modules[__name__] = _mod
