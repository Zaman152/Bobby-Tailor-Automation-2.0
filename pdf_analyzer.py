"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.pipeline.pdf_analyzer
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.pipeline.pdf_analyzer import *  # noqa: F401,F403
from bobbytailor.pipeline.pdf_analyzer import (  # noqa: F401
    _is_noise_sheet_candidate,
    _sheet_name_from_doc,
)

import sys as _sys

import bobbytailor.pipeline.pdf_analyzer as _mod

_sys.modules[__name__] = _mod
