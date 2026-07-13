"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.pipeline.cross_references
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.pipeline.cross_references import *  # noqa: F401,F403

import sys as _sys

import bobbytailor.pipeline.cross_references as _mod

_sys.modules[__name__] = _mod
