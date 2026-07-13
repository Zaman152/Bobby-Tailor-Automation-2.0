"""Transitional import shim (Phase 21 V3-STRUCT-01).

Real module: bobbytailor.web.app
Keeps legacy root imports working and aliases sys.modules so that
monkeypatching through either import path hits the same module object.
"""
from bobbytailor.web.app import *  # noqa: F401,F403

import sys as _sys

import bobbytailor.web.app as _mod

# Flask resolves templates/static relative to the defining module's location
# (now src/bobbytailor/web/). Repoint them at the repo root where they live.
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parent
_mod.app.template_folder = str(_ROOT / "templates")
_mod.app.static_folder = str(_ROOT / "static")

_sys.modules[__name__] = _mod


if __name__ == "__main__":
    _mod.app.run(debug=True, port=5050, use_reloader=False)
