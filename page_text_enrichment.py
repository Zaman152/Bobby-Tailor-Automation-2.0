"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.pipeline.page_text_enrichment
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.pipeline.page_text_enrichment import *  # noqa: F401,F403

import sys as _sys

import bobbytailor.pipeline.page_text_enrichment as _mod

_sys.modules[__name__] = _mod
