"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.vision.claude_analyzer
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.vision.claude_analyzer import *  # noqa: F401,F403

import sys as _sys

import bobbytailor.vision.claude_analyzer as _mod

_sys.modules[__name__] = _mod
