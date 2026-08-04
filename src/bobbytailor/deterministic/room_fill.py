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

# ── Elevation facades (23-14 / INV-03) ───────────────────────────────────────
#
# A facade is a FILLED SILHOUETTE subdivided by joint and reveal lines — not a
# void enclosed by walls. The naive room flood fill fragments Bob's front
# elevation into 63 voids summing 4,561 SF; complement labelling (flood the
# FREE pixels from the clip border, invert, take the largest component)
# returns ONE clean blob per elevation on all three fixtures that draw
# elevations, with no tuning (INV-03 §3.1-3.2).

# The word that names an elevation drawing in its own printed callout title.
ELEVATION_TITLE_RE = re.compile(r"\bELEVATIONS?\b", re.IGNORECASE)

# Orientation classification. An exterior facade names its orientation either
# directly BEFORE the elevation word ("FRONT ELEVATION NEW", "SIDE ELEVATION
# TYPE A") or directly AFTER it ("LEASING ELEVATION FRONT", "BUILDING
# ELEVATION SOUTH …", "16-BAY GARAGE ELEVATION SIDE1"). A title with NEITHER —
# "MAIN ENTRY LOUNGE ELEVATION A", "ELEVATION GUEST ENTRY DOOR", "ELEVATION
# VIEW" — is an interior or detail elevation, and it is EXCLUDED from
# new-work exterior quantities rather than guessed at (23-CONTEXT decision 4:
# interior elevations are excluded; WC areas must not be synthesized).
_ELEV_ORIENT_BEFORE_RE = re.compile(
    r"\b(TRUCK\s+DOCK|NORTH|SOUTH|EAST|WEST|FRONT|REAR|BACK|SIDE)\s+"
    r"ELEVATIONS?\b",
    re.IGNORECASE,
)
_ELEV_ORIENT_AFTER_RE = re.compile(
    r"\bELEVATIONS?\s*-?\s*(NORTH|SOUTH|EAST|WEST|FRONT|REAR|BACK|SIDE)\d?\b",
    re.IGNORECASE,
)
# Intent: a demolition/existing elevation describes what is REMOVED, not what
# is built — Bob's page 4 carries FRONT ELEVATION DEMOLITION (6,134 SF) beside
# FRONT ELEVATION NEW (6,245 SF), and counting both doubles the front facade.
_ELEV_DEMO_RE = re.compile(r"\b(DEMOLITION|DEMO|EXISTING)\b", re.IGNORECASE)
_ELEV_INTERIOR_RE = re.compile(r"\bINTERIOR\b", re.IGNORECASE)

# A dedicated drawing-title text line ("FRONT ELEVATION DEMOLITION" at 25 pt)
# is short; a general note that happens to contain the word ELEVATIONS is a
# sentence. Measured on the real sheets: every true title line is <= 45 chars,
# the shortest offending note is 73.
_ELEV_TITLE_MAX_CHARS = 60

# Datum labels — the words an elevation prints beside its vertical ruler.
# Measured on the real sheets: Crow prints T/ PANEL, T/ PANEL AT GUTTER,
# FINISH FLOOR and TRUCK COURT; Chelsea prints PLATE BEARING / FLOOR spot
# elevations prefixed "EL:"; Moxy's civic elevations print T/ ROOF against a
# SEA-LEVEL datum (969'-2") — which is why the wall band below requires a
# genuine zero-feet floor datum and refuses a base-963 ladder.
ELEVATION_DATUM_LABEL_RE = re.compile(
    r"FINISH\s*FLOOR|FIN\.?\s*FL(?:R|OOR)?\b|T\s*/|T\.?O\.?\s|TOP\s+OF\s"
    r"|PARAPET|GUTTER|TRUCK\s+COURT|\bGRADE\b|B\.?O\.?\s|PLATE\s+BEARING"
    r"|\bFLOOR\b|\bENTRY\b|\bEL\s*[:.]",
    re.IGNORECASE,
)
# A feet-inches token near these markers is a dimension or a mounting height,
# never a datum: "+16'-0\" AFF", "35'-3\" OPENING", "@ 24\" O.C.".
_DATUM_EXCLUDE_RE = re.compile(
    r"\bAFF\b|\bO\.?C\.?\b|OPENING|\bTYP\b|SCALE", re.IGNORECASE
)
# A datum VALUE line is short — "45' - 2\"", "EL: 30' - 5 1/8\"" — while a
# note that happens to contain a feet token is a sentence.
_DATUM_VALUE_MAX_CHARS = 20
_DATUM_LABEL_MAX_CHARS = 40
# A label line sits directly above/below its value line in the ladder.
_DATUM_PAIR_GAP_PT = 20.0
# The datum-derived scale is NOISY — the label baseline is offset from its
# leader, so Crow's pairs read 0.79-0.85x the printed scale — and it must
# NEVER override a printed scale. ±30% is still tight enough to reject a
# sixteen-times misparse (INV-03 §3.5).
DATUM_SCALE_TOLERANCE = 0.30

# Keynote legends (23-14 Task 4). A sheet's keyed notes pair a lone TWO-digit
# number block with the note text beside it, under a legend header — and one
# real sheet carries TWO legends (KEYED NOTES and DEMO KEYED NOTES) whose
# numbers collide: Bob's '03' means NEW EIFS SCRATCH COAT in one and REMOVE
# EXISTING LIGHT SCONCE in the other, so an entry must stay grouped under its
# own header and a tag must resolve through the legend belonging to the
# DRAWING it sits in.
KEYNOTE_HEADER_RE = re.compile(
    r"\bKEY(?:ED)?\s*NOTES\b|\bKEYNOTES\b", re.IGNORECASE
)
_KEYNOTE_NUM_RE = re.compile(r"^(\d{2})\.?$")
_KEYNOTE_HEADER_MAX_CHARS = 30
# A legend entry's number block shares its header's column; the general notes
# higher on the sheet have no keynote header above them and join nothing.
_KEYNOTE_COLUMN_TOL_PT = 300.0
_KEYNOTE_PAIR_GAP_PT = 40.0

# Render resolution for facade silhouettes. Elevations are wide-format —
# Crow's south facade band is 2,441 x 335 pt — so the room-fill 160 DPI would
# be a 12-million-pixel clip. 80 DPI resolved every facade on all three
# fixtures in INV-03 §3.2 with no tuning, and the budget below bounds the
# worst case rather than raising any resolution constant (R11 / T-23-56).
FACADE_DPI = 80
MAX_FACADE_PIXELS = 6_000_000


@dataclass
class FacadeResult:
    """One elevation facade measured as a complement-labelled silhouette.

    ``area_sf`` is the DOMINANT solid component — the facade blob — measured
    at the drawing's own printed scale. ``void_areas_sf`` lists enclosed free
    regions inside that blob (openings) so a net area can be reported beside
    the gross; ``sub_components`` lists the OTHER solid components (Bob's
    EIFS sign band is a detached 142 SF component beside the 6,245 SF facade)
    so a positioned keynote tag can later claim one as a material sub-region.

    Identity fields (``title`` … ``excluded``) are stamped by the pipeline
    from :func:`elevation_titles`; the measurement itself knows only geometry.
    """

    area_sf: float                    # dominant component, gross SF
    bbox_ft: tuple = (0.0, 0.0)       # (w_ft, h_ft) of the dominant component
    bbox_pt: tuple = ()               # dominant bbox in PAGE space (x0,y0,x1,y1)
    fill_ratio: float = 0.0           # dominant px / its bbox px
    component_count: int = 0          # solid components >= min_region_sf
    void_areas_sf: List[float] = field(default_factory=list)
    sub_components: List[dict] = field(default_factory=list)
    candidate_id: str = ""
    scale_fpi: Optional[float] = None
    sheet_name: str = ""
    # Identity (from the callout title):
    title: str = ""
    orientation: str = ""
    is_demo: bool = False
    is_interior: bool = False
    excluded: bool = False            # True => not a new-work exterior quantity
    excluded_reason: str = ""
    # Datum band (23-14 Task 2; None until elevation_datums finds a pair):
    datum_height_ft: Optional[float] = None
    band_cropped: bool = False
    area_uncropped_sf: Optional[float] = None
    # Material attribution (23-14 Task 4; text-anchored keynotes only):
    materials: List[dict] = field(default_factory=list)
    needs_review: bool = False
    review_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "area_sf": self.area_sf,
            "bbox_ft": list(self.bbox_ft),
            "bbox_pt": list(self.bbox_pt),
            "fill_ratio": self.fill_ratio,
            "component_count": self.component_count,
            "void_areas_sf": self.void_areas_sf,
            "sub_components": self.sub_components,
            "candidate_id": self.candidate_id,
            "scale_fpi": self.scale_fpi,
            "sheet_name": self.sheet_name,
            "title": self.title,
            "orientation": self.orientation,
            "is_demo": self.is_demo,
            "is_interior": self.is_interior,
            "excluded": self.excluded,
            "excluded_reason": self.excluded_reason,
            "datum_height_ft": self.datum_height_ft,
            "band_cropped": self.band_cropped,
            "area_uncropped_sf": self.area_uncropped_sf,
            "materials": self.materials,
            "needs_review": self.needs_review,
            "review_reason": self.review_reason,
        }


@dataclass
class ElevationTitle:
    """One elevation drawing found by its OWN printed-scale callout title.

    ``scale`` is the :class:`~bobbytailor.deterministic.printed_scale.
    PrintedScale` the title is bound to — each elevation is measured at THAT
    callout's own feet-per-point, never a page-level scale.
    ``callout_bbox_pt`` is the callout's bbox in PAGE space, the space the
    sheet is read in, so callers can stack clips top-to-bottom as a reader
    would.
    """

    title: str
    orientation: str          # "" => not classifiable as an exterior facade
    is_demo: bool
    is_interior: bool
    scale: object             # PrintedScale
    callout_bbox_pt: tuple    # page-space (x0, y0, x1, y1)


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


def measure_facade_area(
    page,
    clip,
    feet_per_point: float,
    dpi: int = FACADE_DPI,
    candidate_id: str = "",
    max_pixels: int = MAX_FACADE_PIXELS,
    min_region_sf: float = MIN_REGION_SF,
    crop_band_pt: Optional[tuple] = None,
) -> Optional[FacadeResult]:
    """Measure one elevation facade as a complement-labelled silhouette.

    Same contract as :func:`measure_enclosed_area` — its sibling: the clip is
    in DRAWING space and is mapped through :func:`to_page_space` before
    rendering; it returns ``None`` on any failure and never raises.

    The recipe (INV-03 §3.2), sharing THE one labeller (:func:`label_mask`):

    1. render the clip and threshold to ink / free;
    2. label the FREE pixels; every free component touching the clip border is
       the BACKGROUND (this is the flood from all four borders);
    3. ``solid = NOT background`` — ink plus everything the outline encloses;
    4. label the solid; the LARGEST component is the facade.

    A room flood fill keeps the voids; this keeps their complement. The same
    drawing that fragments into 63 voids returns one blob here, because a
    facade's joints and reveals subdivide free space but never disconnect ink.

    The render resolution is chosen PER CLIP so the pixel budget is bounded:
    elevations are wide-format, and *dpi* is only ever lowered to fit
    *max_pixels*, never raised (R11 / threat T-23-56).

    Returns a :class:`FacadeResult` carrying the dominant blob's gross area,
    its bbox in feet and in page-space points, its fill ratio, the component
    count, the enclosed void areas (openings — so a net can be reported
    beside the gross), and the other solid components (a detached sign band)
    for later material claiming. Identity fields are left blank for the
    caller to stamp.

    With *crop_band_pt* — a ``(y_top, y_floor)`` PAGE-space pair from
    :func:`datum_wall_band` — the dominant blob is CROPPED to the wall band:
    ``area_sf`` and ``bbox_ft`` describe only the rows between the top datum
    and the finish floor, the uncropped gross is kept in
    ``area_uncropped_sf``, and ``band_cropped`` is set. This is what drops
    the roof, the gable and the annotation tail (INV-03 §3.3: a 56-64 ft
    blob against a 45'-2\" parapet).
    """
    if not feet_per_point or feet_per_point <= 0:
        return None
    try:
        import fitz  # noqa: PLC0415 — optional at import time for test stubs

        page_clip = _rect(to_page_space(page, clip))
        if page_clip is None or page_clip.is_empty:
            return None
        # Per-clip pixel budget: lower the zoom until the render fits. The
        # constant itself is never raised — a hostile 20,000 pt clip renders
        # coarser, not bigger.
        zoom = dpi / 72.0
        n_budget = page_clip.width * zoom * page_clip.height * zoom
        if n_budget > max_pixels and page_clip.width * page_clip.height > 0:
            zoom = math.sqrt(max_pixels / (page_clip.width * page_clip.height))
        pix = page.get_pixmap(
            clip=page_clip, matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csGRAY
        )
    except Exception as exc:  # noqa: BLE001 — a defective page must not kill a run
        logger.debug("facade: render failed for %s: %s", candidate_id, exc)
        return None
    if not pix.width or not pix.height:
        return None

    width, height = pix.width, pix.height
    n_px = width * height
    px_area_sf = (1.0 / (zoom * zoom)) * feet_per_point * feet_per_point

    free = free_mask(pix.samples, n_px)
    free_labelled = label_mask(free, width, height)

    # Background lookup table: free components touching the clip border.
    is_background = bytearray(free_labelled.count + 1)
    for k in range(free_labelled.count):
        if free_labelled.touches_edge[k]:
            is_background[k + 1] = 1

    solid = bytearray(n_px)
    free_labels = free_labelled.labels
    for i in range(n_px):
        if not free[i] or not is_background[free_labels[i]]:
            solid[i] = 1

    solid_labelled = label_mask(solid, width, height)
    if not solid_labelled.count:
        return None

    order = sorted(
        range(solid_labelled.count),
        key=lambda k: solid_labelled.counts[k],
        reverse=True,
    )
    dominant_label = order[0] + 1
    dominant_px = solid_labelled.counts[order[0]]
    if dominant_px * px_area_sf < min_region_sf:
        return None

    # One pass for every solid component's bbox (needed for the dominant's
    # fill ratio AND for sub-component claiming).
    bboxes: dict = {}
    solid_labels = solid_labelled.labels
    for i in range(n_px):
        lab = solid_labels[i]
        if not lab:
            continue
        x = i % width
        y = i // width
        bb = bboxes.get(lab)
        if bb is None:
            bboxes[lab] = [x, y, x, y]
        else:
            if x < bb[0]:
                bb[0] = x
            elif x > bb[2]:
                bb[2] = x
            if y < bb[1]:
                bb[1] = y
            elif y > bb[3]:
                bb[3] = y

    px_len_ft = (1.0 / zoom) * feet_per_point

    def _bbox_ft(bb):
        return (
            round((bb[2] - bb[0] + 1) * px_len_ft, 1),
            round((bb[3] - bb[1] + 1) * px_len_ft, 1),
        )

    def _bbox_pt(bb):
        return (
            round(page_clip.x0 + bb[0] / zoom, 1),
            round(page_clip.y0 + bb[1] / zoom, 1),
            round(page_clip.x0 + (bb[2] + 1) / zoom, 1),
            round(page_clip.y0 + (bb[3] + 1) / zoom, 1),
        )

    dom_bb = bboxes[dominant_label]
    dom_bbox_px = (dom_bb[2] - dom_bb[0] + 1) * (dom_bb[3] - dom_bb[1] + 1)

    # Enclosed voids of the dominant component: free components that touch no
    # border and whose seed pixel now lies inside the dominant solid.
    voids: List[float] = []
    for k in range(free_labelled.count):
        if free_labelled.touches_edge[k]:
            continue
        area = free_labelled.counts[k] * px_area_sf
        if area < min_region_sf:
            continue
        if solid_labels[free_labelled.starts[k]] == dominant_label:
            voids.append(round(area, 1))
    voids.sort(reverse=True)

    sub_components: List[dict] = []
    component_count = 1
    for k in order[1:]:
        area = solid_labelled.counts[k] * px_area_sf
        if area < min_region_sf:
            continue
        component_count += 1
        if len(sub_components) < 32:
            bb = bboxes[k + 1]
            w_ft, h_ft = _bbox_ft(bb)
            sub_components.append(
                {
                    "area_sf": round(area, 1),
                    "bbox_ft": [w_ft, h_ft],
                    "bbox_pt": list(_bbox_pt(bb)),
                }
            )

    dom_w_ft, dom_h_ft = _bbox_ft(dom_bb)
    result = FacadeResult(
        area_sf=round(dominant_px * px_area_sf, 1),
        bbox_ft=(dom_w_ft, dom_h_ft),
        bbox_pt=_bbox_pt(dom_bb),
        fill_ratio=round(dominant_px / dom_bbox_px, 3) if dom_bbox_px else 0.0,
        component_count=component_count,
        void_areas_sf=voids,
        sub_components=sub_components,
        candidate_id=candidate_id,
        scale_fpi=round(feet_per_point * 72.0, 4),
    )

    if crop_band_pt is not None:
        try:
            y_top, y_floor = float(crop_band_pt[0]), float(crop_band_pt[1])
        except (TypeError, ValueError, IndexError):
            return result
        r0 = max(0, int((y_top - page_clip.y0) * zoom))
        r1 = min(height, int((y_floor - page_clip.y0) * zoom) + 1)
        if r1 > r0:
            cropped_px = 0
            cb = None
            for y in range(r0, r1):
                row = y * width
                for x in range(dom_bb[0], dom_bb[2] + 1):
                    if solid_labels[row + x] == dominant_label:
                        cropped_px += 1
                        if cb is None:
                            cb = [x, y, x, y]
                        else:
                            if x < cb[0]:
                                cb[0] = x
                            elif x > cb[2]:
                                cb[2] = x
                            if y < cb[1]:
                                cb[1] = y
                            elif y > cb[3]:
                                cb[3] = y
            if cropped_px and cb is not None:
                result.area_uncropped_sf = result.area_sf
                result.area_sf = round(cropped_px * px_area_sf, 1)
                result.bbox_ft = _bbox_ft(cb)
                result.bbox_pt = _bbox_pt(cb)
                result.band_cropped = True
    return result


def elevation_titles(page) -> List[ElevationTitle]:
    """Every elevation drawing on *page*, found by its OWN callout title.

    Driven off the printed-scale callouts rather than viewport segmentation:
    on Crow, ``segment_viewports`` merges four elevations into two regions and
    mislabels a 2,464 pt band as a legend, while the four scale callouts are
    exact (INV-03 §2.2). The callout is the reliable anchor for "one drawing".

    Two title sources, in order:

    1. A DEDICATED title text line — Bob's prints ``FRONT ELEVATION
       DEMOLITION`` at 25 pt on the callout's own baseline while the callout
       block itself absorbed a keynote sentence, so the drawing's own big
       title outranks whatever text bled into the callout. A candidate line
       must contain the elevation word, be title-short
       (:data:`_ELEV_TITLE_MAX_CHARS`), read HORIZONTALLY (a rotated
       title-block strip like Chelsea's "ELEVATIONS -" is taller than wide in
       page space), and its page-space vertical band must intersect the
       callout's. Lines and callouts pair one-to-one, nearest centre first.
    2. The callout's own extracted title, when it contains the elevation word
       and no dedicated line claimed the callout.

    Classification is by TITLE, never by guess: the orientation is the
    compass/relative word adjacent to the elevation word ("" when none — an
    interior or detail elevation, excluded from exterior quantities);
    demolition/existing and interior intent are flagged so a demolition
    facade is never summed with the new-work facade drawn beside it.

    Sorted by callout position as the sheet is read (page-space y, then x).
    Never raises; a page with no callouts yields ``[]``.
    """
    try:
        import fitz  # noqa: PLC0415
        from bobbytailor.deterministic.printed_scale import (  # noqa: PLC0415
            extract_printed_scales,
        )
    except Exception:  # noqa: BLE001
        return []

    try:
        scales = extract_printed_scales(page) or []
    except Exception:  # noqa: BLE001
        return []
    if not scales:
        return []
    scale_boxes = []
    for s in scales:
        box = _rect(to_page_space(page, _rect(s.bbox_pt)))
        scale_boxes.append(box)

    # Candidate dedicated title lines.
    lines: List[tuple] = []
    try:
        blocks = page.get_text("dict")["blocks"]
    except Exception:  # noqa: BLE001
        blocks = []
    for b in blocks:
        for line in b.get("lines", []):
            txt = " ".join(
                "".join(sp.get("text", "") for sp in line.get("spans", [])).split()
            )
            if not txt or len(txt) > _ELEV_TITLE_MAX_CHARS:
                continue
            if not ELEVATION_TITLE_RE.search(txt):
                continue
            box = _rect(to_page_space(page, _rect(line.get("bbox"))))
            if box is None or box.width <= box.height:
                continue
            lines.append((txt, box))

    # One-to-one pairing: nearest centres first, y-bands must intersect.
    candidates: List[tuple] = []
    for li, (_txt, lbox) in enumerate(lines):
        for si, sbox in enumerate(scale_boxes):
            if sbox is None:
                continue
            if min(lbox.y1, sbox.y1) - max(lbox.y0, sbox.y0) <= 0:
                continue
            d = math.hypot(
                (lbox.x0 + lbox.x1) / 2 - (sbox.x0 + sbox.x1) / 2,
                (lbox.y0 + lbox.y1) / 2 - (sbox.y0 + sbox.y1) / 2,
            )
            candidates.append((d, li, si))
    candidates.sort()
    titles_by_scale: dict = {}
    used_lines = set()
    for _d, li, si in candidates:
        if li in used_lines or si in titles_by_scale:
            continue
        used_lines.add(li)
        titles_by_scale[si] = lines[li][0]

    out: List[ElevationTitle] = []
    for si, s in enumerate(scales):
        title = titles_by_scale.get(si)
        if title is None:
            if ELEVATION_TITLE_RE.search(s.title or ""):
                title = s.title
            else:
                continue
        m = _ELEV_ORIENT_BEFORE_RE.search(title)
        orientation = m.group(1) if m else ""
        if not orientation:
            m = _ELEV_ORIENT_AFTER_RE.search(title)
            orientation = m.group(1) if m else ""
        orientation = " ".join(orientation.upper().split())
        box = scale_boxes[si]
        out.append(
            ElevationTitle(
                title=title,
                orientation=orientation,
                is_demo=bool(_ELEV_DEMO_RE.search(title)),
                is_interior=bool(_ELEV_INTERIOR_RE.search(title)),
                scale=s,
                callout_bbox_pt=(
                    tuple(box) if box is not None else tuple(s.bbox_pt)
                ),
            )
        )
    out.sort(key=lambda e: (e.callout_bbox_pt[1], e.callout_bbox_pt[0]))
    return out


def elevation_datums(page, clip) -> List[tuple]:
    """``[(y_pt, feet, label), ...]`` — the drawing's own vertical ruler.

    Parses a vertical position and a feet value from datum texts inside
    *clip* (PAGE space, the space the sheet is read in — the same contract as
    :func:`drawing_ceiling_heights`). A datum is either a short value line
    carrying its own label ("EL: 30' - 5 1/8\""), or a short value line
    ("45' - 2\"") paired with the label line printed within
    :data:`_DATUM_PAIR_GAP_PT` of it ("T/ PANEL"). Reuses
    :data:`FEET_INCHES_RE` — THE feet-and-inches parser of this module — with
    a leading-minus check for below-grade datums ("-4' - 0\" TRUCK COURT").

    Mounting heights and dimensions are excluded by MARKER
    (:data:`_DATUM_EXCLUDE_RE`), not by band: "+16'-0\" AFF" is in any
    plausible band and is an awning height, not a datum.

    Sorted by vertical position. Never raises; no ladder yields ``[]``.
    """
    box = _rect(clip)
    if box is None:
        return []
    try:
        blocks = page.get_text("dict")["blocks"]
    except Exception:  # noqa: BLE001 — a datum harvest must never kill a run
        return []

    values: List[tuple] = []
    labels: List[tuple] = []
    for b in blocks:
        for line in b.get("lines", []):
            txt = " ".join(
                "".join(sp.get("text", "") for sp in line.get("spans", [])).split()
            )
            if not txt:
                continue
            pbox = _rect(to_page_space(page, _rect(line.get("bbox"))))
            if pbox is None:
                continue
            if not (box.x0 <= pbox.x0 and pbox.x1 <= box.x1
                    and box.y0 <= pbox.y0 and pbox.y1 <= box.y1):
                continue
            if _DATUM_EXCLUDE_RE.search(txt):
                continue
            m = FEET_INCHES_RE.search(txt)
            is_label = bool(ELEVATION_DATUM_LABEL_RE.search(txt))
            if m and len(txt) <= _DATUM_VALUE_MAX_CHARS:
                feet = int(m.group(1)) + int(m.group(2)) / 12.0
                if m.group(3) and m.group(4):
                    try:
                        feet += int(m.group(3)) / int(m.group(4)) / 12.0
                    except ZeroDivisionError:
                        pass
                if m.start() > 0 and txt[m.start() - 1] == "-":
                    feet = -feet
                values.append((pbox, feet, txt, is_label))
            elif is_label and len(txt) <= _DATUM_LABEL_MAX_CHARS:
                labels.append((pbox, txt))

    out: List[tuple] = []
    for vbox, feet, vtxt, inline_label in values:
        y_centre = round((vbox.y0 + vbox.y1) / 2.0, 1)
        if inline_label:
            out.append((y_centre, feet, vtxt))
            continue
        best = None
        best_gap = _DATUM_PAIR_GAP_PT
        for lbox, ltxt in labels:
            gap = abs((lbox.y0 + lbox.y1) / 2.0 - (vbox.y0 + vbox.y1) / 2.0)
            if gap > best_gap:
                continue
            # The label and its value share the ladder column; allow a small
            # negative overlap for staggered leaders.
            if min(vbox.x1, lbox.x1) - max(vbox.x0, lbox.x0) < -60.0:
                continue
            best, best_gap = ltxt, gap
        if best is not None:
            out.append((y_centre, feet, best))
    return sorted(out)


def datum_wall_band(datums) -> Optional[tuple]:
    """``(y_top_pt, y_floor_pt, span_ft)`` — the wall band of a datum ladder.

    From the TOP datum down to the FINISH-FLOOR datum (the entry whose feet
    value is zero). Cropping the facade blob to this band drops the roof, the
    gable and the annotation tail — the reason a Crow blob bbox reads
    56-64 ft against a 45'-2\" parapet (INV-03 §3.3).

    Requires a genuine zero-feet floor: Moxy's civic ladder is sea-level
    based (T/ ROOF 969'-2\") and correctly yields ``None`` — a drawing with
    no datum pair is FLAGGED by the caller, never cropped by a guess.
    """
    if not datums or len(datums) < 2:
        return None
    floor = None
    for y, feet, _label in datums:
        if abs(feet) <= 0.01:
            floor = (y, feet)
    if floor is None:
        return None
    top = max(datums, key=lambda d: d[1])
    if top[1] <= 1.0 or top[0] >= floor[0]:
        return None
    return (top[0], floor[0], round(top[1] - floor[1], 2))


def datum_scale_check(
    datums,
    feet_per_point: float,
    tolerance: float = DATUM_SCALE_TOLERANCE,
) -> Optional[bool]:
    """Is the printed scale PLAUSIBLE against the datum ladder's own geometry?

    ``|f_a - f_b| / |y_a - y_b|`` over the ladder's extreme pair is a free
    feet-per-point estimate. It is noisy (label baselines are offset from
    their leaders — Crow measures 0.79-0.85x printed) so it may only ever be
    a ±*tolerance* plausibility band and must NEVER override a printed
    scale; it exists to reject an order-of-magnitude misparse (a 16x wrong
    scale reads ~13x outside the band).

    Returns ``True``/``False``, or ``None`` when the ladder cannot answer
    (fewer than two distinct datums, or no printed scale to check).
    """
    if not feet_per_point or feet_per_point <= 0 or not datums:
        return None
    lo = min(datums, key=lambda d: d[1])
    hi = max(datums, key=lambda d: d[1])
    dy = abs(hi[0] - lo[0])
    dft = hi[1] - lo[1]
    if dy < 1.0 or dft < 1.0:
        return None
    ratio = (dft / dy) / feet_per_point
    return (1.0 - tolerance) <= ratio <= (1.0 + tolerance)


def keynote_legend(page) -> dict:
    """``{header_text: {number: note_text}}`` — keynote legends BY HEADER.

    Pairing a number block with its note text reuses THE pairing primitive
    from plan 23-05 (:func:`tag_pairing.pair_two_token_tags`): same reading
    frame, bounded gap, one-to-one. Each paired entry then joins the nearest
    :data:`KEYNOTE_HEADER_RE` header ABOVE it (page space) within its column
    (:data:`_KEYNOTE_COLUMN_TOL_PT`); an entry with no keynote header above
    it — a numbered general note — joins nothing.

    Grouping by header is the whole point: the same number means different
    things in the new-work legend and the demolition legend, and the correct
    one is chosen by which DRAWING the tag sits in
    (:func:`keynote_tags` + the caller's demo flag). Never raises.
    """
    try:
        import fitz  # noqa: PLC0415
        from bobbytailor.deterministic.tag_pairing import (  # noqa: PLC0415
            page_tag_lines,
            pair_two_token_tags,
        )
    except Exception:  # noqa: BLE001
        return {}
    try:
        lines = page_tag_lines(page)
    except Exception:  # noqa: BLE001
        return {}

    headers: List[tuple] = []
    for line in lines:
        text = line.text.strip()
        if len(text) <= _KEYNOTE_HEADER_MAX_CHARS and KEYNOTE_HEADER_RE.search(text):
            box = _rect(to_page_space(page, _rect(line.bbox_pt)))
            if box is not None:
                headers.append((text, box))
    if not headers:
        return {}

    try:
        pairs = pair_two_token_tags(
            lines,
            lambda t: bool(_KEYNOTE_NUM_RE.match(t.strip())),
            lambda t: len(t.strip()) > 8 and not _KEYNOTE_NUM_RE.match(t.strip()),
            max_gap_pt=_KEYNOTE_PAIR_GAP_PT,
        )
    except Exception:  # noqa: BLE001
        return {}

    out: dict = {}
    for num_line, text_line in pairs:
        nbox = _rect(to_page_space(page, _rect(num_line.bbox_pt)))
        if nbox is None:
            continue
        best = None
        best_gap = float("inf")
        for header_text, hbox in headers:
            gap = nbox.y0 - hbox.y1
            if gap < -2.0 or abs(nbox.x0 - hbox.x0) > _KEYNOTE_COLUMN_TOL_PT:
                continue
            if gap < best_gap:
                best, best_gap = header_text, gap
        if best is None:
            continue
        number = _KEYNOTE_NUM_RE.match(num_line.text.strip()).group(1)
        out.setdefault(best, {}).setdefault(number, text_line.text.strip())
    return out


def keynote_tags(page, clip) -> List[tuple]:
    """``[(number, x_pt, y_pt), ...]`` — positioned keynote tags inside *clip*.

    The lone two-digit number blocks inside a drawing's clip (PAGE space,
    like every elevation clip) — the markers whose meaning
    :func:`keynote_legend` holds. Positions are page-space centres so a tag
    can be tested against a facade sub-component's bbox. Never raises.
    """
    box = _rect(clip)
    if box is None:
        return []
    try:
        from bobbytailor.deterministic.tag_pairing import (  # noqa: PLC0415
            page_tag_lines,
        )

        lines = page_tag_lines(page)
    except Exception:  # noqa: BLE001
        return []
    out: List[tuple] = []
    for line in lines:
        m = _KEYNOTE_NUM_RE.match(line.text.strip())
        if not m:
            continue
        pbox = _rect(to_page_space(page, _rect(line.bbox_pt)))
        if pbox is None:
            continue
        if not (box.x0 <= pbox.x0 and pbox.x1 <= box.x1
                and box.y0 <= pbox.y0 and pbox.y1 <= box.y1):
            continue
        out.append(
            (m.group(1), (pbox.x0 + pbox.x1) / 2.0, (pbox.y0 + pbox.y1) / 2.0)
        )
    return out


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
