"""
Vector-geometry take-off — measure REAL lengths/areas from a CAD-exported PDF.

Most commercial construction plans are vector PDFs: PyMuPDF exposes the actual
line/rect/curve coordinates (in PDF points). With a known drawing scale
(feet-per-point) those coordinates convert to real-world feet — the same thing a
human does with takeoff software, but read straight from the geometry instead of
guessed by vision.

WHAT THIS DOES (honestly):
  - resolve_scale(): determine feet-per-point for a page from, in priority order,
      (1) an explicit override (user/manifest-supplied scale — most reliable),
      (2) the dominant printed scale notation on the sheet,
      (3) self-calibration from the drawing's own dimension strings.
    Each path returns a CONFIDENCE; only (1) and a clean single-scale (2) are
    treated as high confidence.
  - measure_geometry(): compute candidate quantities from the geometry —
      total linework length (LF), and the building footprint area (SF) via a
      density-trimmed extent. These are MEASURED CANDIDATES, not gospel.

WHAT THIS DOES NOT DO:
  - It does not semantically segment the drawing (which polyline is "CMU wall"
    vs a gridline). That binding is left to the manifest/AI + human verification.
  - It does not guarantee correctness on multi-scale sheets or messy drawings;
    low-confidence results are flagged for review rather than trusted blindly.
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

POINTS_PER_INCH = 72.0


@dataclass
class ScaleResult:
    feet_per_point: Optional[float]
    confidence: str            # high | medium | low | none
    method: str                # override | printed_scale | dimension_calibration | none
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _segments(page) -> List[Tuple[float, float, float, float]]:
    """All straight line segments on the page as (x0,y0,x1,y1) in PDF points."""
    out = []
    for path in page.get_drawings():
        for it in path["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                out.append((a.x, a.y, b.x, b.y))
            elif it[0] == "re":
                r = it[1]
                out.extend([
                    (r.x0, r.y0, r.x1, r.y0),
                    (r.x1, r.y0, r.x1, r.y1),
                    (r.x1, r.y1, r.x0, r.y1),
                    (r.x0, r.y1, r.x0, r.y0),
                ])
    return out


def _seg_len(s) -> float:
    return ((s[0] - s[2]) ** 2 + (s[1] - s[3]) ** 2) ** 0.5


# ── Scale resolution ───────────────────────────────────────────────────────────

def resolve_scale(
    page,
    scale_text: Optional[str] = None,
    override_feet_per_inch: Optional[float] = None,
) -> ScaleResult:
    """Determine feet-per-point for *page*. See module docstring for priority."""
    # (1) Explicit override — most reliable.
    if override_feet_per_inch and override_feet_per_inch > 0:
        return ScaleResult(
            feet_per_point=override_feet_per_inch / POINTS_PER_INCH,
            confidence="high", method="override",
            detail=f"{override_feet_per_inch} ft per inch (supplied)",
        )

    # (2) Printed scale notation, recovered with stacked-fraction awareness and
    #     snapped to the standard scale ladder. Char-geometry (rawdict) is the
    #     ground truth; the vision-supplied scale string is only a fallback hint.
    #     Mangled readings (e.g. 1/8 collapsed to "18") are rejected by the ladder
    #     snap instead of producing a wildly wrong feet-per-inch.
    from scale_extraction import dominant_scale
    fpi, conf, detail = dominant_scale(page, scale_text)
    if fpi:
        return ScaleResult(
            feet_per_point=fpi / POINTS_PER_INCH,
            confidence=conf, method="printed_scale",
            detail=detail,
        )

    # (3) Self-calibration from dimension strings — least reliable.
    fpp = _calibrate_from_dimensions(page)
    if fpp:
        return ScaleResult(
            feet_per_point=fpp, confidence="low", method="dimension_calibration",
            detail=f"{fpp * POINTS_PER_INCH:.1f} ft/in (calibrated from dimensions)",
        )

    return ScaleResult(feet_per_point=None, confidence="none", method="none")


def _collect_printed_scales(text: str) -> List[Tuple[float, int]]:
    """Find printed scale notations -> [(feet_per_inch, occurrences)] desc by count.

    Delegates to the ladder-snapping text extractor so collapsed stacked fractions
    (e.g. "1/8" read as "18") are recovered/rejected rather than trusted blindly.
    """
    from scale_extraction import extract_scales_from_text
    return extract_scales_from_text(text)


def _calibrate_from_dimensions(page) -> Optional[float]:
    """Estimate feet-per-point by matching dimension strings to nearby segments."""
    import re

    dim_re = re.compile(r"^(\d{1,3})'\s*-?\s*(\d{1,2})?\"?$")
    dims = []
    for w in page.get_text("words"):
        m = dim_re.match(w[4].strip())
        if m:
            ft = int(m.group(1)) + (int(m.group(2)) / 12 if m.group(2) else 0)
            if ft >= 8:  # ignore tiny detail dims
                dims.append(((w[0] + w[2]) / 2, (w[1] + w[3]) / 2, ft))
    if len(dims) < 3:
        return None

    aligned = [s for s in _segments(page)
               if (abs(s[0] - s[2]) < 2 or abs(s[1] - s[3]) < 2) and _seg_len(s) > 20]
    if not aligned:
        return None

    ratios = []
    for cx, cy, ft in dims:
        best = None
        best_d = 1e9
        for s in aligned:
            mx, my = (s[0] + s[2]) / 2, (s[1] + s[3]) / 2
            d = ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5
            L = _seg_len(s)
            r = ft / L
            if 0.05 < r < 2.0 and d < best_d:
                best_d, best = d, r
        if best:
            ratios.append(best)
    if len(ratios) < 3:
        return None
    return statistics.median(ratios)


# ── Measurement ─────────────────────────────────────────────────────────────────

@dataclass
class RawGeometry:
    """Scale-INDEPENDENT geometry measures in PDF points.

    These are captured once; multiplying by the (scale/72) factor recomputes exact
    real-world quantities for ANY scale the user later verifies — no vision re-run.
    """
    footprint_pt2: float      # bounding extent area in points²
    total_linework_pt: float  # sum of all segment lengths in points
    long_run_pt: float        # sum of segments ≥ 5ft-equivalent in points
    width_pt: float
    height_pt: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GeometryMeasurement:
    scale: dict
    footprint_sf: Optional[float]
    total_linework_lf: Optional[float]
    long_run_lf: Optional[float]
    confidence: str
    needs_review: bool
    raw: Optional[dict] = None  # RawGeometry.to_dict() — enables instant rescale
    page_width_pt: Optional[float] = None   # for UI px<->pt mapping
    page_height_pt: Optional[float] = None
    # Per-viewport breakdown on multi-scale sheets (each detail measured with its
    # OWN scale). None/[] means the whole sheet used a single scale. The top-level
    # fields above mirror the dominant (main-plan) viewport.
    viewports: Optional[list] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _raw_from_segments(segs, trim_pct: float, fpp: Optional[float]) -> RawGeometry:
    """Scale-independent raw measures for a set of segments (captured once)."""
    lens = [_seg_len(s) for s in segs]
    total_pt = sum(lens)
    xs = sorted([s[0] for s in segs] + [s[2] for s in segs])
    ys = sorted([s[1] for s in segs] + [s[3] for s in segs])

    def _pct(vals, p):
        i = min(len(vals) - 1, max(0, int(len(vals) * p / 100)))
        return vals[i]

    w_pt = _pct(xs, 100 - trim_pct) - _pct(xs, trim_pct)
    h_pt = _pct(ys, 100 - trim_pct) - _pct(ys, trim_pct)
    # "long run" threshold is 5ft; in points that depends on scale, so when we have
    # a scale use it, else fall back to a generous point threshold so the raw value
    # is still meaningful and recomputable.
    long_thresh_pt = (5 / fpp) if fpp else 36.0
    long_pt = sum(L for L in lens if L >= long_thresh_pt)
    return RawGeometry(
        footprint_pt2=round(w_pt * h_pt, 3),
        total_linework_pt=round(total_pt, 3),
        long_run_pt=round(long_pt, 3),
        width_pt=round(w_pt, 3),
        height_pt=round(h_pt, 3),
    )


def _measure_single(sc: ScaleResult, segs, pw, ph, trim_pct: float) -> GeometryMeasurement:
    """Whole-sheet measurement with one scale (override / single printed scale)."""
    if not segs:
        return GeometryMeasurement(sc.to_dict(), None, None, None,
                                   sc.confidence or "none", True, None,
                                   page_width_pt=pw, page_height_pt=ph)
    fpp = sc.feet_per_point
    raw = _raw_from_segments(segs, trim_pct, fpp)
    if not fpp:
        return GeometryMeasurement(sc.to_dict(), None, None, None,
                                   "none", True, raw.to_dict(),
                                   page_width_pt=pw, page_height_pt=ph)
    from scale_recalc import recompute  # local import avoids cycle
    vals = recompute(raw.to_dict(), fpp * POINTS_PER_INCH)
    # AUTO-ACCEPT: when the scale was read cleanly and snapped to the standard
    # ladder (high confidence), the conversion is exact, so the measured quantity
    # is accepted automatically. Medium/low-confidence scales stay flagged for a
    # human to confirm.
    return GeometryMeasurement(
        scale=sc.to_dict(),
        footprint_sf=vals["footprint_sf"],
        total_linework_lf=vals["total_linework_lf"],
        long_run_lf=vals["long_run_lf"],
        confidence=sc.confidence,
        needs_review=(sc.confidence != "high"),
        raw=raw.to_dict(),
        page_width_pt=pw,
        page_height_pt=ph,
    )


def _measure_viewports(callouts, segs, pw, ph, trim_pct: float) -> Optional[GeometryMeasurement]:
    """Bind geometry to per-viewport scales on a multi-scale sheet.

    Each segment is assigned to the nearest scale-callout anchor, every viewport is
    measured with ITS OWN scale, and the dominant (largest real-area) viewport —
    the main plan that drives most quantities — populates the top-level fields.
    """
    from scale_recalc import recompute  # local import avoids cycle

    buckets: List[List] = [[] for _ in callouts]
    for s in segs:
        mx, my = (s[0] + s[2]) / 2.0, (s[1] + s[3]) / 2.0
        best_i, best_d = 0, float("inf")
        for i, c in enumerate(callouts):
            d = (mx - c["x"]) ** 2 + (my - c["y"]) ** 2
            if d < best_d:
                best_d, best_i = d, i
        buckets[best_i].append(s)

    viewports: List[dict] = []
    for c, vsegs in zip(callouts, buckets):
        if not vsegs:
            continue
        fpi = c["feet_per_inch"]
        fpp = fpi / POINTS_PER_INCH
        raw = _raw_from_segments(vsegs, trim_pct, fpp)
        vals = recompute(raw.to_dict(), fpi)
        viewports.append({
            "feet_per_inch": fpi,
            "anchor": {"x": round(c["x"], 1), "y": round(c["y"], 1)},
            "segment_count": len(vsegs),
            "raw": raw.to_dict(),
            "footprint_sf": vals["footprint_sf"],
            "total_linework_lf": vals["total_linework_lf"],
            "long_run_lf": vals["long_run_lf"],
            "dominant": False,
        })
    if not viewports:
        return None

    dom = max(viewports, key=lambda v: (v["footprint_sf"] or 0.0,
                                        v["total_linework_lf"] or 0.0))
    dom["dominant"] = True
    fpi = dom["feet_per_inch"]
    total_segs = sum(v["segment_count"] for v in viewports)
    # Reliability of the dominant SCALE = geometry sharing that scale (multiple
    # viewports at the same scale should not penalise confidence). Confidence is
    # high when the dominant scale clearly owns the sheet, else medium so a human
    # double-checks the split.
    scale_segs = sum(v["segment_count"] for v in viewports
                     if v["feet_per_inch"] == fpi)
    share = scale_segs / total_segs if total_segs else 0
    n_scales = len({v["feet_per_inch"] for v in viewports})
    conf = "high" if (n_scales == 1 or share >= 0.6) else "medium"
    sc = ScaleResult(
        feet_per_point=fpi / POINTS_PER_INCH,
        confidence=conf,
        method="printed_scale_viewport",
        detail=(f"{fpi:g} ft/in — dominant of {len(viewports)} viewports, "
                f"{n_scales} scale(s) (geometry share {share:.0%})"),
    )
    return GeometryMeasurement(
        scale=sc.to_dict(),
        footprint_sf=dom["footprint_sf"],
        total_linework_lf=dom["total_linework_lf"],
        long_run_lf=dom["long_run_lf"],
        confidence=conf,
        needs_review=(conf != "high"),  # auto-accept clean, dominant-scale sheets
        raw=dom["raw"],
        page_width_pt=pw,
        page_height_pt=ph,
        viewports=viewports,
    )


def measure_geometry(
    page,
    scale_text: Optional[str] = None,
    override_feet_per_inch: Optional[float] = None,
    trim_pct: float = 0.5,
) -> GeometryMeasurement:
    """Measure candidate quantities from page geometry. Always confidence-flagged.

    On multi-scale sheets (>=2 distinct printed scale callouts and no explicit
    override) geometry is bound per-viewport so each detail is measured with its
    own scale; otherwise a single sheet scale is used.
    """
    try:
        pw, ph = float(page.rect.width), float(page.rect.height)
    except Exception:
        pw = ph = None
    segs = _segments(page)

    # Explicit override (user/manifest) or no geometry -> single whole-sheet scale.
    if (override_feet_per_inch and override_feet_per_inch > 0) or not segs:
        return _measure_single(
            resolve_scale(page, scale_text, override_feet_per_inch),
            segs, pw, ph, trim_pct,
        )

    # Multi-scale sheet: bind geometry to per-viewport scales.
    try:
        from scale_extraction import extract_scale_callouts
        callouts = extract_scale_callouts(page)
    except Exception:
        callouts = []
    if len(callouts) >= 2:
        m = _measure_viewports(callouts, segs, pw, ph, trim_pct)
        if m is not None:
            return m

    # Single dominant scale (0/1 callout, or no viewport produced geometry).
    return _measure_single(
        resolve_scale(page, scale_text, override_feet_per_inch),
        segs, pw, ph, trim_pct,
    )
