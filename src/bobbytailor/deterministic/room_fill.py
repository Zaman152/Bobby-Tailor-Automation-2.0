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
  below :data:`MIN_REGION_SF` are fixtures/annotation cells, not rooms. A
  region ABOVE :data:`MAX_REGION_SF` is kept and flagged — it is implausible
  as one guest room but perfectly ordinary as a lobby, and dropping it made
  the engine report nothing at all for the drawing.
* Every region also reports the perimeter of its outer contour, traced from
  the same mask its area was counted from, plus the blind shape ratio
  P/sqrt(A). Wall area is perimeter x height, so a fill that cannot state its
  perimeter cannot bind to a wall item at all (INV-01 §3).
* Flag-don't-guess: a measurement whose region structure is implausible for a
  single unit is returned with ``needs_review=True`` rather than silently
  halved or dropped. The human corrects it once and the learning store carries
  the correction forward.
* Plausibility is a RATIO against the drawing's OWN printed overall dimensions
  (:func:`printed_extent_bound` / :func:`cross_check_extent`), never a size in
  square feet. A guest-room-sized constant is right for a guest room and wrong
  for a lobby; ``fill / (max printed horizontal x max printed vertical)`` is
  ~1.0 for both and ~2.0 for a clip that really has swallowed a second plan.
"""
from __future__ import annotations

import logging
import math
import re
from array import array
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

# A drawing's title line names WHAT the drawing is:
#   "KING SUITE B - RCP PLAN"   "QQ A - AR PLAN"   "KING A - FF PLAN (LEFT)"
# The suffix is the discipline, and it decides which drawing measures which
# item: a CEILING area is taken off the Reflected Ceiling Plan, a floor/wall off
# the Architectural plan. Picking "the biggest region on the sheet" instead gives
# 33% mean error; picking by discipline gives 3.3% (real Moxy prototype sheets).
PLAN_TITLE_RE = re.compile(
    r"([A-Z0-9 \-/()&']+?)\s*-\s*(AR|RCP|FF|EM|FC)\s+PLAN", re.IGNORECASE
)

# Which drawing discipline measures which measure-basis.
BASIS_PLAN_KIND = {
    "ceiling_area": "RCP",   # reflected ceiling plan
    "roof_area": "RCP",
    "floor_area": "AR",      # architectural plan
    "wall_area": "AR",
    "area": "AR",
}

# Render resolution. 160 DPI resolves a 1/4"=1'-0" guestroom to ~2 px/inch of
# real wall — enough to keep thin partition strokes continuous (a broken wall
# leaks the fill into the outside region and the room is lost).
DEFAULT_DPI = 160

# Grayscale threshold: below this is ink (wall linework), above is free space.
INK_THRESHOLD = 170

# A region smaller than this is a fixture outline, a dimension cell or a text
# box — never a room. Larger than MAX is a sheet-scale region, not a unit; as
# of 23-09 such a region is KEPT AND FLAGGED rather than discarded.
MIN_REGION_SF = 8.0
MAX_REGION_SF = 900.0

# P / sqrt(A) — the BLIND shape validator. It is computed from geometry alone;
# no golden quantity is consulted and none may ever be (D-07). Observed values,
# all from INV-01 §4 on the real Moxy sheets:
#
#   4.00        a perfect square — the theoretical floor for any region
#   4.24        a 1:2 rectangle
#   4.24-5.08   every HONEST reflected-ceiling guest room measured
#               (KING SUITE B 4.24, QQ A 4.64, BUNK B 4.84, KING A 5.08)
#   8.54-9.04   the LEAKING architectural fills on those same four sheets,
#               where the contour wanders out through a door swing or a
#               dimension string
#   11.6-13.4   annotation and dimension cells — a 13.4 SF cell contributes
#               42 LF, more than a 121.8 SF bedroom's 56 LF
#
# 8.0 is therefore roughly a 2x margin on the worst honest room measured
# (5.08) and still below the best leak measured (8.54). The margin is read off
# the geometry; it is NOT fitted to any total, and it may not be.
#
# It is deliberately NOT applied to AREA. Stripping high-ratio regions from a
# real Moxy suite moves its measured area by nearly sixty square feet, and
# whether those slivers are closets or a cancelling error is a separate
# question — changing area here would be the coincidence trap run in reverse
# (INV-01 §4). This constant exists for the wall binder (23-13) to consume.
MAX_HONEST_SHAPE_RATIO = 8.0

# fill / (max printed horizontal dim x max printed vertical dim). A RATIO —
# dimensionless, scale-free and building-type-free. It replaces the 900 SF
# "largest plausible guest unit" threshold, which was a guest-room-shaped
# constant: correct for a guest room, wrong for a lobby, and applied on the
# WRONG SIDE of the room-mix multiplication so it never saw the number that was
# actually wrong (INV-02 §5).
#
# Read off the DISTRIBUTION, not fitted to a total (INV-02 §4, all sixteen real
# Moxy prototype sheets, measured before any golden value was consulted):
#
#   0.976 - 1.073   thirteen sheets that print an overall dimension pair
#   ~2.0            what a clip that had swallowed a second plan would read
#   2.479           ID-410, where only PARTIAL interior dimensions paired and
#                   the BOUND — not the fill — is wrong; flagged, as it must be
#
# 1.25 sits clear above every honest sheet measured (1.073) and far below both
# failure modes, so it discriminates without overfitting to a room size. It is
# not a quantity in square feet and must never become one.
EXTENT_TOLERANCE = 1.25

# How a partition shared by two rooms is billed (D-08, resolved from DATA).
#
# The question: does a wall item bill BOARD FACES (a shared partition counted
# once per side) or WALL LENGTH once? The Moxy take-off's own legend label is
# silent — it reads just "Gyp Wall <n> SF" with no convention stated — but the
# estimator's own markup answers it: on ID-407 (KING A) the Gyp Wall trace runs
# along BOTH faces of the bedroom/bath partition (parallel strokes at x 426.5
# and 433.0 pt, y 579.0 and 587.3 pt — 6.5-8.3 pt apart, one wall thickness at
# 1/4" = 1'-0"), and the same double-face tracing repeats on ID-411 and ID-413.
# The unit's envelope is traced once, on its room-side face.
#
# Summing every billable enclosed region's OUTER perimeter implements exactly
# that convention: the bedroom region's contour runs along the bedroom face of
# the shared partition, the bathroom region's contour along the bathroom face,
# and the envelope appears once. This constant exists so the wall binder's
# audit trail can NAME the convention instead of leaving it implicit.
PARTITION_CONVENTION = (
    "board faces: a partition shared by two regions is billed once per side "
    "(the sum of every billable region's outer perimeter); read off the "
    "take-off's own Gyp Wall markup, which traces a shared partition on both "
    "faces — the legend label itself states no convention"
)

# Plausible ceiling-height band for a per-drawing height tag, in feet. Read off
# the real sheets: every Moxy prototype RCP prints its room height (9'-0",
# 9'-8" on BUNK A) and its bath/entry soffit (8'-0") inside the clip; fixture
# mounting tags carry the AFF marker and are excluded by MARKER, not by band.
CEILING_HEIGHT_BAND_FT = (7.0, 12.0)

# The above-finished-floor marker. A span containing it is a fixture MOUNTING
# height (8'-1" AFF towel bar), never a ceiling height.
AFF_MARKER = "AFF"

# Feet-and-inches token: 9'-0", 9'-8", 10'-10 3/8", 8' - 4" …
FEET_INCHES_RE = re.compile(
    r"(\d{1,2})'\s*-?\s*(\d{1,2})(?:\s+(\d+)/(\d+))?\s*\"?"
)


@dataclass
class FilledRegion:
    """One enclosed region measured by flood fill.

    ``perimeter_lf`` is traced from the SAME mask ``area_sf`` was counted from
    — not from a parallel re-measurement — so the two can never describe
    different regions. ``shape_ratio`` is ``perimeter_lf / sqrt(area_sf)``; see
    :data:`MAX_HONEST_SHAPE_RATIO` for what its values mean.

    A ``perimeter_lf`` of 0.0 on a region with a real area means the trace did
    not complete (it hit the iteration cap, T-23-34). It is a "not measured",
    never a "no walls", and :func:`measure_enclosed_area` flags it.
    """

    area_sf: float
    px: int
    touches_edge: bool
    perimeter_lf: float = 0.0
    shape_ratio: float = 0.0


@dataclass
class RoomFillResult:
    """Enclosed-area measurement for one viewport."""

    area_sf: float                 # sum of every enclosed region (the unit)
    regions: List[float] = field(default_factory=list)
    candidate_id: str = ""
    scale_fpi: Optional[float] = None
    needs_review: bool = False
    review_reason: str = ""
    sheet_name: str = ""
    viewport_title: str = ""       # e.g. "KING SUITE B - RCP PLAN"
    plan_name: str = ""            # "KING SUITE B"
    plan_kind: str = ""            # "RCP" | "AR" | "FF" | "EM" | "FC"
    # Wall area is perimeter x height, so the perimeter has to leave this
    # dataclass or the binding cannot be built (INV-01 §3). The two lists are
    # PARALLEL TO ``regions`` — same order, same length — because a perimeter
    # that cannot say which region it belongs to cannot be filtered by shape.
    perimeter_lf: float = 0.0      # sum over the same regions ``area_sf`` sums
    region_perimeters: List[float] = field(default_factory=list)
    region_shape_ratios: List[float] = field(default_factory=list)
    # The drawing's OWN statement of its extent, and how the measurement
    # compares to it. Both are ``None`` when the drawing prints no overall
    # dimension pair — which is a NEEDS REVIEW, never a dropped measurement
    # (INV-02 risk 2: a bound-derived rejection of a good fill would be worse
    # than the bug it is meant to catch).
    bound_sf: Optional[float] = None
    extent_ratio: Optional[float] = None
    # The wall height this unit's quantities multiply by, and WHERE it came
    # from. Resolved per drawing (the unit's own reflected-ceiling clip prints
    # it) with the project resolver as a flagged fallback — never silently. A
    # source that is not "drawing" or "learned" must flag downstream: the
    # project answer on Moxy is 15 ft harvested from a roof-plan clearance
    # callout, and multiplying a guest-room perimeter by it is a ~67%
    # overstatement that today arrives UNFLAGGED (INV-01 §5).
    wall_height_ft: Optional[float] = None
    wall_height_source: str = ""

    def to_dict(self) -> dict:
        return {
            "area_sf": self.area_sf,
            "regions": self.regions,
            "candidate_id": self.candidate_id,
            "scale_fpi": self.scale_fpi,
            "needs_review": self.needs_review,
            "review_reason": self.review_reason,
            "sheet_name": self.sheet_name,
            "viewport_title": self.viewport_title,
            "plan_name": self.plan_name,
            "plan_kind": self.plan_kind,
            "perimeter_lf": self.perimeter_lf,
            "region_perimeters": self.region_perimeters,
            "region_shape_ratios": self.region_shape_ratios,
            "bound_sf": self.bound_sf,
            "extent_ratio": self.extent_ratio,
            "wall_height_ft": self.wall_height_ft,
            "wall_height_source": self.wall_height_source,
        }


def _rect(value):
    """``fitz.Rect(value)``, or ``None`` when fitz is missing or value is bad."""
    try:
        import fitz  # noqa: PLC0415 — optional at import time for test stubs

        return fitz.Rect(value)
    except Exception:  # noqa: BLE001
        return None


def to_page_space(page, rect):
    """Map *rect* from DRAWING space into PAGE (display) space.

    ``page.get_text(...)`` and ``page.get_drawings()`` report coordinates in the
    page's UNROTATED space (the mediabox), but ``page.get_pixmap(clip=…)`` — and
    every "which drawing sits above this label" judgement a human makes reading
    the sheet — live in ``page.rect``, which is the ROTATED one. On a sheet with
    ``/Rotate 270`` those are different spaces: Bob's page 4 has
    ``page.rect = 3024 x 2160`` while its drawings span ``y 99..2972``, i.e. the
    drawing's own y exceeds the display height. Handing such a rectangle to the
    rasteriser renders the wrong region, or nothing at all.

    This is the SINGLE implementation of that mapping for the whole engine.
    ``page.rotation_matrix`` is the identity on an unrotated page, so this
    function returns the caller's own object untouched there — 76 of the 83
    pages across the four real fixtures are unrotated and take a literally
    unchanged path. It never raises: a page object that cannot answer (a test
    stub, a defective file) yields the input unchanged, which is exactly
    today's behaviour.

    :func:`from_page_space` is its exact inverse.
    """
    return _map_rect(page, rect, "rotation_matrix")


def from_page_space(page, rect):
    """Map *rect* from PAGE (display) space back into DRAWING space.

    The inverse of :func:`to_page_space`, via ``page.derotation_matrix``. A
    caller that REASONS in page space (because "above" only means anything as
    the sheet is read) but must hand the result to an API speaking drawing
    space needs this direction; without it the coordinate space would have to
    be re-derived at each such site, which is the duplication D-03 forbids.
    Identity on an unrotated page, and never raises.
    """
    return _map_rect(page, rect, "derotation_matrix")


def _map_rect(page, rect, matrix_attr: str):
    """Shared body of :func:`to_page_space` / :func:`from_page_space`."""
    try:
        rotation = int(getattr(page, "rotation", 0) or 0) % 360
    except Exception:  # noqa: BLE001
        return rect
    if rotation == 0:
        # The matrix is the identity here, so the mapping is a no-op by
        # construction. Returning the caller's own object rather than a
        # rebuilt one keeps the unrotated majority BYTE-identical instead of
        # merely equal.
        return rect
    matrix = getattr(page, matrix_attr, None)
    if matrix is None:
        return rect
    box = _rect(rect)
    if box is None:
        return rect
    try:
        return box * matrix
    except Exception:  # noqa: BLE001
        return rect


def plan_titles(page) -> List[tuple]:
    """[(plan_name, plan_kind, bbox), ...] for every '<NAME> - <KIND> PLAN' label."""
    out: List[tuple] = []
    try:
        blocks = page.get_text("dict")["blocks"]
    except Exception:  # noqa: BLE001
        return out
    for b in blocks:
        for line in b.get("lines", []):
            txt = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
            m = PLAN_TITLE_RE.search(txt.upper())
            if m:
                out.append((m.group(1).strip(), m.group(2).upper(), tuple(line["bbox"])))
    return out


def select_fill_for_basis(
    fills: Sequence[RoomFillResult],
    basis: str,
    ambiguity_out: Optional[List[str]] = None,
) -> Optional[RoomFillResult]:
    """The fill whose drawing discipline measures *basis* (ceiling -> RCP …).

    ONE coordinated selection rule (23-13 Task 4), reconciling three separate
    proposals so this function is not edited three times in three directions:

    * **Selection** — prefer the fill whose extent ratio is closest to one,
      breaking ties by candidate identifier. The old ``min(area)`` "the
      smaller is the single unit" rule is GONE: its rationale rested on the
      opposite-hand-clip misdiagnosis this phase falsified (INV-02). If two
      same-discipline fills BOTH validate against their own printed extent,
      nothing is returned and the ambiguity is flagged through
      *ambiguity_out* — two drawings of the same name on one sheet make the
      unit ambiguous, and silently taking the smaller is a guess.
    * **Discipline** — unchanged (:data:`BASIS_PLAN_KIND`): wall area stays on
      the architectural drawing. The shape gate flags a degenerate AR fill;
      switching disciplines to dodge the leak would be a selection rule
      chosen for its output.
    * **Availability** — when EVERY candidate is flagged, the smallest flagged
      one is returned WITH ITS FLAG INTACT rather than nothing (the 23-03
      repair): a discipline whose every drawing was flagged used to return
      ``None`` and the caller's ``continue`` deleted the row — flag-don't-
      guess degraded into drop-and-be-silent (INV-08 §2 rows S8-S9).

    Returns ``None`` when no drawing of the right discipline was measured at
    all, or when the choice between validated candidates is ambiguous (then a
    reason is appended to *ambiguity_out*). The caller must flag — never
    substitute a different drawing's area, and never take a silent pick.
    """
    want = BASIS_PLAN_KIND.get((basis or "").strip().lower())
    if not want:
        return None
    matches = [f for f in fills if f.plan_kind == want]
    if not matches:
        return None
    clean = [f for f in matches if not f.needs_review]
    if not clean:
        # Availability: every candidate is flagged. The smallest flagged one,
        # flag intact, beats silence (23-03 / INV-08 §4 step 8).
        return min(matches, key=lambda f: f.area_sf)
    if len(clean) == 1:
        return clean[0]
    # Several clean candidates. A candidate VALIDATES when its measured area
    # sits inside the tolerance of the drawing's own printed extent.
    validated = [
        f for f in clean
        if f.extent_ratio is not None and f.extent_ratio <= EXTENT_TOLERANCE
    ]
    if len(validated) >= 2:
        if ambiguity_out is not None:
            names = sorted(
                {str(f.viewport_title or f.plan_name or f.candidate_id)
                 for f in validated}
            )
            ambiguity_out.append(
                "%d %s drawings on one sheet (%s) each validate against "
                "their own printed extent — which one is the unit is "
                "AMBIGUOUS; nothing was selected, and the smaller was not "
                "silently taken" % (len(validated), want, ", ".join(names))
            )
        return None
    if validated:
        return validated[0]
    # No candidate validates (no printed extent on a clean synthetic fill, or
    # every ratio is off): closest to one wins, candidate id breaks ties, and
    # a fill with no ratio at all ranks last. Area size plays no part.
    return min(
        clean,
        key=lambda f: (
            abs(float(f.extent_ratio) - 1.0)
            if f.extent_ratio is not None else float("inf"),
            str(f.candidate_id),
        ),
    )


@dataclass
class LabelledMask:
    """The output of :func:`label_mask` — a labelled bitmap that KEEPS its labels.

    ``labels[i]`` is the 1-based component id of pixel ``i``, or 0 for a pixel
    that is not set in the input mask. The three per-component lists are
    parallel and 0-indexed, so component ``k`` (1-based) is described by
    ``counts[k - 1]``, ``starts[k - 1]`` and ``touches_edge[k - 1]``.
    """

    labels: "array"
    counts: List[int]
    starts: List[int]
    touches_edge: List[bool]
    width: int
    height: int

    @property
    def count(self) -> int:
        return len(self.counts)


# 1 where the sample is free space, 0 where it is ink. Built once at import so
# the per-pixel classification is a single C-level ``bytes.translate`` rather
# than a 1.2-million-iteration Python loop per clip — the labeller is already
# the dominant cost of a fill (T-23-33) and the render resolution constant is
# deliberately NOT raised to compensate (R11).
_FREE_TABLE = bytes(1 if v > INK_THRESHOLD else 0 for v in range(256))


def free_mask(samples, n_px: int):
    """The free-space (non-ink) mask of a grayscale sample buffer."""
    try:
        return samples.translate(_FREE_TABLE)
    except (AttributeError, TypeError, ValueError):  # a list, a test stub
        out = bytearray(n_px)
        for i in range(n_px):
            if samples[i] > INK_THRESHOLD:
                out[i] = 1
        return out


def label_mask(mask, width: int, height: int) -> LabelledMask:
    """Connected-component label a boolean/byte mask, KEEPING the labels.

    THE one labeller (D-03). Three consumers share this single implementation
    so a clip is labelled ONCE, not once per question asked of it:

    1. the enclosed-void consumer — :func:`measure_enclosed_area`, which labels
       free space and measures each void that does not touch the clip edge;
    2. the contour consumer — :func:`_trace_outer_contour`, which needs the
       label array and each component's seed pixel, both of which the previous
       implementation built and then threw away;
    3. the silhouette-complement consumer that plan 23-14 adds, which labels
       INK rather than free space. Nothing here knows which of the two it was
       handed, which is exactly why one function can serve both.

    Connectivity is 4-way, unchanged: a room that leaks into the outside
    through a diagonal pixel gap is not enclosed, and 8-way labelling of free
    space would silently merge them.

    Args:
        mask:   a ``bytes``/``bytearray``/sequence where a truthy entry is a
                member pixel, indexed row-major.
        width:  pixels per row.
        height: rows.

    Returns:
        A :class:`LabelledMask`. ``starts[k]`` is component ``k+1``'s
        TOPMOST-then-LEFTMOST pixel by construction: the outer scan runs in
        raster order, so the first pixel of a component ever visited is its
        lowest linear index, which is its smallest ``y`` and, within that row,
        its smallest ``x``. That is precisely the seed a Moore-neighbour trace
        requires, so no second pass is needed to find it.
    """
    n_px = width * height
    labels = array("i")
    labels.frombytes(b"\x00" * (labels.itemsize * n_px))
    counts: List[int] = []
    starts: List[int] = []
    edges: List[bool] = []
    last_row = n_px - width
    for start in range(n_px):
        if not mask[start] or labels[start]:
            continue
        cid = len(counts) + 1
        queue = deque([start])
        labels[start] = cid
        count = 0
        edge = False
        while queue:
            idx = queue.popleft()
            count += 1
            x = idx % width
            if x == 0 or x == width - 1 or idx < width or idx >= last_row:
                edge = True
            if x + 1 < width:
                j = idx + 1
                if mask[j] and not labels[j]:
                    labels[j] = cid
                    queue.append(j)
            if x > 0:
                j = idx - 1
                if mask[j] and not labels[j]:
                    labels[j] = cid
                    queue.append(j)
            if idx < last_row:
                j = idx + width
                if mask[j] and not labels[j]:
                    labels[j] = cid
                    queue.append(j)
            if idx >= width:
                j = idx - width
                if mask[j] and not labels[j]:
                    labels[j] = cid
                    queue.append(j)
        counts.append(count)
        starts.append(start)
        edges.append(edge)
    return LabelledMask(
        labels=labels, counts=counts, starts=starts, touches_edge=edges,
        width=width, height=height,
    )


def _label_regions(samples, width: int, height: int, px_area_sf: float,
                   px_len_ft: float = 0.0) -> List[FilledRegion]:
    """Connected-component label every free (non-ink) region in a gray bitmap.

    A thin projection over :func:`label_mask` — the counting view of the one
    labeller. The return shape is exactly what it always was, so no caller
    moves.

    With *px_len_ft* supplied, each region's outer contour is traced from that
    SAME labelled mask and its perimeter and shape ratio are filled in. The
    clip is still labelled exactly once: tracing costs O(boundary), while the
    labelling it reuses costs O(area).
    """
    labelled = label_mask(free_mask(samples, width * height), width, height)
    out: List[FilledRegion] = []
    for k, count in enumerate(labelled.counts):
        region = FilledRegion(
            area_sf=count * px_area_sf, px=count,
            touches_edge=labelled.touches_edge[k],
        )
        if px_len_ft > 0.0:
            contour, truncated = _trace_outer_contour(
                labelled.labels, width, height, k + 1, labelled.starts[k],
                max_steps=4 * count + 16,
            )
            if not truncated:
                region.perimeter_lf = _ring_length(
                    _simplify_ring(contour)
                ) * px_len_ft
                if region.area_sf > 0.0:
                    region.shape_ratio = region.perimeter_lf / math.sqrt(
                        region.area_sf
                    )
        out.append(region)
    return out


# The Moore neighbourhood of a pixel, in one consistent rotational order
# starting due WEST. The order is what makes the trace walk a ring; the
# starting direction is what makes it the OUTER ring.
_MOORE = ((-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1))
_MOORE_INDEX = {off: i for i, off in enumerate(_MOORE)}


def _trace_outer_contour(labels, width: int, height: int, region_id: int,
                         start_idx: int, max_steps: int = 0):
    """The OUTER boundary ring of one labelled component, in pixel coordinates.

    Moore-neighbour (8-connected) tracing with Jacob's stopping criterion,
    seeded at the component's topmost-then-leftmost pixel — the index
    :func:`label_mask` already recorded — with an initial backtrack direction
    of WEST. The pixel due west of that seed cannot be a member (a member there
    would itself have been the topmost-leftmost pixel), so west is background by
    construction and the trace starts on the outside of the ring.

    Because it walks ONE ring from the outside, an interior hole never enters
    the result: a furniture outline, a plumbing fixture or a room-number text
    box sitting inside a room contributes nothing to that room's perimeter.
    That is the difference between measuring a wall and measuring every line
    printed inside it.

    This is the TRACED method and the only one that may ship. INV-05 §3
    measured the naive alternative — counting raster boundary pixels — at
    roughly SIX TIMES the true perimeter, because a boundary pixel is counted
    once per exposed face and a one-pixel-wide staircase exposes several. It
    was measured precisely so that it would never be mistaken for cheap.

    Args:
        max_steps: hard iteration cap (T-23-34). A degenerate component — a
            single pixel, or a shape whose ring never re-enters the seed in the
            seed's own direction — must FLAG, never spin. Callers pass
            ``4 * px_count + 16``; the true ring of a 4-connected component of
            *n* pixels cannot exceed roughly ``2n`` steps, so the cap is a
            safety net that a real region never approaches.

    Returns:
        ``(points, truncated)``. *points* is a CLOSED ring — its first and last
        entries are the same pixel — which is precisely the input
        :func:`_simplify_ring` is built to survive. *truncated* is True when
        the cap stopped the walk, in which case the ring is incomplete and the
        caller must flag rather than publish it.
    """
    sx, sy = start_idx % width, start_idx // width
    points = [(sx, sy)]
    px, py = sx, sy
    b_dir = 0                       # direction from the current pixel to its backtrack
    cap = max_steps if max_steps > 0 else 4 * width * height
    steps = 0
    truncated = False
    first_state = None
    while True:
        moved = False
        for k in range(1, 9):
            d = (b_dir + k) % 8
            dx, dy = _MOORE[d]
            nx, ny = px + dx, py + dy
            if 0 <= nx < width and 0 <= ny < height and \
                    labels[ny * width + nx] == region_id:
                # The backtrack for the next step is the neighbour examined
                # immediately BEFORE this one — the last background cell the
                # scan touched. Two consecutive Moore positions are always
                # 8-adjacent, so it is a legal backtrack for the new pixel.
                prev = (b_dir + k - 1) % 8
                bx = px + _MOORE[prev][0]
                by = py + _MOORE[prev][1]
                px, py = nx, ny
                b_dir = _MOORE_INDEX[(bx - px, by - py)]
                moved = True
                break
        if not moved:
            break                   # an isolated pixel has no ring to walk
        steps += 1
        state = (px, py, b_dir)
        # Jacob's criterion, stated on the FIRST TRANSITION rather than on the
        # seed's initial backtrack. Testing for "back at the seed, facing west
        # again" looks equivalent and is not: the seed is where the walk STARTS,
        # not necessarily where the ring passes through it. Measured on Moxy
        # page 35 (ACC KING TUB, RCP, the dominant 184.3 SF region): the ring
        # re-enters its seed heading SOUTH, so the state "seed, backtrack west"
        # lies on the walk's tail and never recurs — the walk then ran to its
        # iteration cap and that room reported no perimeter at all. Repeating
        # the first transition is the state the walk is guaranteed to return to,
        # because the trace is deterministic in (pixel, backtrack).
        if first_state is None:
            first_state = state
        elif state == first_state:
            break
        points.append((px, py))
        if steps >= cap:
            truncated = True
            break
    if points[-1] != points[0]:
        points.append(points[0])
    return points, truncated


def _perpendicular(cx, cy, ax, ay, bx, by, norm):
    """Distance from C to the segment AB's infinite line (radial if A == B)."""
    if norm <= 0.0:
        return math.hypot(cx - ax, cy - ay)
    return abs((bx - ax) * (ay - cy) - (ax - cx) * (by - ay)) / norm


def _douglas_peucker(points, eps_px: float):
    """Douglas-Peucker on an OPEN polyline. Never call this on a closed ring.

    :func:`_simplify_ring` is the entry point for rings and exists precisely
    because this function is the wrong tool for one. Iterative rather than
    recursive: a real room contour carries thousands of vertices and the
    recursive form is one pathological shape away from a RecursionError.
    """
    n = len(points)
    if n < 3:
        return list(points)
    keep = bytearray(n)
    keep[0] = keep[n - 1] = 1
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = points[i]
        bx, by = points[j]
        norm = math.hypot(bx - ax, by - ay)
        best, best_d = -1, 0.0
        for k in range(i + 1, j):
            cx, cy = points[k]
            d = _perpendicular(cx, cy, ax, ay, bx, by, norm)
            if d > best_d:
                best, best_d = k, d
        if best > 0 and best_d > eps_px:
            keep[best] = 1
            stack.append((i, best))
            stack.append((best, j))
    return [points[k] for k in range(n) if keep[k]]


def _simplify_ring(points, eps_px: float = 2.0):
    """Douglas-Peucker on a CLOSED ring, with the split repair.

    THE HAZARD. Running plain simplification on a ring whose first and last
    points coincide destroys it. The base chord is degenerate — it runs from a
    point to itself — so every vertex measures zero deviation from it, nothing
    survives the tolerance, and the ring collapses to a single point of zero
    length. INV-01's prototype hit exactly this: every simplified perimeter
    came back 0.0 while the areas were correct, which reads as "the room has no
    walls" rather than as a bug.

    THE REPAIR. Split the ring at the vertex FARTHEST from its first point,
    simplify the two halves independently as ordinary open polylines, and
    rejoin. Both halves then have a long, well-conditioned base chord.

    Simplification is kept even though the correction is small on rectilinear
    guest rooms — under one and a half percent on every region INV-01 §4
    measured — because it is a diagonal wall that needs it: traced pixel by
    pixel, a 45-degree wall is a staircase and a staircase is a factor of
    root-two longer than the wall it approximates.

    ``eps_px`` is 2 px at the shipped 160 DPI render, i.e. about 0.05 ft of the
    real building at a 1/4"=1'-0" guest-room scale — comfortably below the
    thickness of the linework being traced, so no real wall jog is erased.
    """
    if len(points) < 3:
        return list(points)
    ring = list(points)
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return list(points)
    p0 = ring[0]
    far = 0
    far_d = -1.0
    for i in range(1, len(ring)):
        d = (ring[i][0] - p0[0]) ** 2 + (ring[i][1] - p0[1]) ** 2
        if d > far_d:
            far, far_d = i, d
    if far == 0:
        return [p0, p0]
    first = _douglas_peucker(ring[:far + 1], eps_px)
    second = _douglas_peucker(ring[far:] + [p0], eps_px)
    return first[:-1] + second


def _ring_length(points) -> float:
    """The polyline length of *points*, in the units the points are given in."""
    total = 0.0
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        total += math.hypot(bx - ax, by - ay)
    return total


def measure_enclosed_area(
    page,
    clip,
    feet_per_point: float,
    dpi: int = DEFAULT_DPI,
    candidate_id: str = "",
    min_region_sf: float = MIN_REGION_SF,
    max_region_sf: float = MAX_REGION_SF,
    dropped_regions: Optional[List[float]] = None,
) -> Optional[RoomFillResult]:
    """Sum every enclosed region inside *clip* -> the unit's floor/ceiling SF.

    Args:
        page:            a PyMuPDF page.
        clip:            ``fitz.Rect`` bounding ONE drawing viewport, in
            DRAWING space — the space ``page.get_text`` and
            ``page.get_drawings`` report, which is where every caller's
            rectangle comes from. It is mapped through :func:`to_page_space`
            before rendering, because the rasteriser speaks ``page.rect``. On
            an unrotated page the two spaces are identical and nothing moves;
            on a rotated one this is the difference between rendering the
            drawing and rendering blank paper (INV-03 §4.2). A caller holding a
            rectangle it computed in PAGE space must map it back with
            :func:`from_page_space` first, so this function has exactly one
            contract and no caller can pick the wrong one.
        feet_per_point:  that viewport's OWN scale (never a project default).
        dpi:             render resolution.
        candidate_id:    id carried onto the result for fusion binding.
        dropped_regions: optional OUT-list. Every region LARGER than
            *max_region_sf* has its area appended here, so the coverage ledger
            can say *"3 regions of 1,240 / 980 / 1,510 SF exceeded one unit"*
            instead of the fact existing nowhere (INV-08 §4 step 7 / CONCERNS
            H1). Purely observational: passing it changes no threshold and no
            returned value. Since 23-09 such a region is KEPT AND FLAGGED
            rather than discarded, so this is an OVERSIZE register, not a
            rejection register; the parameter keeps its name because renaming
            it belongs with its caller, which is 23-11's scope. Moving the
            threshold to make anything pass remains the coincidence trap
            INV-08 risk 6 forbids, and the constant is unchanged.

    Returns:
        A :class:`RoomFillResult`, or ``None`` when the render fails or no
        enclosed region survives (caller keeps its prior behaviour — additive).
        A result whose regions include an oversize one comes back FLAGGED with
        its measurement intact — never as ``None``.
    """
    if not feet_per_point or feet_per_point <= 0:
        return None
    try:
        import fitz  # noqa: PLC0415 — optional at import time for test stubs

        # The rasteriser's clip is in page.rect space; the caller's rectangle
        # came from get_text/get_drawings, which is the mediabox. Identical on
        # an unrotated page, 90 degrees apart on a rotated one. get_pixmap
        # still intersects the mapped clip with the page rectangle itself, so
        # a rotation cannot widen the rendered region (T-23-27).
        pix = page.get_pixmap(
            clip=to_page_space(page, clip), dpi=dpi, colorspace=fitz.csGRAY
        )
    except Exception as exc:  # noqa: BLE001 — a defective page must not kill a run
        logger.debug("room_fill: render failed for %s: %s", candidate_id, exc)
        return None
    if not pix.width or not pix.height:
        return None

    zoom = dpi / 72.0
    px_area_sf = (1.0 / (zoom * zoom)) * feet_per_point * feet_per_point
    # The LINEAR analogue of the area factor, beside it so the two can never
    # drift apart. Area scales by the SQUARE of the scale and length by the
    # first power; deriving a perimeter from an area factor — or the reverse —
    # is the same class of error as measuring a 1/4" sheet at 1/8".
    px_len_ft = (1.0 / zoom) * feet_per_point
    regions = _label_regions(
        pix.samples, pix.width, pix.height, px_area_sf, px_len_ft
    )

    # The outside of the drawing touches the clip edge; rooms never do.
    #
    # A region LARGER than the maximum is kept and flagged, never dropped. The
    # hard drop it replaces made this engine return nothing at all — not a
    # flagged number, nothing — for every lobby, ballroom and retail floor
    # plate in the set, and a drawing that measured nothing is indistinguishable
    # from an item that is genuinely zero. That is the silent-zero failure this
    # phase exists to abolish (INV-02 §5). The rejection is still recorded in
    # *dropped_regions* so the coverage ledger can name it.
    enclosed: List[FilledRegion] = []
    oversize: List[FilledRegion] = []
    for r in regions:
        if r.touches_edge or r.area_sf < min_region_sf:
            continue
        if r.area_sf > max_region_sf:
            oversize.append(r)
            if dropped_regions is not None:
                dropped_regions.append(round(r.area_sf, 1))
        enclosed.append(r)
    if not enclosed:
        return None

    ordered = sorted(enclosed, key=lambda r: r.area_sf, reverse=True)
    result = RoomFillResult(
        area_sf=round(sum(r.area_sf for r in enclosed), 1),
        regions=[round(r.area_sf, 1) for r in ordered],
        candidate_id=candidate_id,
        scale_fpi=round(feet_per_point * 72.0, 4),
        perimeter_lf=round(sum(r.perimeter_lf for r in ordered), 1),
        region_perimeters=[round(r.perimeter_lf, 1) for r in ordered],
        region_shape_ratios=[round(r.shape_ratio, 2) for r in ordered],
    )

    notes: List[str] = []
    if oversize:
        notes.append(
            "%d region(s) of %s SF exceed the %.0f SF maximum for a single unit "
            "— KEPT AND FLAGGED, never discarded: a lobby, ballroom or retail "
            "floor plate is legitimately larger than a guest room, and dropping "
            "it returned nothing at all for the whole drawing. Verify the clip "
            "names ONE drawing before billing this area"
            % (len(oversize),
               ", ".join("%.0f" % r.area_sf
                         for r in sorted(oversize, key=lambda r: r.area_sf,
                                         reverse=True)),
               max_region_sf)
        )
    unmeasured = [r for r in ordered if r.perimeter_lf <= 0.0]
    if px_len_ft > 0.0 and unmeasured:
        notes.append(
            "%d of %d region(s) have no traced perimeter (the contour walk hit "
            "its iteration cap) — their length is UNMEASURED, not zero; the "
            "areas are unaffected" % (len(unmeasured), len(ordered))
        )
    if notes:
        result.needs_review = True
        result.review_reason = "; ".join(notes)
    return result


def _add_reason(result: RoomFillResult, reason: str) -> RoomFillResult:
    """Flag *result* and APPEND *reason*, preserving anything already there.

    A flag that silently overwrites another flag is the same defect as no flag
    at all: the oversize-region note raised inside :func:`measure_enclosed_area`
    used to be erased by the very next call.
    """
    result.needs_review = True
    result.review_reason = (
        "%s; %s" % (result.review_reason, reason) if result.review_reason else reason
    )
    return result


def printed_extent_bound(
    page,
    clip,
    plan_name: str = "",
    mask_rects: Sequence = (),
    sibling_rects: Sequence = (),
    samples: Optional[Sequence] = None,
) -> Optional[float]:
    """The drawing's OWN printed overall extent, in square feet.

    ``max(printed horizontal dimension) x max(printed vertical dimension)`` over
    the dimension strings this drawing prints. It is the drawing's own statement
    of how big it is, harvested from the sheet and independent of any golden
    quantity — which is the whole point: a measurement can then be cross-checked
    against the drawing rather than against a remembered room size.

    Args:
        page:          a PyMuPDF page.
        clip:          this drawing's clip, in DRAWING space (the space
            ``page.get_text`` reports, which is where the samples' own
            bounding boxes live). Used only when *sibling_rects* is empty.
        plan_name:     carried only into the review reason.
        mask_rects:    title-block / legend / schedule rectangles, excluded
            from the harvest exactly as the scale solver excludes them.
        sibling_rects: other drawings of the SAME plan name whose dimensions
            describe the same unit — in this drawing set the overall dimensions
            are printed on the ARCHITECTURAL plan and nowhere else, so a
            reflected-ceiling fill has no dimension of its own to check against
            and would be unbounded without them. Restricting to the
            architectural sibling is what separates an OVERALL dimension from
            the partial furniture dimensions the FF/EM/FC plans carry, and from
            the partial interior dimensions a reflected-ceiling plan carries:
            adding this drawing's own clip to the set turns ID-415 from "no
            bound" (correct) into 9'-0" x 1'-3" = 11.2 SF, a bound 25x too
            small, which reports a good measurement as a 25x overrun.
        samples:       pre-harvested :class:`DimensionSample` list. The harvest
            walks every segment on the page, so a caller measuring several
            drawings on one sheet passes it once instead of five times.

    Returns:
        The bound in SF, or ``None`` when no horizontal/vertical PAIR is found.
        ``None`` means "this drawing does not say how big it is" and must be
        flagged, never guessed and never used to drop a measurement.
    """
    box = _rect(clip)
    if box is None:
        return None
    if samples is None:
        try:
            from bobbytailor.deterministic.dimensions import (  # noqa: PLC0415
                extract_dimension_samples,
            )

            samples = extract_dimension_samples(page, exclude_rects=list(mask_rects))
        except Exception:  # noqa: BLE001 — a cross-check must never kill a run
            return None
    # The architectural sibling IS the dimensioned drawing — and for an
    # architectural fill it is this drawing's own clip, so the two cases are one
    # rule rather than a union. Falling back to the drawing itself only when the
    # set has no architectural plan of this name keeps a lobby sheet measurable
    # instead of unbounded by construction.
    rects = [r for r in (_rect(s) for s in sibling_rects) if r is not None] or [box]

    max_h = 0.0
    max_v = 0.0
    for s in samples or ():
        bbox = getattr(s, "text_bbox", None)
        feet = float(getattr(s, "feet", 0.0) or 0.0)
        if not bbox or len(bbox) < 4 or feet <= 0.0:
            continue
        cx = (float(bbox[0]) + float(bbox[2])) / 2.0
        cy = (float(bbox[1]) + float(bbox[3])) / 2.0
        if not any(r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1 for r in rects):
            continue
        # A dimension string reads ALONG the dimension it measures, so the
        # text's own writing direction is its orientation.
        rot = getattr(s, "rotation", (1.0, 0.0)) or (1.0, 0.0)
        dx, dy = float(rot[0]), float(rot[1])
        if abs(dx) >= abs(dy):
            max_h = max(max_h, feet)
        else:
            max_v = max(max_v, feet)
    if max_h <= 0.0 or max_v <= 0.0:
        return None
    return round(max_h * max_v, 1)


def cross_check_extent(
    result: RoomFillResult, bound_sf: Optional[float]
) -> RoomFillResult:
    """Cross-check a measured area against the drawing's own printed extent.

    THE SUPERSEDED STORY, corrected (D-01 / INV-02). This function replaces
    ``flag_implausible_unit``, whose docstring asserted that Moxy ID-412 and
    ID-416 measured ~2x because the clip reached into the neighbouring
    opposite-hand plan. That claim is FALSE and three independent geometric
    probes falsified it: those two sheets are bit-identical across a 240 pt
    range of clip widths (while three others move 17-20%), every counted region
    sits inside 47% of the clip, and the fill matches the drawing's own printed
    overall dimensions at a ratio of 1.007. The ~2x came one layer later, from
    a room-mix ``unit_count`` of 2 that counted a suite's entry + connecting
    door as two units.

    The old guard was also on the WRONG SIDE of that multiplication — it saw
    458 SF and passed it, never the 917 SF that was actually wrong — and its
    threshold was a size in square feet, i.e. a guest-room-shaped constant that
    a lobby breaks. This one is a RATIO (:data:`EXTENT_TOLERANCE`), so it reads
    ~1.0 for a guest room, ~1.0 for a ballroom, and ~2.0 for a clip that really
    has swallowed a second plan.

    It is a FLAG, never a FILTER. No bound is a NEEDS REVIEW carrying the
    measured area, not a dropped row: two of the sixteen prototype sheets print
    no dimension pair at all and one produced a bound 2.5x too small from
    partial interior dimensions, so a bound-derived rejection of a good fill
    would be worse than the bug it is meant to catch (INV-02 risk 2).

    Any reason already on the result is preserved.
    """
    if not bound_sf or bound_sf <= 0.0:
        result.bound_sf = None
        result.extent_ratio = None
        return _add_reason(
            result,
            "this drawing prints no overall dimension pair, so there is no "
            "printed extent to cross-check the measured %.0f SF against — the "
            "measurement stands, unverified" % result.area_sf,
        )
    result.bound_sf = round(float(bound_sf), 1)
    ratio = result.area_sf / float(bound_sf) if bound_sf else 0.0
    result.extent_ratio = round(ratio, 3)
    if ratio > EXTENT_TOLERANCE:
        return _add_reason(
            result,
            "measured %.0f SF is %.2fx the drawing's OWN printed overall extent "
            "of %.0f SF (tolerance %.2f) — either the clip names more than one "
            "drawing, or the printed dimensions found were partial; verify "
            "before billing" % (result.area_sf, ratio, bound_sf, EXTENT_TOLERANCE),
        )
    return result


def wall_perimeter_for_unit(
    result: RoomFillResult,
    max_shape_ratio: float = MAX_HONEST_SHAPE_RATIO,
) -> "tuple[float, str]":
    """The perimeter that should be BILLED for this unit, with its reason.

    Sums ``region_perimeters`` over regions whose blind shape ratio is at or
    below *max_shape_ratio* — the honest rooms. Regions above it are
    annotation/dimension cells (measured 11.6-13.4 on the real sheets, where a
    13.4 SF cell contributes more linear feet than a 121.8 SF bedroom); their
    LF is dropped and NAMED in the reason, never silently.

    If the DOMINANT region itself exceeds the threshold — the leaking
    architectural fills, measured 8.54-9.04 — the whole measurement is
    untrustworthy as a perimeter and ``(0.0, reason)`` is returned so the
    caller flags instead of emitting a fabricated linear-foot figure. The same
    refusal applies when the dominant region's perimeter is UNMEASURED (the
    trace hit its cap): a zero there is "not measured", never "no walls".

    The threshold's rationale is geometric (see
    :data:`MAX_HONEST_SHAPE_RATIO`): 4.0 is a square, the worst honest room
    measured 5.08, and 8.0 is roughly a two-times margin. It is NOT fitted to
    any quantity and may never be.

    The convention this sum implements is :data:`PARTITION_CONVENTION` —
    board faces, read off the take-off's own markup (D-08).
    """
    perims = list(result.region_perimeters or [])
    ratios = list(result.region_shape_ratios or [])
    if not perims or len(perims) != len(ratios):
        return 0.0, (
            "no per-region perimeters are recorded on this fill, so there is "
            "no billable perimeter — the wall area is UNMEASURED, not zero"
        )
    # ``regions``/``region_perimeters``/``region_shape_ratios`` are parallel
    # and ordered by area DESC (measure_enclosed_area), so index 0 is the
    # dominant region.
    if perims[0] <= 0.0:
        return 0.0, (
            "the dominant region's perimeter is UNMEASURED (the contour walk "
            "hit its cap), so no billable perimeter exists — flag, never a "
            "fabricated figure"
        )
    if ratios[0] > max_shape_ratio:
        return 0.0, (
            "the dominant region's shape ratio %.2f exceeds the honest-room "
            "maximum %.1f — the fill is leaking through door swings or "
            "dimension strings (the INV-01 architectural-leak signature), so "
            "its perimeter would be fabricated linear feet; the wall area is "
            "UNMEASURED, not zero" % (ratios[0], max_shape_ratio)
        )
    billable = 0.0
    dropped: List[str] = []
    areas = list(result.regions or [])
    for i, (p, r) in enumerate(zip(perims, ratios)):
        if p <= 0.0:
            continue
        if r > max_shape_ratio:
            area_txt = "%.1f SF" % areas[i] if i < len(areas) else "?"
            dropped.append("%s at ratio %.2f (%.1f LF)" % (area_txt, r, p))
            continue
        billable += p
    reason = ""
    if dropped:
        reason = (
            "%d annotation-shaped region(s) dropped from the billable "
            "perimeter (shape ratio above %.1f): %s"
            % (len(dropped), max_shape_ratio, "; ".join(dropped))
        )
    return round(billable, 1), reason


def wall_area_for_unit(perimeter_lf: float, height_ft: float) -> float:
    """Billable perimeter x wall height -> one unit's wall area, in SF.

    One line, named, so the formula string and the tests have a single anchor
    — the linear sibling of :func:`total_for_units`.
    """
    return round(float(perimeter_lf) * float(height_ft), 1)


def drawing_ceiling_heights(page, clip) -> List[float]:
    """Ceiling-height tags printed INSIDE *clip*, in feet, deduplicated.

    Scans text lines fully inside the clip (page space — the space the clip
    from ``_fill_clip_for_title`` lives in); accepts feet-and-inches tokens in
    :data:`CEILING_HEIGHT_BAND_FT`; REJECTS any span containing
    :data:`AFF_MARKER`, because ``8'-1" AFF`` is a fixture MOUNTING height,
    not a ceiling.

    Pass the REFLECTED-CEILING clip: printing the room height is what an RCP
    is for. An architectural plan's clip is full of room DIMENSIONS
    (``10'-10 3/8"``) that land in the same band and would be mistaken for
    heights — the caller (:func:`resolve_drawing_height` via the pipeline)
    therefore reads the RCP sibling of the same plan name, exactly as
    :func:`printed_extent_bound` reads the architectural sibling.
    """
    out: List[float] = []
    box = _rect(clip)
    if box is None:
        return out
    lo, hi = CEILING_HEIGHT_BAND_FT
    try:
        blocks = page.get_text("dict")["blocks"]
    except Exception:  # noqa: BLE001 — a height harvest must never kill a run
        return out
    for b in blocks:
        for line in b.get("lines", []):
            bbox = line.get("bbox")
            if not bbox or len(bbox) < 4:
                continue
            pbox = _rect(to_page_space(page, _rect(bbox)))
            if pbox is None:
                continue
            if not (box.x0 <= pbox.x0 and pbox.x1 <= box.x1
                    and box.y0 <= pbox.y0 and pbox.y1 <= box.y1):
                continue
            txt = "".join(s.get("text", "") for s in line.get("spans", []))
            if AFF_MARKER in txt.upper():
                continue
            for m in FEET_INCHES_RE.finditer(txt):
                feet = int(m.group(1)) + int(m.group(2)) / 12.0
                if m.group(3) and m.group(4):
                    try:
                        feet += int(m.group(3)) / int(m.group(4)) / 12.0
                    except ZeroDivisionError:
                        continue
                if lo <= feet <= hi:
                    value = round(feet, 3)
                    if value not in out:
                        out.append(value)
    return sorted(out)


def resolve_drawing_height(
    page,
    clip,
    project_height_ft: Optional[float] = None,
    project_height_source: str = "",
) -> "tuple[Optional[float], str]":
    """``(height_ft, source)`` — most specific first, and never a silent guess.

    Precedence: the drawing's own ceiling tag (source ``"drawing"``), then
    whatever the project resolver produced (its source carried through —
    ``"learned"`` wins inside the resolver already, then ``"plan"``, then
    ``"default"``), then ``(None, "")`` so the caller FLAGS.

    The TALLER tag wins when the clip prints several: within one unit the
    reflected ceiling plan prints the room height and the lower bath/entry
    soffit, and the wall boarded to full height is the tall one (INV-01 §5).

    Anything whose source is not ``"drawing"`` (or ``"learned"``) must set
    needs-review downstream with the source named: Moxy's project answer is
    15 ft from a roof-plan ``CLEAR REQ'D`` callout whose source reads
    ``"plan"``, which is precisely the trap that does not flag today.
    """
    if clip is not None:
        tags = drawing_ceiling_heights(page, clip)
        if tags:
            return max(tags), "drawing"
    try:
        height = float(project_height_ft) if project_height_ft is not None else None
    except (TypeError, ValueError):
        height = None
    if height is not None and height > 0:
        return height, (project_height_source or "default")
    return None, ""


def total_for_units(area_sf: float, unit_count: int) -> float:
    """Prototype-unit area x how many of that type exist -> project quantity.

    Hotel/multifamily take-offs are authored this way: a sheet draws ONE typical
    unit and the estimator multiplies by the room mix. ``unit_count`` is a human
    input (the estimator knows the mix); ``area_sf`` is measured from the plan.
    """
    if unit_count is None or unit_count <= 0:
        return round(area_sf, 1)
    return round(area_sf * int(unit_count), 1)
