"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.deterministic.schedule_extraction
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.deterministic.schedule_extraction import *  # noqa: F401,F403
from bobbytailor.deterministic.schedule_extraction import (  # noqa: F401
    _material_columns,
    _tag_column,
    _tag_tokens,
)

import sys as _sys

import bobbytailor.deterministic.schedule_extraction as _mod

_sys.modules[__name__] = _mod
