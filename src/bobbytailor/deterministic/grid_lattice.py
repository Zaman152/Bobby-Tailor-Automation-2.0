"""Structural grid-lattice marker detection — the columns `cluster_symbols` cannot see.

WHY THIS MODULE EXISTS
----------------------
Crow's 132 columns were reported as "unfindable". They are not. On the OVERALL
FLOOR PLAN (page 0) there are **120 closed 1.44 x 1.56 pt rectangles sitting one
per cell on a 20 x 6 sub-grid of the sheet's own printed A..H / 1..22 gridlines,
at 100% occupancy with no stray and no duplicate**. That is a shape whose
positions are *predicted by the printed text and then found* — not a count that
happened to look plausible.

``symbols.py`` cannot recover them, and no amount of tuning will make it:

* the four marker edges are four separate single-line paths drawn in the SAME
  ``(type, stroke, fill, width)`` style class as the gridlines, so the style
  partition that `symbols.py` docstring claims will separate CAD blocks from
  "the connective wall/grid network" does not separate anything here;
* a gridline dash endpoint lands 0.805 pt from a marker corner — inside
  ``symbols.ENDPOINT_EPS_PT`` — so the dash unions into the marker's connected
  component, and the resulting shape signature depends on how much dash happened
  to attach. The dash phase differs per intersection, so the single lattice
  SHATTERS into ``SYM-2`` (56) + ``SYM-32`` (5) + ``SYM-43`` (3) + ``SYM-45`` (3)
  + 53 fragments below ``MIN_INSTANCES``.

Loosening ``ENDPOINT_EPS_PT`` / ``QUANT_PT`` / the style key are all global knobs
that would re-break the groups which currently work, and none of them can undo a
connection that is geometrically real at 0.8 pt. So this module is **strictly
additive**: it re-reads the same primitives with a different, position-first
question and never touches ``symbols.py``.

THE RECIPE (measured, not tuned)
--------------------------------
1. ``closed_rects``   — index axis-aligned H/V segments by exact endpoint and
   emit every rectangle whose four edges are all present.
2. ``grid_axes``      — collinear runs of >= ``AXIS_MIN_TOKENS`` bubble tokens
   (``^\\d{1,2}$`` / ``^[A-Z]$``); each run is a candidate axis, carrying its
   labels so an instance can be named by its cell (``B-7``).
3. ``lattice_groups`` — for each (X-axis, Y-axis, marker-size) triple, snap
   marker centres to the axes and accept ONLY IF: ``n >= MIN_MARKERS``,
   ``>= 2`` distinct X **and** ``>= 2`` distinct Y, occupancy ``>= 0.9``, and no
   duplicate cell.

The ``>= 2 distinct Y`` requirement is the load-bearing one. Ground truth §10
was fooled by a 136-mark collinear tick row and concluded "no 2-D lattice
exists". Every tick row has ``yspan = 0`` -> one distinct Y -> **rejected by
construction, not by tuning**. The same is true of the 40-mark panel-joint row.

WHAT THIS MODULE REFUSES TO DO
------------------------------
It publishes ``count = 120`` on Crow page 0. Golden is 132. **It does not close
that gap.**

INV-B proposed a completion rule — "extend the six detected column lines across
the full 22-line number axis" -> 6 x 22 = 132 — and was candid that the rule was
chosen *after* seeing that golden is 132. Re-measured here, the drawing gives no
warrant for it. The occupied block is rows B..G of A..H and columns 2..21 of
1..22: **both axes are missing exactly their two end positions**, and all four
footprint edges (x=439, x=2481, y=1200, y=1828) carry the same continuous
long-line panel geometry (2636-9795 pt of it per edge). Nothing in the drawing
distinguishes "the end COLUMNS are concealed in the panel" from "the end ROWS
are concealed in the panel". Extending the number axis gives 132; extending the
letter axis gives 160; extending both gives 176. Exactly one of those matches
the answer key, and picking it because it matches is the coincidence trap that
has already cost this project days.

So :class:`LatticeGroup` publishes ``count`` = what is drawn, and every
extension the geometry equally supports as a *flagged, unconfirmed*
:class:`CompletionHypothesis`. ``completion_candidate`` is populated ONLY when a
single axis qualifies — when the drawing itself picks. On Crow it is ``None``,
``needs_review`` is True, and the run asks a human. That is the product: what
can be measured is measured, everything else is explicitly flagged.

Zero API. Pure geometry + the drawing's own printed text.
"""
from __future__ import annotations

import logging
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from bobbytailor.deterministic.dimensions import _visible_drawings
from bobbytailor.deterministic.symbols import _harvest_primitives

logger = logging.getLogger(__name__)

# ── Tuning constants ─────────────────────────────────────────────────────────
# Every one of these is a SHAPE constraint. None of them is a count threshold,
# and none may ever be adjusted to make a total match a golden take-off.

# Coordinate quantization for exact-endpoint rectangle closure (PDF points).
COORD_QUANT = 0.01
# Plausible plan-scale structural marker, in INCHES on the real building. A
# 10"-square HSS column prints inside this; so would a 6" pipe or a 24" pier.
# Deliberately generous — rejection is the lattice's job, not the size window's.
MARKER_MIN_IN = 4.0
MARKER_MAX_IN = 36.0
# A column marker is square-ish. Generous: 1.44 x 1.56 pt is 1.08.
MARKER_ASPECT_MAX = 2.0
# Grid-bubble text run -> candidate axis.
AXIS_TOKEN_RE = re.compile(r"^(?:\d{1,2}|[A-Z])$")
AXIS_MIN_TOKENS = 4
AXIS_COLLINEAR_TOL_PT = 2.0
# Marker centre -> gridline snap tolerance.
SNAP_TOL_PT = 6.0
# Lattice acceptance. n >= 12 is "a structural bay grid", not "enough to match".
MIN_MARKERS = 12
MIN_DISTINCT_X = 2
MIN_DISTINCT_Y = 2
MIN_OCCUPANCY = 0.9
# Resource-exhaustion caps (threat model), mirroring symbols.MAX_PRIMITIVES.
MAX_PRIMITIVES = 200_000
MAX_RECTS = 20_000
MAX_AXES_PER_ORIENTATION = 12
# Two markers this close are the same physical object drawn twice.
COLOCATED_TOL_PT = 3.0

_EPS = 1e-9

Point = Tuple[float, float]
Rect = Tuple[float, float, float, float]


# ── Data ─────────────────────────────────────────────────────────────────────


@dataclass
class GridAxis:
    """One printed gridline axis recovered from bubble text.

    ``orientation`` is "x" when the labels vary along X (a row of number
    bubbles, giving the vertical gridlines) and "y" when they vary along Y.
    """

    orientation: str
    coords: List[float]
    labels: List[str]
    text_line_pt: float = 0.0   # the shared perpendicular coordinate of the run

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.coords)

    @property
    def span_pt(self) -> float:
        return (self.coords[-1] - self.coords[0]) if len(self.coords) > 1 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orientation": self.orientation,
            "coords": [round(c, 2) for c in self.coords],
            "labels": list(self.labels),
            "text_line_pt": round(self.text_line_pt, 2),
        }


@dataclass
class CompletionHypothesis:
    """An extrapolation the geometry ALLOWS but does not establish.

    Never a measurement. ``confirmed`` is False until a human says otherwise,
    and a hypothesis must never be summed into a published quantity.
    """

    axis: str                  # "x" | "y" | "both"
    count: int
    rule: str
    missing_cells: int
    confirmed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "axis": self.axis,
            "count": self.count,
            "rule": self.rule,
            "missing_cells": self.missing_cells,
            "confirmed": self.confirmed,
        }


@dataclass
class LatticeGroup:
    """One 2-D lattice of identical markers on printed gridline intersections."""

    candidate_id: str
    count: int
    marker_size_pt: Tuple[float, float]
    marker_size_in: Tuple[float, float]
    n_cols: int
    n_rows: int
    occupancy: float
    cell_ids: List[str]
    instance_bboxes_pt: List[Rect]
    axis_x: GridAxis
    axis_y: GridAxis
    # Every extension the drawing equally supports. Flagged, never summed.
    completion_hypotheses: List[CompletionHypothesis] = field(default_factory=list)
    # Populated ONLY when exactly one axis qualifies — i.e. when the drawing
    # itself picks the extension. None means "the drawing does not say".
    completion_candidate: Optional[int] = None
    needs_review: bool = True
    review_reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["axis_x"] = self.axis_x.to_dict()
        d["axis_y"] = self.axis_y.to_dict()
        d["completion_hypotheses"] = [h.to_dict() for h in self.completion_hypotheses]
        d["marker_size_pt"] = list(self.marker_size_pt)
        d["marker_size_in"] = list(self.marker_size_in)
        return d


# ── Step 1: closed rectangles ────────────────────────────────────────────────


def closed_rects(prims: Sequence, max_dim_pt: float) -> List[Rect]:
    """Every axis-aligned rectangle up to ``max_dim_pt`` whose 4 edges exist.

    A rectangle is emitted only when all four edges are present as separate
    primitives at matching endpoints. This is what makes the detector immune to
    the gridline dash: the dash is one segment on one side of the intersection
    and can never close a box.
    """
    if max_dim_pt <= 0:
        return []
    horiz: Dict[Tuple[float, float], List[float]] = defaultdict(list)
    vert = set()
    for p in prims:
        if getattr(p, "kind", None) != "l":
            continue
        x1, y1 = p.e1
        x2, y2 = p.e2
        if abs(y1 - y2) < COORD_QUANT and abs(x1 - x2) > COORD_QUANT:
            key = (round(min(x1, x2), 2), round(max(x1, x2), 2))
            horiz[key].append(round(y1, 2))
        elif abs(x1 - x2) < COORD_QUANT and abs(y1 - y2) > COORD_QUANT:
            vert.add((round(x1, 2), round(min(y1, y2), 2), round(max(y1, y2), 2)))

    out: List[Rect] = []
    for (x_lo, x_hi), ys in horiz.items():
        if x_hi - x_lo > max_dim_pt:
            continue
        levels = sorted(set(ys))
        for i in range(len(levels)):
            for j in range(i + 1, len(levels)):
                y_lo, y_hi = levels[i], levels[j]
                if y_hi - y_lo > max_dim_pt:
                    break  # levels are sorted: every later j is further away
                if (x_lo, y_lo, y_hi) in vert and (x_hi, y_lo, y_hi) in vert:
                    out.append((x_lo, y_lo, x_hi, y_hi))
                    if len(out) >= MAX_RECTS:
                        logger.warning(
                            "grid_lattice: closed-rect cap %d reached; truncating",
                            MAX_RECTS,
                        )
                        return out
    return out


# ── Step 2: grid axes from printed bubble text ───────────────────────────────


def _is_grid_axis_labelling(labels: Sequence[str]) -> bool:
    """Is this run of tokens actually a GRIDLINE axis, or incidental text?

    Three structural properties of a printed grid, none of them a threshold:

    * **Distinct.** A gridline axis names every line uniquely — that is what
      makes ``B-7`` mean one place. Repeated labels are not an axis.
    * **Homogeneous.** An axis is numbered OR lettered, never both.
    * **Ordered.** Bubbles run in sequence along the axis, either direction.

    Measured cost of NOT checking this: Chelsea page 17 carries roof-pitch
    callouts whose glyphs read ``3 2 4 / 3 2 4 / ...`` across the sheet. Twelve
    pitch-triangle boxes snapped to that "axis" and produced a 6 x 2 lattice at
    100% occupancy — a textbook false positive on a second plan set, which the
    four-plan-set rule rejects outright. Requiring distinct, homogeneous,
    ordered labels kills it by construction.
    """
    labels = list(labels)
    if len(set(labels)) != len(labels):
        return False
    if all(t.isdigit() for t in labels):
        keys: List[Any] = [int(t) for t in labels]
    elif all(t.isalpha() for t in labels):
        keys = labels
    else:
        return False
    return keys == sorted(keys) or keys == sorted(keys, reverse=True)


def _cluster_1d(values: Sequence[Tuple[float, Any]], tol: float):
    """Group ``(coord, payload)`` pairs into runs whose coord differs by < tol."""
    ordered = sorted(values, key=lambda v: v[0])
    runs: List[List[Tuple[float, Any]]] = []
    for coord, payload in ordered:
        if runs and abs(coord - runs[-1][-1][0]) <= tol:
            runs[-1].append((coord, payload))
        else:
            runs.append([(coord, payload)])
    return runs


def grid_axes(page) -> Tuple[List[GridAxis], List[GridAxis]]:
    """Candidate (x-axes, y-axes) read off collinear runs of grid-bubble text.

    Returns axes whose LABELS come from the drawing, so every detected instance
    can be named by the cell the drawing itself names it by.
    """
    try:
        words = page.get_text("words")
    except Exception:  # noqa: BLE001 — a page with no text layer is not an error
        return [], []

    tokens = []
    for w in words:
        text = str(w[4]).strip()
        if not AXIS_TOKEN_RE.match(text):
            continue
        tokens.append(((w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0, text))

    x_axes: List[GridAxis] = []
    y_axes: List[GridAxis] = []

    # A horizontal run of bubbles (shared Y) marks the VERTICAL gridlines -> x-axis.
    for run in _cluster_1d([(cy, (cx, t)) for cx, cy, t in tokens], AXIS_COLLINEAR_TOL_PT):
        seen: Dict[float, str] = {}
        for _, (cx, t) in run:
            seen.setdefault(round(cx, 2), t)
        if len(seen) < AXIS_MIN_TOKENS:
            continue
        coords = sorted(seen)
        if not _is_grid_axis_labelling([seen[c] for c in coords]):
            continue
        x_axes.append(
            GridAxis(
                orientation="x",
                coords=coords,
                labels=[seen[c] for c in coords],
                text_line_pt=sum(c for c, _ in run) / len(run),
            )
        )

    # A vertical run of bubbles (shared X) marks the HORIZONTAL gridlines -> y-axis.
    for run in _cluster_1d([(cx, (cy, t)) for cx, cy, t in tokens], AXIS_COLLINEAR_TOL_PT):
        seen = {}
        for _, (cy, t) in run:
            seen.setdefault(round(cy, 2), t)
        if len(seen) < AXIS_MIN_TOKENS:
            continue
        coords = sorted(seen)
        if not _is_grid_axis_labelling([seen[c] for c in coords]):
            continue
        y_axes.append(
            GridAxis(
                orientation="y",
                coords=coords,
                labels=[seen[c] for c in coords],
                text_line_pt=sum(c for c, _ in run) / len(run),
            )
        )

    x_axes.sort(key=lambda a: (-len(a), a.text_line_pt))
    y_axes.sort(key=lambda a: (-len(a), a.text_line_pt))
    return (
        x_axes[:MAX_AXES_PER_ORIENTATION],
        y_axes[:MAX_AXES_PER_ORIENTATION],
    )


# ── Step 3: the lattice ──────────────────────────────────────────────────────


def _snap(value: float, coords: Sequence[float], tol: float) -> Optional[int]:
    best_i, best_d = None, tol
    for i, c in enumerate(coords):
        d = abs(value - c)
        if d < best_d:
            best_i, best_d = i, d
    return best_i


def _completion_hypotheses(
    occupied_x: Sequence[int],
    occupied_y: Sequence[int],
    axis_x: GridAxis,
    axis_y: GridAxis,
) -> List[CompletionHypothesis]:
    """Every axis extension the drawing ALLOWS. None of them is a measurement.

    An axis qualifies only when the occupied positions are a contiguous run
    whose gaps are exclusively at the axis ENDS — the "the end members are
    concealed inside the perimeter panel" reading. An interior gap means the
    lattice genuinely stops, and no extension is proposed.
    """

    def _end_gaps_only(occ: Sequence[int], axis_len: int) -> int:
        occ = sorted(set(occ))
        if not occ:
            return 0
        if occ != list(range(occ[0], occ[-1] + 1)):
            return 0  # interior gap: the lattice really does stop
        return (occ[0]) + (axis_len - 1 - occ[-1])

    nx, ny = len(set(occupied_x)), len(set(occupied_y))
    gap_x = _end_gaps_only(occupied_x, len(axis_x))
    gap_y = _end_gaps_only(occupied_y, len(axis_y))

    out: List[CompletionHypothesis] = []
    if gap_x:
        out.append(
            CompletionHypothesis(
                axis="x",
                count=ny * len(axis_x),
                rule=(
                    "each detected row extends to every gridline on the %s axis "
                    "(%s..%s); the %d end position(s) are assumed concealed in "
                    "the perimeter construction"
                    % (
                        axis_x.orientation,
                        axis_x.labels[0],
                        axis_x.labels[-1],
                        gap_x,
                    )
                ),
                missing_cells=ny * len(axis_x) - ny * nx,
            )
        )
    if gap_y:
        out.append(
            CompletionHypothesis(
                axis="y",
                count=nx * len(axis_y),
                rule=(
                    "each detected column extends to every gridline on the %s "
                    "axis (%s..%s); the %d end position(s) are assumed concealed "
                    "in the perimeter construction"
                    % (
                        axis_y.orientation,
                        axis_y.labels[0],
                        axis_y.labels[-1],
                        gap_y,
                    )
                ),
                missing_cells=nx * len(axis_y) - ny * nx,
            )
        )
    if gap_x and gap_y:
        out.append(
            CompletionHypothesis(
                axis="both",
                count=len(axis_x) * len(axis_y),
                rule=(
                    "the lattice fills the full printed grid %s..%s x %s..%s"
                    % (
                        axis_x.labels[0],
                        axis_x.labels[-1],
                        axis_y.labels[0],
                        axis_y.labels[-1],
                    )
                ),
                missing_cells=len(axis_x) * len(axis_y) - ny * nx,
            )
        )
    return out


def lattice_groups(
    rects: Sequence[Rect],
    x_axes: Sequence[GridAxis],
    y_axes: Sequence[GridAxis],
    fpp: float,
) -> List[LatticeGroup]:
    """Accept marker-size classes that form a full 2-D lattice on printed axes.

    Returns at most one group per (x-axis, y-axis) pair — the largest surviving
    marker class — and never two groups sharing a marker class.
    """
    if fpp <= 0 or not rects or not x_axes or not y_axes:
        return []

    by_size: Dict[Tuple[float, float], List[Rect]] = defaultdict(list)
    for r in rects:
        by_size[(round(r[2] - r[0], 2), round(r[3] - r[1], 2))].append(r)
    sized = [
        (size, rs) for size, rs in by_size.items() if len(rs) >= MIN_MARKERS
    ]

    accepted: List[LatticeGroup] = []
    used_sizes = set()
    for ax in x_axes:
        for ay in y_axes:
            best: Optional[Tuple] = None
            for size, rs in sized:
                if size in used_sizes:
                    continue
                cells: List[Tuple[int, int]] = []
                boxes: List[Rect] = []
                for r in rs:
                    cx, cy = (r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0
                    ix = _snap(cx, ax.coords, SNAP_TOL_PT)
                    iy = _snap(cy, ay.coords, SNAP_TOL_PT)
                    if ix is None or iy is None:
                        continue
                    cells.append((ix, iy))
                    boxes.append(r)
                if len(cells) < MIN_MARKERS:
                    continue
                ux = {c[0] for c in cells}
                uy = {c[1] for c in cells}
                if len(ux) < MIN_DISTINCT_X or len(uy) < MIN_DISTINCT_Y:
                    continue
                if len(set(cells)) != len(cells):
                    continue  # duplicate cell: not one-marker-per-intersection
                occ = len(cells) / float(len(ux) * len(uy))
                if occ < MIN_OCCUPANCY - _EPS:
                    continue
                cand = (len(cells), size, cells, boxes, ux, uy, occ)
                if best is None or cand[0] > best[0]:
                    best = cand
            if best is None:
                continue
            n, size, cells, boxes, ux, uy, occ = best
            used_sizes.add(size)
            order = sorted(range(n), key=lambda i: (cells[i][1], cells[i][0]))
            hyps = _completion_hypotheses(sorted(ux), sorted(uy), ax, ay)
            single = [h for h in hyps if h.axis in ("x", "y")]
            completion = single[0].count if len(single) == 1 else None
            if completion is not None:
                reason = (
                    "the drawing shows %d marker(s); %d more are inferred by the "
                    "one axis that admits an extension — CONFIRM before pricing"
                    % (n, completion - n)
                )
            elif hyps:
                reason = (
                    "the drawing shows %d marker(s). Both grid axes are missing "
                    "only their end positions, so the drawing does NOT determine "
                    "how many further markers are concealed in the perimeter: "
                    "%s are all equally supported. CONFIRM which, if any, applies."
                    % (n, " / ".join(str(h.count) for h in hyps))
                )
            else:
                reason = (
                    "the drawing shows %d marker(s) and the lattice is complete "
                    "on both printed axes" % n
                )
            accepted.append(
                LatticeGroup(
                    candidate_id="",
                    count=n,
                    marker_size_pt=size,
                    marker_size_in=(
                        round(size[0] * fpp * 12.0, 1),
                        round(size[1] * fpp * 12.0, 1),
                    ),
                    n_cols=len(ux),
                    n_rows=len(uy),
                    occupancy=round(occ, 4),
                    cell_ids=[
                        "%s-%s" % (ay.labels[cells[i][1]], ax.labels[cells[i][0]])
                        for i in order
                    ],
                    instance_bboxes_pt=[boxes[i] for i in order],
                    axis_x=ax,
                    axis_y=ay,
                    completion_hypotheses=hyps,
                    completion_candidate=completion,
                    needs_review=True,
                    review_reason=reason,
                    evidence={
                        "axis_x_labels": "%s..%s" % (ax.labels[0], ax.labels[-1]),
                        "axis_y_labels": "%s..%s" % (ay.labels[0], ay.labels[-1]),
                        "axis_x_len": len(ax),
                        "axis_y_len": len(ay),
                        "occupied_cols": [ax.labels[i] for i in sorted(ux)],
                        "occupied_rows": [ay.labels[i] for i in sorted(uy)],
                        "off_grid_markers": 0,
                        "marker_span_pt": (
                            round(
                                max(b[0] for b in boxes) - min(b[0] for b in boxes), 1
                            ),
                            round(
                                max(b[1] for b in boxes) - min(b[1] for b in boxes), 1
                            ),
                        ),
                    },
                )
            )
    accepted.sort(key=lambda g: (-g.count, g.marker_size_pt))
    for i, g in enumerate(accepted, start=1):
        g.candidate_id = "LAT-%d" % i
    return accepted


# ── Entry point ──────────────────────────────────────────────────────────────


def detect_grid_lattices(
    page,
    fpp: float,
    exclude_rects: Optional[Sequence] = None,
    *,
    doc=None,
    page_index: int = 0,
) -> List[LatticeGroup]:
    """Detect structural marker lattices on one page. Additive; never raises.

    ``fpp`` is feet-per-point from the scale solver and is what turns the marker
    size window from a magic point value into a real-world inch range, so the
    same constants work at 1"=40' and at 1/8"=1'.
    """
    try:
        if fpp is None or fpp <= 0:
            return []
        if doc is None:
            doc = page.parent

        prims = _harvest_primitives(_visible_drawings(page, doc))
        if not prims:
            return []
        if len(prims) > MAX_PRIMITIVES:
            logger.warning(
                "grid_lattice: page %d has %d primitives (> %d); skipping",
                page_index,
                len(prims),
                MAX_PRIMITIVES,
            )
            return []

        max_dim_pt = (MARKER_MAX_IN / 12.0) / fpp
        min_dim_pt = (MARKER_MIN_IN / 12.0) / fpp
        rects = [
            r
            for r in closed_rects(prims, max_dim_pt)
            if min_dim_pt - _EPS <= (r[2] - r[0])
            and min_dim_pt - _EPS <= (r[3] - r[1])
            and max(r[2] - r[0], r[3] - r[1])
            <= MARKER_ASPECT_MAX * min(r[2] - r[0], r[3] - r[1]) + _EPS
            and not _center_in(r, exclude_rects)
        ]
        if len(rects) < MIN_MARKERS:
            return []

        x_axes, y_axes = grid_axes(page)
        groups = lattice_groups(rects, x_axes, y_axes, fpp)
        if groups:
            logger.info(
                "grid_lattice: page %d -> %d lattice(s): %s",
                page_index,
                len(groups),
                ", ".join(
                    "%s n=%d %dx%d occ=%.2f"
                    % (g.candidate_id, g.count, g.n_cols, g.n_rows, g.occupancy)
                    for g in groups
                ),
            )
        return groups
    except Exception as exc:  # noqa: BLE001 — additive: never break a run
        logger.debug("grid_lattice failed on page %d: %s", page_index, exc)
        return []


def _center_in(rect: Rect, rects: Optional[Sequence]) -> bool:
    if not rects:
        return False
    cx, cy = (rect[0] + rect[2]) / 2.0, (rect[1] + rect[3]) / 2.0
    for r in rects:
        try:
            x0, y0, x1, y1 = r
        except (TypeError, ValueError):
            continue
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return True
    return False


# ── Duplicate suppression ────────────────────────────────────────────────────


def lattice_shadowed_symbol_ids(
    symbol_groups: Sequence,
    lattices: Sequence[LatticeGroup],
    *,
    min_fraction: float = 0.8,
) -> List[str]:
    """Symbol candidate ids whose instances ARE the lattice markers.

    ``cluster_symbols`` shatters the lattice into fragments and the semantic
    pass then names the largest fragment something plausible — on Crow it named
    56 column markers "Bollards", which is the whole of the reported "Bollards
    56 vs 28" defect. Those fragments are the SAME physical objects the lattice
    now counts properly, so publishing both double-counts the drawing.

    A group is shadowed only when ``min_fraction`` of its instances sit on a
    lattice marker. Nothing is suppressed on a page with no lattice, which is
    every page across all four plan sets except Crow p0.
    """
    if not symbol_groups or not lattices:
        return []
    marks: List[Point] = []
    for lat in lattices:
        for b in lat.instance_bboxes_pt:
            marks.append(((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0))
    if not marks:
        return []

    cell = max(COLOCATED_TOL_PT, 1.0)
    index: Dict[Tuple[int, int], List[Point]] = defaultdict(list)
    for mx, my in marks:
        index[(int(mx // cell), int(my // cell))].append((mx, my))

    def _on_marker(x: float, y: float) -> bool:
        gx, gy = int(x // cell), int(y // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for mx, my in index.get((gx + dx, gy + dy), ()):
                    if math.hypot(mx - x, my - y) <= COLOCATED_TOL_PT:
                        return True
        return False

    shadowed: List[str] = []
    for grp in symbol_groups:
        boxes = list(getattr(grp, "instance_bboxes_pt", ()) or ())
        if not boxes:
            continue
        hits = sum(
            1
            for b in boxes
            if _on_marker((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)
        )
        if hits / float(len(boxes)) >= min_fraction:
            shadowed.append(getattr(grp, "candidate_id", ""))
    return [cid for cid in shadowed if cid]
