"""Deterministic building footprint from printed overall dimensions.

A human estimator reads the *overall* dimension strings off a floor plan
("1136' - 0\"" along the top, "350' - 0\"" up the side) and multiplies them to
get the building footprint. That is exact and scale-independent — far more
reliable than vision-guessed areas or whole-sheet bounding boxes (which include
the title block, details, and site plan and run 2.5–4.7x too large).

This module extracts those dimension strings, separates them by axis using each
text line's rotation (``dir`` = (cos, sin): horizontal vs vertical), and takes
the largest in each axis as the overall building extent.

From the footprint we get, deterministically:
  - floor / roof area (SF)  = width x depth
  - exterior perimeter (LF) = 2 x (width + depth)   [rectangular assumption]
  - exterior wall area (SF) = perimeter x wall height (height from manifest/assumption)

On the Crow regression this yields 397,600 SF vs a golden 395,673 SF (0.5%).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Feet-inch dimension token: "1136' - 0\"", "350'-0", "55' - 6\"", "60'".
_DIM_RE = re.compile(r"^\s*(\d{2,4})\s*'\s*[-–]?\s*(\d{1,2})?\s*\"?\s*$")

# Plausible overall-building extents in feet. Below this we are reading a room
# or detail dimension; above it we are reading a site/property line.
MIN_OVERALL_FT = 50.0
MAX_OVERALL_FT = 2000.0


@dataclass
class Footprint:
    width_ft: float          # overall horizontal extent
    depth_ft: float          # overall vertical extent
    area_sf: float           # width x depth
    perimeter_lf: float      # 2 x (width + depth), rectangular assumption
    confidence: str          # "high" | "medium" | "low"
    page_index: int          # 0-based page the footprint was read from
    sheet_name: str = ""
    needs_review: bool = False
    review_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_feet(text: str) -> Optional[float]:
    m = _DIM_RE.match(text or "")
    if not m:
        return None
    feet = int(m.group(1))
    inches = int(m.group(2)) if m.group(2) else 0
    if inches >= 12:
        return None
    val = feet + inches / 12.0
    if not (MIN_OVERALL_FT <= val <= MAX_OVERALL_FT):
        return None
    return val


def _axis_dims(page) -> Tuple[List[float], List[float]]:
    """Return (horizontal_dims, vertical_dims) in feet for one page.

    Axis is decided by the text line's rotation vector: a horizontal dimension
    string reads left-to-right (|cos| >= |sin|); a vertical one is rotated 90°.
    """
    try:
        data = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return [], []
    if not isinstance(data, dict):
        return [], []
    horiz: List[float] = []
    vert: List[float] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            dir_ = line.get("dir", (1.0, 0.0)) or (1.0, 0.0)
            dx, dy = dir_[0], dir_[1]
            for span in line.get("spans", []):
                ft = _parse_feet(span.get("text", ""))
                if ft is None:
                    continue
                if abs(dx) >= abs(dy):
                    horiz.append(ft)
                else:
                    vert.append(ft)
    return horiz, vert


def _dominates(vals: List[float], top: float) -> bool:
    """True when `top` clearly stands out (overall dim, not a typical bay dim)."""
    others = [v for v in vals if abs(v - top) > 0.5]
    if not others:
        return True
    return top >= 1.3 * max(others)


def _page_is_floor_plan(page) -> bool:
    try:
        text = (page.get_text("text") or "").upper()
    except Exception:  # noqa: BLE001
        return False
    return "FLOOR PLAN" in text or "ROOF PLAN" in text


def footprint_from_page(page, page_index: int = 0, sheet_name: str = "") -> Optional[Footprint]:
    """Compute a building footprint from one page's overall dimensions, or None."""
    horiz, vert = _axis_dims(page)
    if not horiz or not vert:
        return None
    w = max(horiz)
    d = max(vert)
    area = w * d
    perim = 2.0 * (w + d)

    # Confidence: both overall dims should clearly dominate the bay/room dims.
    strong = _dominates(horiz, w) and _dominates(vert, d)
    confidence = "high" if strong else "medium"
    needs_review = not strong
    reason = "" if strong else "overall building dimensions not clearly dominant; verify on sheet"
    return Footprint(
        width_ft=round(w, 2),
        depth_ft=round(d, 2),
        area_sf=round(area, 1),
        perimeter_lf=round(perim, 1),
        confidence=confidence,
        page_index=page_index,
        sheet_name=sheet_name,
        needs_review=needs_review,
        review_reason=reason,
    )


# Keywords that mark a manifest area item as a building FLOOR or ROOF plane
# (its area equals the footprint). Wall keywords are excluded — wall area is
# perimeter x height for a *single enclosing* material, which is not safely
# attributable from the footprint alone (interior vs exterior, mixed materials).
_FLOOR_ROOF_KW = {
    "floor", "slab", "sealed", "concrete", "flooring", "roof", "deck",
    "decking", "exposed", "structure", "ceiling", "joist", "membrane", "tpo",
    "underlayment", "topping",
}
_WALL_KW = {
    "wall", "walls", "cmu", "masonry", "tilt", "partition", "panel", "panels",
    "parapet", "veneer", "stud", "framing",
}


def _entry_plane(entry) -> Optional[str]:
    """Classify a manifest entry as 'floor_roof', 'wall', or None (ambiguous)."""
    phrases = [entry.name, *getattr(entry, "aliases", [])]
    toks = set()
    for p in phrases:
        toks |= {t for t in re.split(r"[^a-z0-9]+", (p or "").lower()) if t}
    if toks & _WALL_KW:
        return "wall"
    if toks & _FLOOR_ROOF_KW:
        return "floor_roof"
    return None


def footprint_to_legend(footprint: Optional["Footprint"], manifest) -> Optional[dict]:
    """Build an authoritative legend giving floor/roof area items the measured
    footprint, so they override unstable vision-guessed areas.

    Requires a manifest (to know which items are floor/roof planes vs walls).
    Returns None when there is no footprint, no manifest, or no matching items.
    """
    if not footprint or not manifest:
        return None
    area = footprint.area_sf
    if not area or area <= 0:
        return None

    rows: List[dict] = []
    for entry in getattr(manifest, "entries", []):
        if (entry.measure or "").lower() != "area":
            continue
        if _entry_plane(entry) != "floor_roof":
            continue
        rows.append({
            "ITEM": entry.name,
            "DESCRIPTION": entry.name,
            "QTY": str(area), "QUANTITY": str(area),
            "UNIT": (entry.unit or "SF").upper(),
        })
    if not rows:
        return None

    note = (
        f"Building footprint {footprint.width_ft:.0f} ft x {footprint.depth_ft:.0f} ft "
        f"= {area:,.0f} SF, measured deterministically from the overall dimension "
        f"strings on the floor plan (page {footprint.page_index + 1}). Applied to "
        f"floor/roof-plane items. Verify the overall dimensions on the sheet."
    )
    return {
        "name": "Building Footprint (measured from overall dimensions)",
        "table_purpose": "takeoff_legend",
        "schedule_type": "area",
        "use_for_takeoff": True,
        "description": note,
        "rows": rows,
        "_source_pages": [footprint.page_index + 1],
        "_confidence": footprint.confidence,
    }


def extract_footprint_legend(pdf_path: str, manifest) -> Optional[dict]:
    """Convenience: extract footprint from a PDF and convert to a legend."""
    fp = extract_building_footprint(pdf_path)
    return footprint_to_legend(fp, manifest)


def extract_building_footprint(pdf_path: str) -> Optional[Footprint]:
    """Best building footprint across the floor/roof-plan pages of a PDF.

    Prefers pages titled with FLOOR/ROOF PLAN; falls back to any page. Among
    candidates, picks the largest footprint (the overall building, not a partial
    or enlarged plan). Returns None when no usable overall dimensions are found.
    """
    import fitz  # PyMuPDF — imported lazily so importing this module is cheap

    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Footprint: cannot open %s: %s", pdf_path, exc)
        return None

    try:
        plan_candidates: List[Footprint] = []
        any_candidates: List[Footprint] = []
        for i in range(doc.page_count):
            page = doc[i]
            try:
                sheet = (page.get_text("text") or "").strip().splitlines()
            except Exception:  # noqa: BLE001
                sheet = []
            sheet_name = sheet[0][:80] if sheet else ""
            fp = footprint_from_page(page, page_index=i, sheet_name=sheet_name)
            if not fp:
                continue
            any_candidates.append(fp)
            if _page_is_floor_plan(page):
                plan_candidates.append(fp)

        pool = plan_candidates or any_candidates
        if not pool:
            return None
        best = max(pool, key=lambda f: f.area_sf)
        logger.info(
            "Footprint: %.0f x %.0f ft = %.0f SF (page %d, conf=%s)",
            best.width_ft, best.depth_ft, best.area_sf, best.page_index + 1,
            best.confidence,
        )
        return best
    finally:
        doc.close()
