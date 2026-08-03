"""Open-polyline run chaining (SP-5 core) — ONE chainer, two selectors.

An *open run* is a single-stroke line that has to be measured end to end: a
gas main drawn as an annotated CAD linetype, a pipe rail drawn as two thin
parallel faces, a curb, a fence, a conduit. Nothing in the package could
measure one before this module: :mod:`bobbytailor.deterministic.walls`
requires TWO parallel faces at a 3"–16" offset before it will emit anything,
so a single-stroke run can never come out of it, and its 2 ft segment floor
(``walls.MIN_WALL_SEG_FT``) discards the 3 pt exploded dashes an annotated
linetype is made of before pairing is even attempted.

Two investigations reached this module independently — INV-04 (Bob's A3.0 gas
piping, drawn as a ``— GAS — GAS —`` linetype) and INV-06 (Crow's ramp and
stair rails, drawn as double lines on A-401 details). They proposed two
modules with two names. This is the ONE core they share (D-03); the two
selectors that sit on top of it — the annotated-linetype selector and the rail
selector — are plan 23-12. Nothing here knows what a run is *called*.

Design notes that are not obvious:

* **Length is stored in POINTS**, never in feet. ``OpenRun.length_lf`` does the
  conversion as pure arithmetic, so a run recomputes instantly when a scale is
  corrected — the RawGeometry points-until-scale-bound pattern the wall module
  already uses.
* **A bridged gap counts as length.** Walls exclude opening gaps from a wall's
  material length, because a doorway is not wall. The break in an annotated
  linetype is the opposite: the pipe runs straight through the gap, the gap
  exists only so the word can be drawn in it. A run's length is therefore its
  SPAN, gaps included.
* **Chaining is only ever offered inside a clip.** Unclipped chaining on Crow's
  overall floor plan swallowed a hatch field into a single 369-foot "run"
  (INV-06 risk 4, threat T-23-38). The per-viewport clip is the correctness
  strategy and the performance strategy at once.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from bobbytailor.deterministic.printed_scale import (
    _MASK_KINDS as _VIEWPORT_MASK_KINDS,
)
from bobbytailor.deterministic.room_fill import to_page_space
from bobbytailor.deterministic.walls import (
    MAX_SEGMENTS,
    MIN_THICKNESS_FT,
    _harvest_styled,
)

logger = logging.getLogger(__name__)

Point = Tuple[float, float]

# ── Tuning constants ──────────────────────────────────────────────────────────
# Every value below records the OBSERVED number it was read from and the
# physical reason for the margin around it. None of them was fitted to make a
# total match a golden quantity (D-07).

# Segments shorter than this take no part in a run. Observed: the exploded
# dashes of Bob's GAS linetype are ~3 pt, and the micro-strokes that draw the
# word "GAS" itself are < 2.5 pt (INV-04 §2, 39 strokes inside a 10 x 4 pt
# box). 3.0 pt sits between the two populations. This is DELIBERATELY not the
# wall floor: ``walls.MIN_WALL_SEG_FT`` = 2 ft is ~36 pt at 1/4" scale and
# would discard every dash the linetype is made of.
MIN_SEG_PT = 3.0

# Parallel grouping quantisation, degrees. Same value the wall module uses, and
# for the same reason: CAD emits axis-aligned and 45° linework to far better
# than a degree, so 1° separates directions without splitting one line.
ANGLE_QUANT_DEG = 1.0
_ANGLE_BINS = int(round(180.0 / ANGLE_QUANT_DEG))

# Two pieces are on the SAME line when their perpendicular offsets differ by no
# more than this. Observed: INV-04 §3 step S4 grouped Bob's dashes at 1.2 pt.
# The margin covers CAD's own coordinate rounding (~0.01 pt) and the half-width
# of a 0.48 pt pen, and stays far below the 1.4–4.5 pt offset of a rail's two
# faces, which must remain two lines until the pair collapse decides otherwise.
OFFSET_TOL_PT = 1.2

# Collinear pieces this far apart or closer are ONE run with a bridged gap.
# Observed: the GAS mark pitch is 33.7 pt and the mark is 10 pt wide, so the
# ink gap at a mark is ~24 pt; 48 pt is a 2x margin on that, and still under
# the 53 pt pitch of the Crow "K.O." tag row that must NOT chain (INV-04 §3).
GAP_TOL_PT = 48.0

# A chain may turn by at most this much at a joint. Observed: INV-06 §2 step 2
# isolated Crow's rails with a 20° window; the naive unconstrained greedy
# version merged 33 018 page-0 segments into 6 112 junk runs.
CONTINUITY_DEG = 20.0

# Two spans join into one chain when their endpoints are this close. Observed:
# INV-06 §2 step 2 (0.75 pt). CAD closes a polyline exactly; the tolerance
# exists for the float round-trip through the content stream, not for slop.
JOIN_TOL_PT = 0.75

# Parallel-pair collapse band, in REAL FEET. A rail is drawn as two lines and
# without this every rail reports at 2x. Observed: 1 1/2" O.D. pipe = 0.125 ft;
# 1 1/8" = 0.094 ft (INV-06 §1.1). The floor of 0.02 ft (~1/4") is below any
# drawn pipe and above coincident duplicate linework.
#
# The CEILING IS the wall module's minimum thickness, exclusively: a pair at or
# above 3" is a wall, a pair below it is a rail, and NO segment pair can be
# claimed by both. INV-06 proposed 1.00 ft, which overlaps the wall window
# [0.25, 1.333] ft — that overlap is the whole reason this is pinned to the
# wall constant by reference rather than by a copied literal.
PAIR_OFFSET_MIN_FT = 0.02
PAIR_OFFSET_MAX_FT = MIN_THICKNESS_FT  # exclusive; 0.25 ft = 3 in

# Paired faces must overlap at least this share of the shorter one. Observed:
# INV-06 §2 step 2 (70%), the same figure ``walls.MIN_PAIR_OVERLAP`` uses.
PAIR_MIN_OVERLAP = 0.70
# At most this many parallel neighbours are examined per span. The pairing scan
# is otherwise quadratic inside a dense hatch field; 8 is far more neighbours
# than any drawn rail has (it has exactly one).
PAIR_SCAN_MAX = 8

# Stub closure — THE ONE CALIBRATED PARAMETER. Terminal drops, risers and
# elbows carry no glyph and are short, so they are absorbed with ONE hop.
# Observed: INV-04 §4 measured 810.7 LF of bare span, 847.8 LF with one hop
# (-4.4% against the estimator's 886.77) and 897.6 LF with two (+1.2%) — but
# the second hop demonstrably starts absorbing leader arrowheads. The +/-5%
# band IS the contract. Never widen the hop count to chase the residual.
STUB_MAX_PT = 70.0
STUB_SNAP_PT = 4.0
STUB_HOPS = 1

# Minimum real length of a reported run, feet. Observed: INV-06 §2 step 5.
MIN_RUN_FT = 4.0

# A run whose own ink covers less than this share of its span is mostly bridged
# gap — a chain of coincidences rather than a measured line. It is FLAGGED, not
# dropped (a deleted measurement is indistinguishable from a genuine zero).
# Observed: Bob's GAS linetype measures ~0.70 (10 pt of glyph per 33.7 pt of
# pitch); a run bridging a 48 pt gap between two 3 pt dashes measures 0.12.
MIN_INK_FRACTION = 0.25

_EPS = 1e-9


@dataclass
class OpenRun:
    """One chained open run, measured in PDF points only.

    ``polyline_pt`` is the run's vertices in UNROTATED page points — the space
    ``page.get_drawings()`` reports and the space every clip in this module is
    expressed in. ``points_pt`` is the same vertices as a list; it is a
    PROPERTY rather than a second field so the two can never disagree (INV-04
    named it ``polyline_pt``, INV-06 named it ``points_pt``; this is one run,
    not two).

    ``mark_signature`` / ``mark_stats`` are filled in only when a run came from
    an annotated linetype, by the selector that recognised the mark. Nothing in
    this module reads a glyph.
    """

    polyline_pt: Tuple[Point, ...]
    length_pt: float
    ink_pt: float = 0.0
    candidate_id: str = ""
    scale_fpi: Optional[float] = None
    viewport_title: str = ""
    is_typical: bool = False
    paired: bool = False
    mark_signature: Optional[tuple] = None
    mark_stats: Optional[dict] = None
    needs_review: bool = False
    review_reason: str = ""
    segment_count: int = 0

    @property
    def points_pt(self) -> List[Point]:
        return [tuple(p) for p in self.polyline_pt]

    @property
    def bbox_pt(self) -> Tuple[float, float, float, float]:
        xs = [p[0] for p in self.polyline_pt]
        ys = [p[1] for p in self.polyline_pt]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def ink_fraction(self) -> float:
        if self.length_pt <= _EPS:
            return 0.0
        return min(1.0, self.ink_pt / self.length_pt)

    def length_lf(self, feet_per_point: float) -> float:
        """Real length in feet. Pure arithmetic — recompute-safe by design."""
        if not feet_per_point or feet_per_point <= 0:
            return 0.0
        return self.length_pt * feet_per_point

    def to_dict(self) -> dict:
        return {
            "polyline_pt": [list(p) for p in self.polyline_pt],
            "length_pt": self.length_pt,
            "ink_pt": self.ink_pt,
            "candidate_id": self.candidate_id,
            "scale_fpi": self.scale_fpi,
            "viewport_title": self.viewport_title,
            "is_typical": self.is_typical,
            "paired": self.paired,
            "mark_signature": (
                list(self.mark_signature)
                if self.mark_signature is not None
                else None
            ),
            "mark_stats": self.mark_stats,
            "needs_review": self.needs_review,
            "review_reason": self.review_reason,
            "segment_count": self.segment_count,
        }


# ── Internal span type ────────────────────────────────────────────────────────


@dataclass
class _Span:
    """A straight run piece: collinear ink merged across its bridged gaps."""

    p0: Point
    p1: Point
    length: float
    ink: float
    offset: float
    angle_bin: int
    paired: bool = False
    members: int = 1
    used: bool = False

    def direction(self) -> Point:
        dx, dy = self.p1[0] - self.p0[0], self.p1[1] - self.p0[1]
        h = math.hypot(dx, dy)
        if h < _EPS:
            return (1.0, 0.0)
        return (dx / h, dy / h)


# ── Geometry helpers ──────────────────────────────────────────────────────────


def _dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _polyline_len(pts: Sequence[Point]) -> float:
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _canonical_frame(x0, y0, x1, y1) -> Tuple[Point, Point, int]:
    """Direction, normal and angle bin of a segment, direction-agnostic.

    The angle is folded into ``[0, 180)`` before the frame is built, so a
    segment and the same segment drawn backwards yield the IDENTICAL frame and
    therefore the identical perpendicular offset. Without the fold, one
    reversed dash in a linetype lands at ``-offset`` and never groups with the
    line it belongs to.
    """
    theta = math.atan2(y1 - y0, x1 - x0) % math.pi
    u = (math.cos(theta), math.sin(theta))
    n = (-u[1], u[0])
    bin_i = int(round(math.degrees(theta) / ANGLE_QUANT_DEG)) % _ANGLE_BINS
    return u, n, bin_i


def _mid_in_clip(x0, y0, x1, y1, clip) -> bool:
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return clip[0] <= mx <= clip[2] and clip[1] <= my <= clip[3]


def _interval_union(intervals: Sequence[Tuple[float, float]]) -> float:
    """Total covered length of possibly-overlapping 1-D intervals."""
    if not intervals:
        return 0.0
    ordered = sorted(intervals)
    total = 0.0
    lo, hi = ordered[0]
    for a, b in ordered[1:]:
        if a > hi:
            total += hi - lo
            lo, hi = a, b
        else:
            hi = max(hi, b)
    total += hi - lo
    return total


# ── Step 1: collinear merge with a bridged gap ───────────────────────────────


def _merge_collinear(styled_segments) -> List[_Span]:
    """Bin by angle, group by perpendicular offset, merge across small gaps.

    This is INV-04 §3 steps S4–S5 and the model is the wall module's
    interval-union / gap-bridging loop. The merged span's endpoints are the
    REAL ink points that achieve the extreme projections — never a point
    reconstructed on the quantised bin line, which would distort a long span by
    up to half a degree of the bin width.
    """
    by_bin: Dict[int, List[tuple]] = {}
    for s in styled_segments:
        length = s[4] if len(s) > 4 else _dist((s[0], s[1]), (s[2], s[3]))
        if length < MIN_SEG_PT:
            continue
        u, n, bin_i = _canonical_frame(s[0], s[1], s[2], s[3])
        offset = s[0] * n[0] + s[1] * n[1]
        by_bin.setdefault(bin_i, []).append(
            ((s[0], s[1]), (s[2], s[3]), length, offset, u)
        )

    spans: List[_Span] = []
    for bin_i, members in by_bin.items():
        members.sort(key=lambda m: m[3])
        group: List[tuple] = []
        group_start = None
        for m in members:
            if group and m[3] - group_start > OFFSET_TOL_PT:
                spans.extend(_merge_one_group(group, bin_i))
                group = []
                group_start = None
            if not group:
                group_start = m[3]
            group.append(m)
        if group:
            spans.extend(_merge_one_group(group, bin_i))
    return spans


def _merge_one_group(group: List[tuple], bin_i: int) -> List[_Span]:
    """Merge one same-line group along its own longest member's direction."""
    anchor = max(group, key=lambda m: m[2])
    u = anchor[4]
    origin = anchor[0]

    projected = []
    for p0, p1, length, offset, _u in group:
        t0 = (p0[0] - origin[0]) * u[0] + (p0[1] - origin[1]) * u[1]
        t1 = (p1[0] - origin[0]) * u[0] + (p1[1] - origin[1]) * u[1]
        if t1 < t0:
            t0, t1 = t1, t0
            p0, p1 = p1, p0
        projected.append((t0, t1, p0, p1, offset))
    projected.sort(key=lambda r: r[0])

    out: List[_Span] = []
    cur = [projected[0]]
    reach = projected[0][1]
    for rec in projected[1:]:
        if rec[0] - reach <= GAP_TOL_PT:
            cur.append(rec)
            reach = max(reach, rec[1])
        else:
            out.append(_span_from(cur, bin_i))
            cur = [rec]
            reach = rec[1]
    out.append(_span_from(cur, bin_i))
    return out


def _span_from(recs: List[tuple], bin_i: int) -> _Span:
    lo = min(recs, key=lambda r: r[0])
    hi = max(recs, key=lambda r: r[1])
    p0, p1 = lo[2], hi[3]
    length = _dist(p0, p1)
    ink = _interval_union([(r[0], r[1]) for r in recs])
    offset = sum(r[4] for r in recs) / len(recs)
    return _Span(
        p0=p0,
        p1=p1,
        length=length,
        ink=min(ink, length),
        offset=offset,
        angle_bin=bin_i,
        members=len(recs),
    )


# ── Step 2: parallel-pair collapse ───────────────────────────────────────────


def _collapse_pairs(spans: List[_Span], feet_per_point: float) -> List[_Span]:
    """Collapse a rail's two drawn faces into one run of the MEAN length.

    Pairing is restricted to a single 1° angle bin. INV-06 proposed a ±5°
    window; the shipped band is tighter on purpose. CAD draws a rail's two
    faces exactly parallel, so 1° is ample, and a band that is too tight can
    only UNDER-collapse — which reports a rail at 2x, visibly wrong — whereas a
    band that is too wide silently HALVES an unrelated pair of lines.
    """
    lo_pt = PAIR_OFFSET_MIN_FT / feet_per_point
    hi_pt = PAIR_OFFSET_MAX_FT / feet_per_point

    by_bin: Dict[int, List[_Span]] = {}
    for sp in spans:
        by_bin.setdefault(sp.angle_bin, []).append(sp)

    out: List[_Span] = []
    for members in by_bin.values():
        members.sort(key=lambda s: (s.offset, s.p0, s.p1))
        consumed = [False] * len(members)
        for i, a in enumerate(members):
            if consumed[i]:
                continue
            partner = -1
            for j in range(i + 1, min(i + 1 + PAIR_SCAN_MAX, len(members))):
                if consumed[j]:
                    continue
                b = members[j]
                gap = abs(b.offset - a.offset)
                if gap >= hi_pt:
                    break
                if gap < lo_pt:
                    continue
                if _overlap_fraction(a, b) < PAIR_MIN_OVERLAP:
                    continue
                partner = j
                break
            if partner < 0:
                out.append(a)
                continue
            consumed[i] = consumed[partner] = True
            out.append(_mean_span(a, members[partner]))
    return out


def _overlap_fraction(a: _Span, b: _Span) -> float:
    u = a.direction()
    o = a.p0
    ta0 = 0.0
    ta1 = a.length
    tb0 = (b.p0[0] - o[0]) * u[0] + (b.p0[1] - o[1]) * u[1]
    tb1 = (b.p1[0] - o[0]) * u[0] + (b.p1[1] - o[1]) * u[1]
    if tb1 < tb0:
        tb0, tb1 = tb1, tb0
    overlap = min(ta1, tb1) - max(ta0, tb0)
    shorter = min(a.length, b.length)
    if shorter <= _EPS:
        return 0.0
    return max(0.0, overlap) / shorter


def _mean_span(a: _Span, b: _Span) -> _Span:
    """The midline of two parallel faces, with exactly the mean length."""
    u = a.direction()
    n = (-u[1], u[0])
    o = a.p0
    ta0, ta1 = 0.0, a.length
    tb0 = (b.p0[0] - o[0]) * u[0] + (b.p0[1] - o[1]) * u[1]
    tb1 = (b.p1[0] - o[0]) * u[0] + (b.p1[1] - o[1]) * u[1]
    ob = (b.p0[0] - o[0]) * n[0] + (b.p0[1] - o[1]) * n[1]
    if tb1 < tb0:
        tb0, tb1 = tb1, tb0
    t0 = (ta0 + tb0) / 2.0
    t1 = (ta1 + tb1) / 2.0
    off = ob / 2.0

    def _pt(t: float) -> Point:
        return (o[0] + u[0] * t + n[0] * off, o[1] + u[1] * t + n[1] * off)

    p0, p1 = _pt(t0), _pt(t1)
    length = t1 - t0
    return _Span(
        p0=p0,
        p1=p1,
        length=length,
        ink=min(length, (a.ink + b.ink) / 2.0),
        offset=(a.offset + b.offset) / 2.0,
        angle_bin=a.angle_bin,
        paired=True,
        members=a.members + b.members,
    )


# ── Step 3: direction-continuity chaining over a bounded hash grid ───────────


class _EndpointGrid:
    """Bucketed endpoint lookup — the bounded-work half of T-23-37."""

    def __init__(self, cell: float) -> None:
        self.cell = max(cell, 0.5)
        self.buckets: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}

    def add(self, pt: Point, span_index: int, end: int) -> None:
        key = (
            int(math.floor(pt[0] / self.cell)),
            int(math.floor(pt[1] / self.cell)),
        )
        self.buckets.setdefault(key, []).append((span_index, end))

    def near(self, pt: Point) -> List[Tuple[int, int]]:
        cx = int(math.floor(pt[0] / self.cell))
        cy = int(math.floor(pt[1] / self.cell))
        hits: List[Tuple[int, int]] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                hits.extend(self.buckets.get((cx + dx, cy + dy), ()))
        return hits


def _chain(spans: List[_Span]) -> List[dict]:
    """Walk spans end to end, turning by at most ``CONTINUITY_DEG`` a joint."""
    grid = _EndpointGrid(max(JOIN_TOL_PT, STUB_SNAP_PT))
    for i, sp in enumerate(spans):
        grid.add(sp.p0, i, 0)
        grid.add(sp.p1, i, 1)

    order = sorted(range(len(spans)), key=lambda i: (-spans[i].length, i))
    max_dev = math.cos(math.radians(CONTINUITY_DEG))
    chains: List[dict] = []

    for start in order:
        if spans[start].used:
            continue
        spans[start].used = True
        pts = [spans[start].p0, spans[start].p1]
        ink = spans[start].ink
        paired = spans[start].paired
        count = 1

        for forward in (True, False):
            if forward:
                tail, head = pts[-2], pts[-1]
            else:
                tail, head = pts[1], pts[0]
            while True:
                hdx, hdy = head[0] - tail[0], head[1] - tail[1]
                hh = math.hypot(hdx, hdy)
                if hh < _EPS:
                    break
                h = (hdx / hh, hdy / hh)
                best = -1
                best_end = 0
                best_dot = max_dev
                for idx, end in grid.near(head):
                    if spans[idx].used:
                        continue
                    cand = spans[idx]
                    q = cand.p0 if end == 0 else cand.p1
                    if _dist(q, head) > JOIN_TOL_PT:
                        continue
                    other = cand.p1 if end == 0 else cand.p0
                    dx, dy = other[0] - q[0], other[1] - q[1]
                    dh = math.hypot(dx, dy)
                    if dh < _EPS:
                        continue
                    dot = (dx / dh) * h[0] + (dy / dh) * h[1]
                    if dot > best_dot or (
                        best >= 0 and dot == best_dot and idx < best
                    ):
                        best, best_end, best_dot = idx, end, dot
                if best < 0:
                    break
                cand = spans[best]
                cand.used = True
                other = cand.p1 if best_end == 0 else cand.p0
                if forward:
                    pts.append(other)
                else:
                    pts.insert(0, other)
                ink += cand.ink
                paired = paired or cand.paired
                count += 1
                tail, head = head, other

        chains.append(
            {"pts": pts, "ink": ink, "paired": paired, "count": count}
        )
    return chains


# ── Step 4: bounded single-hop stub closure ──────────────────────────────────


def _absorb_stubs(chains: List[dict]) -> List[dict]:
    """Absorb terminal drops, risers and elbows — ONE hop, never two.

    A stub is a SHORT chain with a free end near a longer chain's end. Unlike
    :func:`_chain` this hop carries no continuity constraint (a riser leaves a
    gas main at a right angle) and a looser snap tolerance, which is exactly
    why it is limited to one hop: the second hop demonstrably starts absorbing
    leader arrowheads (INV-04 §4).

    The host endpoint grid is built ONCE, before any absorption, so a stub's
    newly-attached far end can never serve as the anchor for a second stub.
    That is the one-hop guarantee, enforced structurally rather than by a
    counter.
    """
    if not chains or STUB_HOPS < 1:
        return chains
    lengths = [_polyline_len(c["pts"]) for c in chains]
    is_stub = [MIN_SEG_PT <= ln <= STUB_MAX_PT for ln in lengths]
    order = sorted(range(len(chains)), key=lambda i: (-lengths[i], i))
    hosts = [i for i in order if not is_stub[i]]
    if not hosts:
        return chains

    grid = _EndpointGrid(max(STUB_SNAP_PT, 1.0))
    for i in hosts:
        grid.add(chains[i]["pts"][0], i, 0)
        grid.add(chains[i]["pts"][-1], i, 1)

    consumed = set()
    for i in order:
        if not is_stub[i]:
            continue
        stub = chains[i]
        for which in (0, -1):
            q = stub["pts"][which]
            best = None
            for hidx, end in sorted(grid.near(q)):
                if hidx in consumed:
                    continue
                hp = chains[hidx]["pts"][0 if end == 0 else -1]
                d = _dist(hp, q)
                if d <= STUB_SNAP_PT and (best is None or d < best[0]):
                    best = (d, hidx, end)
            if best is None:
                continue
            _d, hidx, end = best
            tail = (
                stub["pts"][1:] if which == 0
                else list(reversed(stub["pts"][:-1]))
            )
            if not tail:
                continue
            if end == 0:
                chains[hidx]["pts"][0:0] = list(reversed(tail))
            else:
                chains[hidx]["pts"].extend(tail)
            chains[hidx]["ink"] += stub["ink"]
            chains[hidx]["count"] += stub["count"]
            consumed.add(i)
            break

    return [c for i, c in enumerate(chains) if i not in consumed]


# ── Clamp ────────────────────────────────────────────────────────────────────


def clamp_run(run: OpenRun, from_pt: float, to_pt: float) -> OpenRun:
    """Trim a run to an ARC-LENGTH window measured along its own polyline.

    This is the clamp INV-04 §3 step S7 needs (``[first_mark - pitch,
    last_mark + pitch]``) and the one a rail selector needs when a detail's own
    printed extent is known. It is exposed rather than inlined because both
    selectors clamp and neither should re-derive polyline arithmetic.

    A window that does not intersect the run returns a zero-length run at the
    nearest vertex; the caller decides whether that is a measurement or a miss.
    """
    pts = run.points_pt
    if len(pts) < 2 or run.length_pt <= _EPS:
        return run
    lo = max(0.0, min(from_pt, to_pt))
    hi = min(run.length_pt, max(from_pt, to_pt))
    if hi <= lo:
        return _replace_polyline(run, (pts[0], pts[0]), 0.0)

    out: List[Point] = []
    walked = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = _dist(a, b)
        if seg <= _EPS:
            continue
        s, e = walked, walked + seg
        walked = e
        if e < lo or s > hi:
            continue
        t0 = max(0.0, (lo - s) / seg)
        t1 = min(1.0, (hi - s) / seg)
        pa = (a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0)
        pb = (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)
        if not out:
            out.append(pa)
        out.append(pb)
    if len(out) < 2:
        return _replace_polyline(run, (pts[0], pts[0]), 0.0)
    length = _polyline_len(out)
    scale = length / run.length_pt if run.length_pt > _EPS else 0.0
    return _replace_polyline(run, tuple(out), length, ink=run.ink_pt * scale)


def _replace_polyline(
    run: OpenRun,
    pts: Tuple[Point, ...],
    length: float,
    ink: Optional[float] = None,
) -> OpenRun:
    return OpenRun(
        polyline_pt=pts,
        length_pt=length,
        ink_pt=run.ink_pt if ink is None else ink,
        candidate_id=run.candidate_id,
        scale_fpi=run.scale_fpi,
        viewport_title=run.viewport_title,
        is_typical=run.is_typical,
        paired=run.paired,
        mark_signature=run.mark_signature,
        mark_stats=run.mark_stats,
        needs_review=run.needs_review,
        review_reason=run.review_reason,
        segment_count=run.segment_count,
    )


# ── Public API ────────────────────────────────────────────────────────────────


def _chain_group(segments, feet_per_point: float, min_run_ft: float) -> List[OpenRun]:
    """The core pipeline for one segment population: merge collinear pieces
    across bridged gaps, collapse parallel pairs, chain with the continuity
    window, absorb stubs with one hop, build the surviving runs."""
    spans = _merge_collinear(segments)
    if not spans:
        return []
    spans = _collapse_pairs(spans, feet_per_point)
    chains = _absorb_stubs(_chain(spans))

    runs: List[OpenRun] = []
    min_len_pt = min_run_ft / feet_per_point
    for chain in chains:
        pts = tuple(chain["pts"])
        length = _polyline_len(pts)
        if length < min_len_pt:
            continue
        run = OpenRun(
            polyline_pt=pts,
            length_pt=length,
            ink_pt=min(chain["ink"], length),
            paired=chain["paired"],
            segment_count=chain["count"],
        )
        if run.ink_fraction < MIN_INK_FRACTION:
            run.needs_review = True
            run.review_reason = (
                "run is %.0f%% bridged gap — its ink covers only %.2f of "
                "its span" % (
                    100.0 * (1.0 - run.ink_fraction), run.ink_fraction
                )
            )
        runs.append(run)
    return runs


def extract_open_runs(
    page,
    doc,
    clip_pt: Sequence[float],
    feet_per_point: float,
    min_run_ft: float = MIN_RUN_FT,
    exclude_rects: Optional[Sequence] = None,
    candidate_prefix: str = "RUN",
    per_pen: bool = False,
) -> List[OpenRun]:
    """Chain the open runs drawn inside ``clip_pt``. Never raises.

    ``clip_pt`` is REQUIRED and is an ``(x0, y0, x1, y1)`` rect in unrotated
    page points. There is deliberately no unclipped entry point: unclipped
    chaining on Crow's overall floor plan swallowed a hatch field into a single
    369-foot "run" (INV-06 risk 4 / T-23-38), and the per-viewport clip is also
    what keeps the work bounded on a 33 000-segment page.

    ``feet_per_point`` parameterises the two real-length constants — the
    minimum reported run length and the parallel-pair offset band. It does NOT
    convert the result: every ``OpenRun.length_pt`` comes back in points.

    ``per_pen=True`` runs the identical pipeline once per (stroke width,
    stroke colour) pen instead of once over everything. CAD draws one object
    with one pen, so merging, pairing and chaining across pens conflates
    DIFFERENT objects: on Crow's stair details, the rail face (a 0.96 pt pen)
    was being merged with the lighter stringer line that continues past the
    rail's end (a 0.36 pt pen), over-chaining the run 72 pt beyond where the
    estimator's own mark stops. The pen partition terminates the chain where
    the drawn object ends — a position-truth fix, not a count fit. This is
    exactly what the styled harvest carries width and colour FOR (23-10).
    """
    if not feet_per_point or feet_per_point <= 0:
        logger.warning("Open-run chaining requires a solved scale; skipping")
        return []
    if not clip_pt or len(tuple(clip_pt)) != 4:
        logger.warning("Open-run chaining requires a clip rect; skipping")
        return []
    clip = tuple(float(c) for c in clip_pt)
    clip = (
        min(clip[0], clip[2]),
        min(clip[1], clip[3]),
        max(clip[0], clip[2]),
        max(clip[1], clip[3]),
    )

    try:
        styled, _curves, _s_len, _c_len = _harvest_styled(
            page, doc, exclude_rects, max_segments=MAX_SEGMENTS
        )
        inside = [
            s for s in styled
            if _mid_in_clip(s[0], s[1], s[2], s[3], clip)
        ]
        if not inside:
            return []

        if per_pen:
            pens: Dict[tuple, list] = {}
            for s in inside:
                pens.setdefault((s[5], s[6]), []).append(s)
            runs: List[OpenRun] = []
            for _pen in sorted(pens, key=lambda k: (k[0], str(k[1]))):
                runs.extend(
                    _chain_group(pens[_pen], feet_per_point, min_run_ft)
                )
        else:
            runs = _chain_group(inside, feet_per_point, min_run_ft)

        runs.sort(key=lambda r: (-r.length_pt, r.polyline_pt))
        for rank, run in enumerate(runs, start=1):
            run.candidate_id = "%s-%d" % (candidate_prefix, rank)
        return runs
    except Exception as exc:  # noqa: BLE001 — untrusted PDF must not crash
        logger.warning("Open-run chaining failed: %s", exc)
        return []


def run_lf(runs: Sequence[OpenRun], feet_per_point: float) -> float:
    """Total real length of ``runs`` — pure conversion, recompute-safe."""
    if not feet_per_point or feet_per_point <= 0:
        return 0.0
    return round(sum(r.length_pt for r in runs) * feet_per_point, 2)


# ═════════════════════════════════════════════════════════════════════════════
# SELECTOR 1 — annotated CAD linetypes (INV-04, gap 4)
#
# Bob's gas main is drawn on the A3.0 roof plan with the SAME width, colour,
# dash array (none — the dashing is exploded) and layer (none) as 1,695 other
# paths. What separates it is the LINETYPE: the line is BROKEN at a regular
# pitch and each gap holds the word "GAS" rendered as 39 vector micro-strokes
# the text layer cannot see. The selector below detects that repeating,
# line-breaking glyph mark — and NOTHING else about the line.
#
# The glyph is a GROUPING key, never a name. Template-matching the mark against
# sheet text was tried and FAILED (the truth ranked 10th of 12 candidates,
# INV-04 §5), and no OCR exists on this machine. Naming is plan 23-15.
# ═════════════════════════════════════════════════════════════════════════════

# ── Selector constants — every value records the observation it came from ────

# A micro-stroke takes part in a glyph, never in a line. Observed: the strokes
# drawing the word "GAS" are < 2.5 pt; the exploded dashes of the line itself
# are ~3 pt (INV-04 §2/§3 S2). 2.5 sits between the two populations, and the
# dash floor is the chainer's own MIN_SEG_PT = 3.0, leaving a deliberate
# no-man's band so one stroke can never be both.
MICRO_MAX_PT = 2.5

# Micro-strokes whose endpoints sit closer than this are the SAME glyph.
# Observed: INV-04 §3 S2 (2.0 pt). SHX vector text draws a letter as connected
# pen strokes; 2.0 pt bridges the pen lifts inside one letter without bridging
# the ~2 pt gap to the neighbouring letter's strokes being too generous —
# measured, the GAS word unions into ONE 39-stroke blob per mark.
MICRO_JOIN_PT = 2.0

# A blob is a candidate glyph mark when its stroke count and bbox span sit in
# the observed band. Observed: GAS = 39 strokes in a 10 x 4 pt box (INV-04 §2);
# the band 18..120 and the 24 pt span cap admit other stock annotated linetypes
# (W, SS, ST, OHE, G) without admitting keynote bubbles or dimension text.
GLYPH_STROKES_MIN = 18
GLYPH_STROKES_MAX = 120
GLYPH_MAX_SPAN_PT = 24.0

# A mark belongs to a line when it sits within this perpendicular distance of
# it. Observed: INV-04 §3 S6 (9 pt) — the glyph straddles the break, so its
# centre is ON the line to within half the glyph's own minor span.
PERP_TOL_PT = 9.0

# Marks are collected inside the merged span extended by this much at each
# end — the first/last glyph of a run sits one break beyond the last dash.
# Same value as the merge's own gap tolerance, and for the same physical
# reason: it is the largest ink gap the linetype produces (INV-04 §3 S6).
SPAN_PAD_PT = GAP_TOL_PT

# ── The four gates (INV-04 §3 S6 a-d). Do not loosen any of them. ────────────

# (a) A linetype repeats; three identical marks is the observed minimum that
# cannot be produced by a label pair.
MIN_MARKS = 3

# (b) The pitch floor and THE DECISIVE RATIO GATE. A linetype's mark pitch is
# a small multiple of its own glyph span — the mark IS the line's texture. A
# row of tags SITTING ON a line repeats at the spacing of the tagged objects,
# far wider than the tag. Observed: the real GAS run's pitch/span ratio is
# 3.4 (33.7 pt pitch / 10 pt glyph); the Crow "K.O." dock-panel tag row that a
# naive detector reported as piping is 26.5 (53 pt pitch / 2 pt glyph); the
# Chelsea three-mark candidates range 8.3-27.0. Six is the widest ratio at
# which no observed false positive survives (INV-04 §3 iteration table).
MIN_PITCH_PT = 15.0
MAX_PITCH_OVER_SPAN = 6.0

# (c) A linetype's pitch is machine-regular; a label row follows the objects
# it labels. Observed: the GAS pitch CV is ~0.02; rejected candidates measure
# 0.26-0.92 (INV-04 §3 S6c).
PITCH_CV_MAX = 0.35

# (d) The line must actually BREAK at the mark: no dash ink under the glyph
# (within half its span plus a 1 pt pen margin) and dash ink present on BOTH
# sides within 0.6 x pitch. A tag row drawn ON TOP of an unbroken line fails
# this even when its pitch is regular. Observed: GAS break_frac = 1.00;
# candidate rows on Bob's own RCP measure 0.00 (INV-04 §3 S6d).
BREAK_FRAC_MIN = 0.80
BREAK_SIDE_FRAC = 0.6
BREAK_CLEAR_PAD_PT = 1.0

# Ink belongs to a span's own line only when it runs ALONG it. cos(10°): CAD
# draws the exploded dashes of one line to far better than a degree; anything
# beyond 10° is crossing linework and must not fill a break.
ALONG_DIR_MIN = 0.985

# ── Dedupe (S8) ──────────────────────────────────────────────────────────────
# Near-identical parallel runs of the SAME signature are one line drawn twice
# (a CAD export artefact), never two pipes 1.5 pt apart. Observed: INV-04 §3
# S8 (1.5 pt offset, 90% overlap).
DEDUP_OFFSET_PT = 1.5
DEDUP_OVERLAP = 0.90


def _linetype_gates_pass(
    mark_count: int,
    mean_pitch_pt: float,
    pitch_cv: float,
    glyph_span_pt: float,
    break_frac: float,
) -> bool:
    """The four S6 gates, in one testable place.

    The rejection fixtures pin this function against the real coincidences the
    development history caught: the Crow "K.O." dock-panel tag row (34 marks of
    signature (54, 2, 2) at pitch 53 — ratio 26.5, and the grade line really
    IS broken at every tag) and the five Chelsea three-mark candidates
    (pitches 108-237, ratios 8.3-27.0). Loosening any gate here must fail
    those fixtures before it can ship.
    """
    if mark_count < MIN_MARKS:
        return False
    if mean_pitch_pt < MIN_PITCH_PT:
        return False
    if glyph_span_pt <= 0:
        return False
    if mean_pitch_pt > MAX_PITCH_OVER_SPAN * glyph_span_pt:
        return False
    if pitch_cv > PITCH_CV_MAX:
        return False
    if break_frac < BREAK_FRAC_MIN:
        return False
    return True


class _DSU:
    """Union-find over micro-stroke indices — the T-23-46 bounded-work half
    is the spatial hash in :func:`_glyph_mark_blobs`, which only ever unions
    endpoints inside a fixed 3x3-cell neighbourhood."""

    __slots__ = ("parent",)

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, a: int) -> int:
        parent = self.parent
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _glyph_mark_blobs(micro_items: Sequence) -> List[dict]:
    """S2-S3: union micro-strokes into blobs; keep the glyph-shaped ones.

    Returns ``[{"signature": (strokes, major, minor), "center": (x, y)}]``.
    The signature is the GROUPING key INV-04 §3 S3 defines — stroke count with
    the rounded major and minor bbox spans. It is never read as text.
    """
    n = len(micro_items)
    if n == 0:
        return []
    dsu = _DSU(n)
    grid: Dict[Tuple[int, int], List[Tuple[int, float, float]]] = {}
    for i, s in enumerate(micro_items):
        for x, y in ((s[0], s[1]), (s[2], s[3])):
            key = (int(x // MICRO_JOIN_PT), int(y // MICRO_JOIN_PT))
            grid.setdefault(key, []).append((i, x, y))
    join_sq = MICRO_JOIN_PT * MICRO_JOIN_PT
    for (cx, cy), pts in grid.items():
        neigh: List[Tuple[int, float, float]] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neigh.extend(grid.get((cx + dx, cy + dy), ()))
        for i, x, y in pts:
            for j, x2, y2 in neigh:
                if j <= i:
                    continue
                if (x - x2) ** 2 + (y - y2) ** 2 <= join_sq:
                    dsu.union(i, j)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(dsu.find(i), []).append(i)

    marks: List[dict] = []
    for idxs in groups.values():
        count = len(idxs)
        if not (GLYPH_STROKES_MIN <= count <= GLYPH_STROKES_MAX):
            continue
        xs: List[float] = []
        ys: List[float] = []
        for i in idxs:
            s = micro_items[i]
            xs.extend((s[0], s[2]))
            ys.extend((s[1], s[3]))
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if max(w, h) > GLYPH_MAX_SPAN_PT:
            continue
        marks.append(
            {
                "signature": (count, round(max(w, h)), round(min(w, h))),
                "center": (
                    (min(xs) + max(xs)) / 2.0,
                    (min(ys) + max(ys)) / 2.0,
                ),
            }
        )
    return marks


def _span_ink_intervals(span: _Span, dash_items: Sequence) -> List[Tuple[float, float]]:
    """Projected ink intervals of the dash pieces on *span*'s own line.

    Only pieces within the merge's own offset tolerance of the span line AND
    running along it count as its ink — crossing linework must not fill a
    break (S6d).
    """
    u = span.direction()
    nvec = (-u[1], u[0])
    ox, oy = span.p0
    out: List[Tuple[float, float]] = []
    for s in dash_items:
        mx, my = (s[0] + s[2]) / 2.0, (s[1] + s[3]) / 2.0
        if abs((mx - ox) * nvec[0] + (my - oy) * nvec[1]) > OFFSET_TOL_PT:
            continue
        length = s[4] if len(s) > 4 else _dist((s[0], s[1]), (s[2], s[3]))
        if length <= _EPS:
            continue
        along = abs((s[2] - s[0]) * u[0] + (s[3] - s[1]) * u[1])
        if along / length < ALONG_DIR_MIN:
            continue
        t0 = (s[0] - ox) * u[0] + (s[1] - oy) * u[1]
        t1 = (s[2] - ox) * u[0] + (s[3] - oy) * u[1]
        if t1 < t0:
            t0, t1 = t1, t0
        out.append((t0, t1))
    out.sort()
    return out


def _has_ink(intervals: Sequence[Tuple[float, float]], lo: float, hi: float) -> bool:
    for a, b in intervals:
        if b < lo:
            continue
        return a <= hi
    return False


def extract_linetype_runs(
    page,
    doc,
    clip_pt: Sequence[float],
    exclude_rects: Optional[Sequence] = None,
) -> List[OpenRun]:
    """Detect annotated-linetype runs inside ``clip_pt``. Never raises.

    INV-04 §3 steps S1-S9 on the shared chainer core: the styled harvest is
    S1, :func:`_merge_collinear` is S4-S5, :func:`clamp_run` is S7 and
    :func:`_absorb_stubs` is S9. Only the glyph blobs (S2-S3), the four gates
    (S6) and the parallel dedupe (S8) are selector-specific.

    Lengths come back in POINTS. Scale binding is :func:`run_scale_fpp` — a
    run is measured at the scale of the drawing that contains it or not at
    all, never at a borrowed page scale.
    """
    if not clip_pt or len(tuple(clip_pt)) != 4:
        logger.warning("Linetype detection requires a clip rect; skipping")
        return []
    clip = tuple(float(c) for c in clip_pt)
    clip = (
        min(clip[0], clip[2]),
        min(clip[1], clip[3]),
        max(clip[0], clip[2]),
        max(clip[1], clip[3]),
    )

    try:
        styled, _curves, _s_len, _c_len = _harvest_styled(
            page, doc, exclude_rects, max_segments=MAX_SEGMENTS
        )
        inside = [
            s for s in styled if _mid_in_clip(s[0], s[1], s[2], s[3], clip)
        ]
        if not inside:
            return []

        # S1-S3 — micro-strokes to signed glyph marks.
        micro = [s for s in inside if s[4] < MICRO_MAX_PT]
        marks = _glyph_mark_blobs(micro)
        if not marks:
            return []
        sig_census: Dict[tuple, int] = {}
        for m in marks:
            sig_census[m["signature"]] = sig_census.get(m["signature"], 0) + 1
        live = {sig for sig, cnt in sig_census.items() if cnt >= MIN_MARKS}
        marks = [m for m in marks if m["signature"] in live]
        if not marks:
            return []

        # S4-S5 — the chainer core's own collinear merge.
        dashes = [s for s in inside if s[4] >= MIN_SEG_PT]
        spans = _merge_collinear(dashes)

        # S6 — the four gates, per (span, signature).
        accepted: List[dict] = []
        for span in spans:
            if span.length < 2 * MIN_PITCH_PT:
                continue
            u = span.direction()
            nvec = (-u[1], u[0])
            ox, oy = span.p0
            by_sig: Dict[tuple, List[Tuple[float, dict]]] = {}
            for m in marks:
                dx, dy = m["center"][0] - ox, m["center"][1] - oy
                if abs(dx * nvec[0] + dy * nvec[1]) > PERP_TOL_PT:
                    continue
                t = dx * u[0] + dy * u[1]
                if t < -SPAN_PAD_PT or t > span.length + SPAN_PAD_PT:
                    continue
                by_sig.setdefault(m["signature"], []).append((t, m))

            ink: Optional[List[Tuple[float, float]]] = None
            for sig, t_marks in by_sig.items():
                if len(t_marks) < MIN_MARKS:
                    continue
                t_marks.sort(key=lambda r: r[0])
                ts = [t for t, _m in t_marks]
                pitches = [b - a for a, b in zip(ts, ts[1:])]
                mean_pitch = sum(pitches) / len(pitches)
                if mean_pitch <= _EPS:
                    continue
                var = sum((p - mean_pitch) ** 2 for p in pitches) / len(pitches)
                pitch_cv = math.sqrt(var) / mean_pitch
                glyph_span = float(sig[1])

                # S6d needs the span's own ink layout; computed lazily, once.
                if ink is None:
                    ink = _span_ink_intervals(span, dashes)
                half = glyph_span / 2.0 + BREAK_CLEAR_PAD_PT
                side = BREAK_SIDE_FRAC * mean_pitch
                broken = 0
                for t in ts:
                    under = _has_ink(ink, t - half, t + half)
                    left = _has_ink(ink, t - side, t - half)
                    right = _has_ink(ink, t + half, t + side)
                    if (not under) and left and right:
                        broken += 1
                break_frac = broken / float(len(ts))

                if not _linetype_gates_pass(
                    len(ts), mean_pitch, pitch_cv, glyph_span, break_frac
                ):
                    continue
                accepted.append(
                    {
                        "span": span,
                        "signature": sig,
                        "ts": ts,
                        "centers": [m["center"] for _t, m in t_marks],
                        "pitch": mean_pitch,
                        "cv": pitch_cv,
                        "break_frac": break_frac,
                    }
                )

        if not accepted:
            return []

        # S7 — clamp to the marks plus one pitch, inside the merged span.
        candidates: List[Tuple[dict, OpenRun]] = []
        for rec in accepted:
            span = rec["span"]
            base = OpenRun(
                polyline_pt=(span.p0, span.p1),
                length_pt=span.length,
                ink_pt=span.ink,
            )
            lo = max(0.0, rec["ts"][0] - rec["pitch"])
            hi = min(span.length, rec["ts"][-1] + rec["pitch"])
            run = clamp_run(base, lo, hi)
            if run.length_pt <= _EPS:
                continue
            run.mark_signature = rec["signature"]
            run.mark_stats = {
                "mark_count": len(rec["ts"]),
                "pitch_pt": round(rec["pitch"], 2),
                "pitch_cv": round(rec["cv"], 4),
                "break_frac": round(rec["break_frac"], 4),
                "glyph_span_pt": float(rec["signature"][1]),
                "mark_centers": [
                    (round(x, 1), round(y, 1)) for x, y in rec["centers"]
                ],
            }
            candidates.append((rec, run))

        # S8 — dedupe near-identical parallel runs of the same signature.
        candidates.sort(key=lambda cr: (-cr[1].length_pt, cr[1].polyline_pt))
        kept: List[Tuple[dict, OpenRun]] = []
        for rec, run in candidates:
            span = rec["span"]
            duplicate = False
            for krec, krun in kept:
                if krec["signature"] != rec["signature"]:
                    continue
                if krec["span"].angle_bin != span.angle_bin:
                    continue
                if abs(krec["span"].offset - span.offset) >= DEDUP_OFFSET_PT:
                    continue
                u = krec["span"].direction()
                ox, oy = krun.polyline_pt[0]
                a0, a1 = 0.0, krun.length_pt
                b0 = (run.polyline_pt[0][0] - ox) * u[0] + (
                    run.polyline_pt[0][1] - oy
                ) * u[1]
                b1 = (run.polyline_pt[-1][0] - ox) * u[0] + (
                    run.polyline_pt[-1][1] - oy
                ) * u[1]
                if b1 < b0:
                    b0, b1 = b1, b0
                overlap = min(a1, b1) - max(a0, b0)
                shorter = min(a1 - a0, b1 - b0)
                if shorter > _EPS and overlap / shorter > DEDUP_OVERLAP:
                    duplicate = True
                    break
            if not duplicate:
                kept.append((rec, run))

        # S9 — ONE-hop stub closure through the core's own absorber. Stub
        # candidates are the leftover merged spans in the chainer's own stub
        # band; the runs are the hosts. The absorber's endpoint grid is built
        # once, so a stub's far end can never anchor a second hop — hop two
        # demonstrably starts absorbing leader arrowheads (INV-04 §4), which
        # is why the residual against the estimator is ACCEPTED, not chased.
        used_spans = {id(rec["span"]) for rec, _run in kept}
        chains: List[dict] = []
        for rec, run in kept:
            chains.append(
                {
                    "pts": list(run.polyline_pt),
                    "ink": run.ink_pt,
                    "paired": False,
                    "count": 1,
                    "_run": run,
                }
            )
        for span in spans:
            if id(span) in used_spans:
                continue
            if MIN_SEG_PT <= span.length <= STUB_MAX_PT:
                chains.append(
                    {
                        "pts": [span.p0, span.p1],
                        "ink": span.ink,
                        "paired": False,
                        "count": 1,
                    }
                )
        merged = _absorb_stubs(chains)

        runs: List[OpenRun] = []
        for chain in merged:
            run = chain.get("_run")
            if run is None:
                continue
            pts = tuple(chain["pts"])
            length = _polyline_len(pts)
            runs.append(
                _replace_polyline(
                    run, pts, length, ink=min(chain["ink"], length)
                )
            )

        runs.sort(key=lambda r: (-r.length_pt, r.polyline_pt))
        for rank, run in enumerate(runs, start=1):
            run.candidate_id = "RUN-%d" % rank
        return runs
    except Exception as exc:  # noqa: BLE001 — untrusted PDF must not crash
        logger.warning("Linetype run detection failed: %s", exc)
        return []


# ═════════════════════════════════════════════════════════════════════════════
# SELECTOR 2 — rails (INV-06, gap 6)
#
# A rail is drawn as one or two thin parallel faces inside a DETAIL drawing at
# the detail's own printed scale. The selector is the chainer core run per pen
# inside a callout-anchored clip; what it adds is the stamping — the owning
# viewport's title, the callout's scale, and the typical-detail flag that is
# the entire defence against summing the same rail drawn on a typical detail
# with the same rail drawn on a main plan (INV-06 risk 3).
#
# THE STANDING CAUTION: measuring a run is not counting the runs. Crow's
# golden rail totals are ~6x and ~21x the drawn per-instance lengths, because
# the instance multiplier is not printed anywhere on the sheets. A rail run is
# emitted PER INSTANCE; the binder (23-13) must ship it flagged with the count
# unknown. Tuning anything here until a total reads 420.35 would be the
# coincidence trap this phase exists to abolish (D-07).
# ═════════════════════════════════════════════════════════════════════════════

# A run is TYPICAL when its callout's scale differs from the resolved page
# scale by more than this relative tolerance. The value matches
# ``takeoff_pipeline._SCALE_MATCH_TOL`` — the same test the pipeline already
# uses to decide whether a viewport is off the page scale — and a test pins
# the two equal so they cannot drift. (Binding by reference is impossible
# here: the deterministic layer must not import the pipeline layer.)
SCALE_MATCH_TOL = 0.05


def extract_rail_runs(
    page,
    doc,
    clip_pt: Sequence[float],
    feet_per_point: float,
    min_run_ft: float = MIN_RUN_FT,
    exclude_rects: Optional[Sequence] = None,
    viewport_title: str = "",
    page_feet_per_point: Optional[float] = None,
) -> List[OpenRun]:
    """Chain the rail runs drawn inside one callout-anchored clip.

    Sits directly on :func:`extract_open_runs` — the ONE chainer — with the
    pen partition on, because a rail's two faces are drawn with one pen and
    the linework that continues past the rail's end is drawn with another.
    Never offered unclipped: the clip requirement is inherited from the core
    (a ``None`` clip returns ``[]``), and running unclipped on Crow's overall
    floor plan chained a hatch field into a 369-foot phantom (INV-06 risk 4).

    ``feet_per_point`` is the CALLOUT's scale — the scale printed beneath the
    detail the clip covers — never the page's. ``page_feet_per_point`` is the
    resolved page scale, used only to stamp ``is_typical``: a run measured at
    an off-page-scale callout is a typical detail, drawn once and installed
    many times, and must never be summed with a main-plan run of the same
    object.
    """
    runs = extract_open_runs(
        page,
        doc,
        clip_pt,
        feet_per_point,
        min_run_ft=min_run_ft,
        exclude_rects=exclude_rects,
        candidate_prefix="RAIL",
        per_pen=True,
    )
    scale_fpi = feet_per_point * 72.0
    typical = False
    if page_feet_per_point and page_feet_per_point > 0:
        typical = (
            abs(feet_per_point - page_feet_per_point)
            > SCALE_MATCH_TOL * page_feet_per_point
        )
    for run in runs:
        run.viewport_title = viewport_title
        run.scale_fpi = scale_fpi
        run.is_typical = typical
    return runs


# ═════════════════════════════════════════════════════════════════════════════
# SCALE BINDING — a run is measured at its own drawing's scale, or not at all
# ═════════════════════════════════════════════════════════════════════════════

# The same containment slack printed_scale._contains grants a label that sits
# a hair outside its region — coordinate rounding, never a different drawing.
CONTAIN_MARGIN_PT = 6.0


def _display_box(page, bbox) -> Tuple[float, float, float, float]:
    """*bbox* mapped to DISPLAY (page) space via THE one rotation transform.

    Identity on an unrotated page and when *page* cannot answer, exactly like
    ``printed_scale._in_page_space`` — this module does not own a second copy
    of the rotation matrix (D-03).
    """
    if page is None:
        return tuple(float(v) for v in bbox)
    try:
        import fitz  # noqa: PLC0415 — optional at import time for test stubs

        rect = to_page_space(page, fitz.Rect(*bbox))
        return float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)
    except Exception:  # noqa: BLE001 — binding must never raise
        return tuple(float(v) for v in bbox)


def run_scale_fpp(page, run, viewports, printed_by_region) -> Optional[float]:
    """Feet-per-point of the drawing that CONTAINS *run*, or ``None``.

    The containment test runs in DISPLAY space — the space the sheet is read
    in — with both the run's bbox and every viewport's bbox mapped through
    ``room_fill.to_page_space``, the same discipline the area path follows
    (INV-04 §4 BUG-C: on a ``/Rotate 270`` sheet, mixing spaces binds a run to
    the wrong drawing). On unrotated pages the transform is the identity by
    construction.

    The owner is the SMALLEST containing non-mask viewport: when a detail is
    nested inside a plan, the detail is the drawing the run belongs to. If
    that drawing has no printed callout of its own, the answer is ``None`` and
    *run* is flagged — a run is NEVER measured at a borrowed scale. On Bob's
    roof plan, borrowing the page's fallback 1.0 ft/in would report the
    ~880 LF gas main as roughly eighty (T-23-47, critical). The larger
    containing plan's scale is NOT consulted either: the outer drawing's
    scale is not the inner drawing's.

    On success the run is stamped with the callout's feet-per-inch (and its
    title, when the run carries none) and the callout's feet-per-point is
    returned. The caller converts: ``run.length_lf(fpp)``.
    """
    try:
        run_box = _display_box(page, run.bbox_pt)
        containing = []
        for vp in viewports:
            if getattr(vp, "kind", "") in _VIEWPORT_MASK_KINDS:
                continue
            box = _display_box(page, vp.bbox_pt)
            if (
                box[0] - CONTAIN_MARGIN_PT <= run_box[0]
                and run_box[2] <= box[2] + CONTAIN_MARGIN_PT
                and box[1] - CONTAIN_MARGIN_PT <= run_box[1]
                and run_box[3] <= box[3] + CONTAIN_MARGIN_PT
            ):
                area = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
                containing.append((area, getattr(vp, "region_id", "")))
        if not containing:
            run.needs_review = True
            run.review_reason = (
                "no viewport contains this run — not measured (a borrowed "
                "page scale is an order-of-magnitude error)"
            )
            return None
        containing.sort()
        owner_id = containing[0][1]
        printed = (printed_by_region or {}).get(owner_id)
        if printed is None:
            run.needs_review = True
            run.review_reason = (
                "the containing drawing (%s) has no printed scale of its own "
                "— not measured (a borrowed page scale is an "
                "order-of-magnitude error)" % (owner_id or "unknown")
            )
            return None
        run.scale_fpi = printed.feet_per_inch
        if not run.viewport_title:
            run.viewport_title = printed.title
        return printed.feet_per_point
    except Exception as exc:  # noqa: BLE001 — untrusted input must not crash
        logger.warning("Run scale binding failed: %s", exc)
        run.needs_review = True
        run.review_reason = "scale binding failed: %s" % exc
        return None
