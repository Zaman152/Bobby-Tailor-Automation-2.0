"""
Takeoff accuracy mode — controls model routing and optional verify passes.

Environment:
  TAKEOFF_ACCURACY_MODE=high|standard  (default: high)
"""
import os

MODES = frozenset({"standard", "high"})


def takeoff_accuracy_mode() -> str:
    raw = (os.getenv("TAKEOFF_ACCURACY_MODE") or "high").strip().lower()
    return raw if raw in MODES else "high"


def is_high_accuracy_mode() -> bool:
    return takeoff_accuracy_mode() == "high"
