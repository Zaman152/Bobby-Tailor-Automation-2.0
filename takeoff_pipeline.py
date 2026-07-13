"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.pipeline.takeoff_pipeline
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.pipeline.takeoff_pipeline import *  # noqa: F401,F403
from bobbytailor.pipeline.takeoff_pipeline import (  # noqa: F401
    _build_count_hint,
    _build_measure_hint,
    _manifest_wall_height,
)

import sys as _sys

import bobbytailor.pipeline.takeoff_pipeline as _mod

_sys.modules[__name__] = _mod
