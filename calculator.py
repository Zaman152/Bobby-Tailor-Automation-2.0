"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.pipeline.calculator
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.pipeline.calculator import *  # noqa: F401,F403
from bobbytailor.pipeline.calculator import (  # noqa: F401
    _calculate_from_component,
    _calculate_from_measurement,
    _calculate_from_room,
    _calculate_from_schedule,
    _parse_numeric,
    _schedule_is_takeoff,
)

import sys as _sys

import bobbytailor.pipeline.calculator as _mod

_sys.modules[__name__] = _mod
