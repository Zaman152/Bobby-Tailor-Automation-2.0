"""
Real-world takeoff measurement engine — the path to true 100% on measured items.

A *measurement* binds a named takeoff item to scale-independent geometry drawn on
a specific sheet (in PDF-point space). Given a verified drawing scale, the
quantity is computed by exact geometry — the same math a human estimator uses in
Bluebeam / PlanSwift. Because the geometry is stored independent of scale, a
scale correction recomputes every bound quantity exactly with no re-extraction.

Measurement types
------------------
- ``count``      : N point markers           → quantity = N            (EA)
- ``length``     : open polyline             → Σ segment lengths       (LF)
- ``area``       : closed polygon            → shoelace area           (SF)
- ``wall_area``  : open/closed polyline run  → length × height_ft      (SF)

All geometry is stored as ``points_pt`` — vertices in PDF points (1/72 inch).
``feet_per_point = feet_per_inch / 72``. Lengths scale linearly, areas by the
square. Two-point calibration derives the true scale from a known real distance,
which is more reliable than any printed scale notation.
"""
from __future__ import annotations

import math
import uuid
from typing import Dict, List, Optional, Sequence

POINTS_PER_INCH = 72.0

Point = Sequence[float]  # (x, y) in PDF points

VALID_TYPES = {"count", "length", "area", "wall_area"}


# ── Pure geometry (scale-independent, in points) ──────────────────────────────

def polyline_length_pt(points: List[Point]) -> float:
    """Sum of segment lengths for an open polyline (points)."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def polygon_area_pt2(points: List[Point]) -> float:
    """Shoelace area of a closed polygon (points²). Auto-closes the ring."""
    if len(points) < 3:
        return 0.0
    pts = list(points)
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    s = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def polygon_perimeter_pt(points: List[Point]) -> float:
    """Perimeter of a closed ring (points). Auto-closes."""
    if len(points) < 2:
        return 0.0
    pts = list(points)
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    return polyline_length_pt(pts)


# ── Scale ─────────────────────────────────────────────────────────────────────

def feet_per_point(feet_per_inch: float) -> float:
    return feet_per_inch / POINTS_PER_INCH


def calibrate_two_point(p1: Point, p2: Point, real_feet: float) -> Optional[float]:
    """Derive feet_per_inch from two points a known *real_feet* apart.

    Returns feet_per_inch (so it slots straight into the scale field), or None
    when the points coincide or the distance is non-positive.
    """
    if real_feet is None or real_feet <= 0:
        return None
    d_pt = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    if d_pt <= 0:
        return None
    fpp = real_feet / d_pt
    return round(fpp * POINTS_PER_INCH, 4)


# ── Measurement quantity ──────────────────────────────────────────────────────

def measurement_quantity(m: Dict, feet_per_inch: Optional[float]) -> Optional[float]:
    """Exact quantity for a single measurement at *feet_per_inch*.

    Counts are scale-independent. Length/area/wall_area require a positive scale;
    return None when scale is missing so the UI can flag "needs scale".
    """
    mtype = m.get("measure_type")
    pts = m.get("points_pt") or []

    if mtype == "count":
        # Count markers: prefer an explicit marker list, else vertex count.
        n = m.get("count")
        if n is None:
            n = len(pts)
        return float(n)

    if not feet_per_inch or feet_per_inch <= 0:
        return None
    fpp = feet_per_point(feet_per_inch)

    if mtype == "length":
        return round(polyline_length_pt(pts) * fpp, 2)
    if mtype == "area":
        return round(polygon_area_pt2(pts) * fpp * fpp, 2)
    if mtype == "wall_area":
        height = float(m.get("height_ft") or 0)
        run_pt = (polygon_perimeter_pt(pts) if m.get("closed")
                  else polyline_length_pt(pts))
        return round(run_pt * fpp * height, 2)
    return None


def recompute_measurement(m: Dict) -> Dict:
    """Return *m* with its ``quantity`` recomputed from its own ``feet_per_inch``."""
    m = dict(m)
    m["quantity"] = measurement_quantity(m, m.get("feet_per_inch"))
    return m


def new_measurement(item: str, unit: str, measure_type: str, sheet: str,
                    points_pt: List[Point], feet_per_inch: Optional[float] = None,
                    **extra) -> Dict:
    """Construct a measurement dict with a stable id and computed quantity."""
    if measure_type not in VALID_TYPES:
        raise ValueError(f"invalid measure_type: {measure_type!r}")
    m = {
        "id": extra.pop("id", None) or uuid.uuid4().hex[:12],
        "item": item,
        "unit": unit,
        "measure_type": measure_type,
        "sheet": sheet,
        "points_pt": [list(p) for p in points_pt],
        "feet_per_inch": feet_per_inch,
        "source": extra.pop("source", "user"),
        "verified": extra.pop("verified", True),
    }
    m.update(extra)
    m["quantity"] = measurement_quantity(m, feet_per_inch)
    return m


# ── Aggregation: bound measurements → item quantities ─────────────────────────

def aggregate_measurements(measurements: List[Dict]) -> Dict[str, Dict]:
    """Roll measurements up per (item, unit) → {quantity, unit, line_count}.

    Only *verified* measurements with a non-None quantity contribute. Returns a
    mapping keyed by the canonical item name for easy summary override.
    """
    out: Dict[str, Dict] = {}
    for m in measurements:
        if not m.get("verified", True):
            continue
        qty = m.get("quantity")
        if qty is None:
            qty = measurement_quantity(m, m.get("feet_per_inch"))
        if qty is None:
            continue
        item = (m.get("item") or "").strip()
        if not item:
            continue
        key = item.lower()
        entry = out.setdefault(key, {
            "item": item, "unit": m.get("unit", ""),
            "quantity": 0.0, "line_count": 0, "sheets": set(),
            "auto": True,   # AND of contributing rows: pipeline-auto vs human
        })
        entry["quantity"] += float(qty)
        entry["line_count"] += 1
        # "auto" = produced by the automatic pipeline (high-confidence scale), as
        # opposed to a human-drawn measurement; lets the UI badge it "Auto".
        if m.get("source") not in ("auto", "geometry"):
            entry["auto"] = False
        if m.get("sheet"):
            entry["sheets"].add(m["sheet"])
    for entry in out.values():
        entry["quantity"] = round(entry["quantity"], 2)
        entry["sheets"] = sorted(entry["sheets"])
    return out
