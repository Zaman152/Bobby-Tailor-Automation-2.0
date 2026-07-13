"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.stores.project_cache
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.stores.project_cache import *  # noqa: F401,F403

import sys as _sys

import bobbytailor.stores.project_cache as _mod

_sys.modules[__name__] = _mod
