"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.web.app
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.web.app import create_app
from config import OUTPUT_DIR  # re-export for tests patching app.OUTPUT_DIR

import sys as _sys
from pathlib import Path as _Path

import bobbytailor.web.app as _mod

app = create_app()

_ROOT = _Path(__file__).resolve().parent
app.template_folder = str(_ROOT / "templates")
app.static_folder = str(_ROOT / "static")

# Expose app on the shim module for `from app import app`
_mod.app = app

_sys.modules[__name__] = _mod

if __name__ == "__main__":
    app.run(debug=True, port=5050, use_reloader=False)
