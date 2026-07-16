"""Enclosed-region room measurement (Recipe E) — raster flood fill.

WHY THIS EXISTS
---------------
The vector room engine (``rooms.extract_rooms``, Recipe C) polygonizes the wall
CENTERLINE network. That works on plans whose walls are drawn as clean paired
linework (Crow), but it collapses on drawing styles that render rooms as loose
axis-aligned strokes: on Moxy's guestroom sheets it returns 17 SF fragments
where the room is 353 SF, and the vector data contains no closed room path at
all (a search for closed paths of 100-900 SF returns zero).

A room is not a polygon in the file — it is a REGION ENCLOSED BY INK. So render
the drawing and flood-fill it. This is robust to non-rectangular rooms, to walls
drawn as strokes/poché/hatch, and to door swings, which is exactly where every
vector shortcut failed (measured 14-106% error; this lands 0.2-3.8% on 8 of 11
real Moxy prototype sheets).

MEASUREMENT CONTRACT
--------------------
* Geometry supplies the number: pixels are counted at the viewport's OWN printed
  scale, never a project-level guess (a 1/4"=1'-0" sheet measured at an assumed
  1/8" is a 4x area error — area scales by the square).
* A unit's ceiling is the SUM of every enclosed region inside it: bedroom +
  bathroom + entry/closet. Filling from a single seed stops at the bathroom wall
  and lands a systematic ~30% under.
* Regions touching the clip edge are the OUTSIDE and are discarded; regions
  below :data:`MIN_REGION_SF` are fixtures/annotation cells, not rooms.
* Flag-don't-guess: a measurement whose region structure is implausible for a
  single unit is returned with ``needs_review=True`` rather than silently
  halved or dropped. The human corrects it once and the learning store carries
  the correction forward.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

# Render resolution. 160 DPI resolves a 1/4"=1'-0" guestroom to ~2 px/inch of
# real wall — enough to keep thin partition strokes continuous (a broken wall
# leaks the fill into the outside region and the room is lost).
DEFAULT_DPI = 160

# Grayscale threshold: below this is ink (wall linework), above is free space.
INK_THRESHOLD = 170

# A region smaller than this is a fixture outline, a dimension cell or a text
# box — never a room. Larger than MAX is a sheet-scale region, not a unit.
MIN_REGION_SF = 8.0
MAX_REGION_SF = 900.0


@dataclass
class FilledRegion:
    """One enclosed region measured by flood fill."""

    area_sf: float
    px: int
    touches_edge: bool


@dataclass
class RoomFillResult:
    """Enclosed-area measurement for one viewport."""

    area_sf: float                 # sum of every enclosed region (the unit)
    regions: List[float] = field(default_factory=list)
    candidate_id: str = ""
    scale_fpi: Optional[float] = None
    needs_review: bool = False
    review_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "area_sf": self.area_sf,
            "regions": self.regions,
            "candidate_id": self.candidate_id,
            "scale_fpi": self.scale_fpi,
            "needs_review": self.needs_review,
            "review_reason": self.review_reason,
        }


def _label_regions(samples, width: int, height: int, px_area_sf: float) -> List[FilledRegion]:
    """Connected-component label every free (non-ink) region in a gray bitmap."""
    n_px = width * height
    free = bytearray(n_px)
    for i in range(n_px):
        if samples[i] > INK_THRESHOLD:
            free[i] = 1
    seen = bytearray(n_px)
    out: List[FilledRegion] = []
    for start in range(n_px):
        if not free[start] or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        count = 0
        edge = False
        while queue:
            idx = queue.popleft()
            count += 1
            x, y = idx % width, idx // width
            if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                edge = True
            if x + 1 < width:
                j = idx + 1
                if free[j] and not seen[j]:
                    seen[j] = 1
                    queue.append(j)
            if x > 0:
                j = idx - 1
                if free[j] and not seen[j]:
                    seen[j] = 1
                    queue.append(j)
            if y + 1 < height:
                j = idx + width
                if free[j] and not seen[j]:
                    seen[j] = 1
                    queue.append(j)
            if y > 0:
                j = idx - width
                if free[j] and not seen[j]:
                    seen[j] = 1
                    queue.append(j)
        out.append(FilledRegion(area_sf=count * px_area_sf, px=count, touches_edge=edge))
    return out


def measure_enclosed_area(
    page,
    clip,
    feet_per_point: float,
    dpi: int = DEFAULT_DPI,
    candidate_id: str = "",
    min_region_sf: float = MIN_REGION_SF,
    max_region_sf: float = MAX_REGION_SF,
) -> Optional[RoomFillResult]:
    """Sum every enclosed region inside *clip* -> the unit's floor/ceiling SF.

    Args:
        page:            a PyMuPDF page.
        clip:            ``fitz.Rect`` bounding ONE drawing viewport.
        feet_per_point:  that viewport's OWN scale (never a project default).
        dpi:             render resolution.
        candidate_id:    id carried onto the result for fusion binding.

    Returns:
        A :class:`RoomFillResult`, or ``None`` when the render fails or no
        enclosed region survives (caller keeps its prior behaviour — additive).
    """
    if not feet_per_point or feet_per_point <= 0:
        return None
    try:
        import fitz  # noqa: PLC0415 — optional at import time for test stubs

        pix = page.get_pixmap(clip=clip, dpi=dpi, colorspace=fitz.csGRAY)
    except Exception as exc:  # noqa: BLE001 — a defective page must not kill a run
        logger.debug("room_fill: render failed for %s: %s", candidate_id, exc)
        return None
    if not pix.width or not pix.height:
        return None

    zoom = dpi / 72.0
    px_area_sf = (1.0 / (zoom * zoom)) * feet_per_point * feet_per_point
    regions = _label_regions(pix.samples, pix.width, pix.height, px_area_sf)

    # The outside of the drawing touches the clip edge; rooms never do.
    enclosed = [
        r.area_sf for r in regions
        if not r.touches_edge and min_region_sf <= r.area_sf <= max_region_sf
    ]
    if not enclosed:
        return None

    total = round(sum(enclosed), 1)
    result = RoomFillResult(
        area_sf=total,
        regions=sorted((round(a, 1) for a in enclosed), reverse=True),
        candidate_id=candidate_id,
        scale_fpi=round(feet_per_point * 72.0, 4),
    )
    return result


def flag_implausible_unit(result: RoomFillResult, expect_max_sf: float) -> RoomFillResult:
    """Flag (never silently correct) a measurement too large for one unit.

    A clip that overlaps the neighbouring opposite-hand plan measures TWO units
    and reports ~2x (real: Moxy ID-412/ID-416). Halving it automatically would
    be a guess, so the row is flagged for review instead — the human resolves it
    once and the learning store applies that decision to later runs.
    """
    if expect_max_sf and result.area_sf > expect_max_sf:
        result.needs_review = True
        result.review_reason = (
            "measured %.0f SF exceeds the plausible single-unit maximum of %.0f SF — "
            "the viewport may include an adjacent (opposite-hand) plan; verify"
            % (result.area_sf, expect_max_sf)
        )
    return result


def total_for_units(area_sf: float, unit_count: int) -> float:
    """Prototype-unit area x how many of that type exist -> project quantity.

    Hotel/multifamily take-offs are authored this way: a sheet draws ONE typical
    unit and the estimator multiplies by the room mix. ``unit_count`` is a human
    input (the estimator knows the mix); ``area_sf`` is measured from the plan.
    """
    if unit_count is None or unit_count <= 0:
        return round(area_sf, 1)
    return round(area_sf * int(unit_count), 1)
