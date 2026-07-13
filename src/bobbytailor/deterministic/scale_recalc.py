"""
Deterministic scale recomputation — the heart of the verify-to-100% workflow.

Vector geometry is captured ONCE as scale-independent point measures
(:class:`geometry_takeoff.RawGeometry`). A human verifies/corrects the drawing
scale per sheet; this module converts those raw points into exact real-world
quantities for the supplied scale. No vision, no API, no re-extraction — pure math.

Conversions (PDF: 72 points per inch):
  feet_per_point = feet_per_inch / 72
  length_ft = length_points  × feet_per_point
  area_sf   = area_points²    × feet_per_point²
"""
from __future__ import annotations

from typing import Dict, Optional

POINTS_PER_INCH = 72.0


def feet_per_point(feet_per_inch: float) -> float:
    return feet_per_inch / POINTS_PER_INCH


def recompute(raw: Dict, feet_per_inch: Optional[float]) -> Dict:
    """Convert raw point measures to real-world quantities at *feet_per_inch*.

    Returns a dict with footprint_sf / total_linework_lf / long_run_lf
    (None when the scale is missing/invalid). Long-run is recomputed from the
    stored long_run_pt; if a finer breakdown were stored it would convert the
    same way. All values rounded to 1 decimal.
    """
    if not feet_per_inch or feet_per_inch <= 0 or not raw:
        return {"footprint_sf": None, "total_linework_lf": None, "long_run_lf": None}
    fpp = feet_per_point(feet_per_inch)
    fp2 = float(raw.get("footprint_pt2") or 0)
    tot = float(raw.get("total_linework_pt") or 0)
    lng = float(raw.get("long_run_pt") or 0)
    return {
        "footprint_sf": round(fp2 * fpp * fpp, 1),
        "total_linework_lf": round(tot * fpp, 1),
        "long_run_lf": round(lng * fpp, 1),
        "width_ft": round(float(raw.get("width_pt") or 0) * fpp, 1),
        "height_ft": round(float(raw.get("height_pt") or 0) * fpp, 1),
    }


def apply_overrides(calibration: Dict, overrides: Dict[str, float]) -> Dict:
    """Apply per-sheet scale overrides to a calibration table and recompute.

    Args:
        calibration: ``{"sheets": [ {sheet, feet_per_inch, raw, ...}, ... ]}``
        overrides: ``{sheet_name: feet_per_inch}`` — user-verified scales.

    Returns the updated calibration (new ``feet_per_inch``, ``measured`` values,
    and ``scale_source='user_verified'`` for overridden sheets). Pure; does not
    write to disk.
    """
    sheets = calibration.get("sheets") or []
    for s in sheets:
        name = s.get("sheet")
        if name in overrides and overrides[name]:
            try:
                fpi = float(overrides[name])
            except (TypeError, ValueError):
                continue
            if fpi <= 0:
                continue
            s["feet_per_inch"] = fpi
            s["scale_source"] = "user_verified"
            s["scale_confidence"] = "high"
            s["measured"] = recompute(s.get("raw") or {}, fpi)
    return calibration
