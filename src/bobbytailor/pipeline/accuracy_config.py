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


def count_tiling_enabled() -> bool:
    """Whether to run an extra tiled recount pass for missed manifest count-objects.

    Tiling improves recall of small repeated symbols on dense sheets but adds API
    cost and carries a boundary double/under-count risk, so it is gated behind a
    flag (default OFF) and validated against the benchmark before enabling.

    Environment: COUNT_TILING=1|true|on to enable.
    """
    return (os.getenv("COUNT_TILING") or "").strip().lower() in ("1", "true", "on", "yes")


def count_tiling_grid() -> tuple:
    """Grid (cols, rows) for tiled recount. Env COUNT_TILING_GRID="2x2" (default)."""
    raw = (os.getenv("COUNT_TILING_GRID") or "2x2").lower()
    try:
        c, r = raw.split("x")
        return max(1, int(c)), max(1, int(r))
    except (ValueError, AttributeError):
        return 2, 2
