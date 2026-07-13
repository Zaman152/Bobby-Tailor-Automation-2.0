"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.pipeline.aggregator
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.pipeline.aggregator import *  # noqa: F401,F403

import sys as _sys

import bobbytailor.pipeline.aggregator as _mod

_sys.modules[__name__] = _mod
