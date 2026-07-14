"""Wall segment extraction (Recipe B) — deterministic LF by thickness class.

Walls in CAD PDFs are drawn as two parallel lines at wall-thickness distance
(3"–16" real), often with fill or hatch between. This module measures them:

1. Harvest visible stroke segments; flatten Bézier ("c") items at 0.5 pt
   chordal tolerance (Recipe E / Pitfall 6 — curved walls must be measured).
2. Drop segments shorter than 2 ft-equivalent; collapse hatch fields
   (Pitfall 2) so dense parallel stroke groups cannot masquerade as walls.
3. Group by angle (1° quantization); pair segments whose perpendicular
   offsets differ by a plausible wall thickness and whose projections
   overlap ≥ 70%.
4. Merge collinear centerline chains; gaps ≤ 4 ft-equivalent are recorded as
   opening candidates (door openings cluster at 3'-0" — the scale solver's
   ``door_check`` cross-validation input).
5. Quantize thickness into 0.5" classes → "TC1", "TC2", … ordered by total
   LF descending.

Vision's role downstream is to LABEL which thickness class is CMU vs
tilt-up vs stud partition (from the wall-type legend / hatch pattern),
never to produce the LF number — the CMU "17 vs 2,204 SF" fix.

``WallSegment`` stores point-space measures only (RawGeometry
points-until-scale-bound pattern): ``wall_lf_by_class`` /
``opening_gap_widths`` do the fpp conversion as pure math, so a human scale
correction rescales instantly without re-extraction.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from bobbytailor.deterministic.dimensions import (
    _mid_in_exclude_rects,
    _visible_drawings,
)
from bobbytailor.deterministic.symbols import _collapse_hatch_fields

logger = logging.getLogger(__name__)

# ── Tuning constants (Recipe B) ───────────────────────────────────────────────

# Segments shorter than this real length never participate in wall pairing
# (Recipe B step 1; also part of the resource-exhaustion mitigation).
MIN_WALL_SEG_FT = 2.0
# Angle quantization for parallel grouping.
ANGLE_QUANT_DEG = 1.0
# Plausible wall thickness window, real feet (3"–16").
MIN_THICKNESS_FT = 0.25
MAX_THICKNESS_FT = 16.0 / 12.0
# Paired segments must overlap at least this share of the shorter one.
MIN_PAIR_OVERLAP = 0.70
# A new pair may reuse a segment only where ≤ this share of its overlap
# interval was already claimed (lets one long face pair with several broken
# opposite pieces without letting parallel triples double-count walls).
MAX_REUSED_OVERLAP = 0.20
# Collinear chain merge: gaps up to a door-width tolerance are openings.
MAX_OPENING_FT = 4.0
# Gaps below this are drafting noise — bridged silently, not openings.
MIN_OPENING_FT = 0.25
# Door-leaf corroboration: perpendicular segment length vs gap width band,
# and endpoint proximity multipliers (see _has_door_leaf).
LEAF_LEN_MIN_FRAC = 0.7
LEAF_LEN_MAX_FRAC = 1.4
LEAF_ANGLE_TOL_BINS = 3
# Thickness class bin width (inches).
THICKNESS_BIN_IN = 0.5
# Chained pieces must agree on thickness within one bin.
CHAIN_THICKNESS_TOL_IN = 0.5
# Bézier flattening chordal tolerance (Recipe E).
BEZIER_CHORD_TOL_PT = 0.5
_BEZIER_MAX_DEPTH = 16
# Curved-wall pairing: offset spread tolerance (constant-offset check).
CURVE_OFFSET_SPREAD_FRAC = 0.20
CURVE_OFFSET_SPREAD_MIN_PT = 0.75
CURVE_MIN_LENGTH_RATIO = 0.5
# Sheets where Bézier length ≥ this share of linework need curve-support
# verification (Pitfall 6).
CURVE_REVIEW_SHARE = 0.05
# Resource-exhaustion cap (threat model): above this, return no walls.
MAX_SEGMENTS = 200_000
# Chains deterministically confident at this real length and above.
HIGH_CONFIDENCE_FT = 4.0

_EPS = 1e-9
_ANGLE_BINS = int(round(180.0 / ANGLE_QUANT_DEG))

Point = Tuple[float, float]
Segment = Tuple[float, float, float, float]


@dataclass
class WallSegment:
    """One merged wall centerline chain, measured in PDF points only.

    ``centerline_pt`` is a tuple of (x, y) vertices — two for straight walls,
    more for flattened curved walls. ``length_pt`` is the MATERIAL length
    (opening gaps excluded); the end-to-end centerline span includes them.
    """

    centerline_pt: tuple          # ((x, y), ...) polyline vertices
    length_pt: float              # material length in points (gaps excluded)
    thickness_pt: float           # perpendicular pair offset in points
    angle_deg: float              # 0–180, quantized group angle
    thickness_class: str          # "TC1", "TC2", ... by total LF descending
    openings_pt: List[tuple] = field(default_factory=list)  # ((x0,y0),(x1,y1))
    candidate_id: str = ""        # "WALL-TC1" — one id per thickness class
    confidence: str = "medium"

    def to_dict(self) -> dict:
        return asdict(self)


# ── Harvest: segments + flattened Bézier polylines ────────────────────────────


def _seg_len(s: Segment) -> float:
    return math.hypot(s[2] - s[0], s[3] - s[1])


def _seg_mid(s: Segment) -> Point:
    return ((s[0] + s[2]) / 2.0, (s[1] + s[3]) / 2.0)


def _polyline_len(pts: Sequence[Point]) -> float:
    return sum(
        math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        for i in range(len(pts) - 1)
    )


def _flat_enough(p0: Point, p1: Point, p2: Point, p3: Point, tol: float) -> bool:
    """True when control points deviate from the p0–p3 chord by ≤ tol."""
    dx, dy = p3[0] - p0[0], p3[1] - p0[1]
    chord = math.hypot(dx, dy)
    if chord < _EPS:
        return (
            math.hypot(p1[0] - p0[0], p1[1] - p0[1]) <= tol
            and math.hypot(p2[0] - p0[0], p2[1] - p0[1]) <= tol
        )
    ux, uy = dx / chord, dy / chord
    for p in (p1, p2):
        px, py = p[0] - p0[0], p[1] - p0[1]
        # Perpendicular distance to the chord line, clamped to the span.
        perp = abs(px * (-uy) + py * ux)
        if perp > tol:
            return False
    return True


def _flatten_bezier(
    p0: Point,
    p1: Point,
    p2: Point,
    p3: Point,
    tol: float = BEZIER_CHORD_TOL_PT,
    depth: int = 0,
) -> List[Point]:
    """Flatten one cubic Bézier to points (excluding p0) at chordal tol."""
    if depth >= _BEZIER_MAX_DEPTH or _flat_enough(p0, p1, p2, p3, tol):
        return [p3]
    # de Casteljau split at t = 0.5.
    m01 = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
    m12 = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    m23 = ((p2[0] + p3[0]) / 2.0, (p2[1] + p3[1]) / 2.0)
    m012 = ((m01[0] + m12[0]) / 2.0, (m01[1] + m12[1]) / 2.0)
    m123 = ((m12[0] + m23[0]) / 2.0, (m12[1] + m23[1]) / 2.0)
    mid = ((m012[0] + m123[0]) / 2.0, (m012[1] + m123[1]) / 2.0)
    left = _flatten_bezier(p0, m01, m012, mid, tol, depth + 1)
    right = _flatten_bezier(mid, m123, m23, p3, tol, depth + 1)
    return left + right


def _rect_edges(r) -> List[Segment]:
    return [
        (r.x0, r.y0, r.x1, r.y0),
        (r.x1, r.y0, r.x1, r.y1),
        (r.x1, r.y1, r.x0, r.y1),
        (r.x0, r.y1, r.x0, r.y0),
    ]


def _quad_edges(q) -> List[Segment]:
    ul, ur, lr, ll = q.ul, q.ur, q.lr, q.ll
    return [
        (ul.x, ul.y, ur.x, ur.y),
        (ur.x, ur.y, lr.x, lr.y),
        (lr.x, lr.y, ll.x, ll.y),
        (ll.x, ll.y, ul.x, ul.y),
    ]


def _is_stroked(path) -> bool:
    """Recipe B step 1: walls are stroke-drawn (type contains 's')."""
    ptype = path.get("type")
    if ptype is None:
        return True
    return "s" in str(ptype)


def _harvest(page, doc, exclude_rects: Optional[Sequence]):
    """Return ``(segments, curve_polylines, straight_len_pt, curve_len_pt)``.

    Straight segments come from "l"/"re"/"qu" items; consecutive "c" items in
    one path are chained into flattened curve polylines (Recipe E). Length
    totals are pre-filter, for the Pitfall-6 curve-share flag.
    """
    segments: List[Segment] = []
    curves: List[List[Point]] = []
    straight_len = 0.0
    curve_len = 0.0

    for path in _visible_drawings(page, doc):
        if not _is_stroked(path):
            continue
        chain: List[Point] = []

        def _flush_chain() -> None:
            nonlocal curve_len
            if len(chain) >= 2:
                length = _polyline_len(chain)
                curve_len += length
                curves.append(list(chain))
            del chain[:]

        for it in path.get("items", []):
            op = it[0]
            if op == "c":
                p0 = (it[1].x, it[1].y)
                p1 = (it[2].x, it[2].y)
                p2 = (it[3].x, it[3].y)
                p3 = (it[4].x, it[4].y)
                if chain and math.hypot(
                    chain[-1][0] - p0[0], chain[-1][1] - p0[1]
                ) > _EPS * 10 + 1e-6:
                    _flush_chain()
                if not chain:
                    chain.append(p0)
                chain.extend(_flatten_bezier(p0, p1, p2, p3))
                continue
            _flush_chain()
            if op == "l":
                a, b = it[1], it[2]
                seg = (a.x, a.y, b.x, b.y)
                segments.append(seg)
                straight_len += _seg_len(seg)
            elif op == "re":
                for seg in _rect_edges(it[1]):
                    segments.append(seg)
                    straight_len += _seg_len(seg)
            elif op == "qu":
                try:
                    edges = _quad_edges(it[1])
                except AttributeError:
                    continue
                for seg in edges:
                    segments.append(seg)
                    straight_len += _seg_len(seg)
        _flush_chain()

    if exclude_rects:
        segments = [
            s for s in segments
            if not _mid_in_exclude_rects(_seg_mid(s), exclude_rects)
        ]
        curves = [
            c for c in curves
            if not _mid_in_exclude_rects(c[len(c) // 2], exclude_rects)
        ]
    return segments, curves, straight_len, curve_len


# ── Parallel-pair detection (straight walls) ─────────────────────────────────


def _angle_bin(seg: Segment) -> int:
    angle = math.degrees(math.atan2(seg[3] - seg[1], seg[2] - seg[0])) % 180.0
    return int(round(angle / ANGLE_QUANT_DEG)) % _ANGLE_BINS


def _interval_overlap_used(
    interval: Tuple[float, float],
    used: List[Tuple[float, float]],
) -> float:
    lo, hi = interval
    total = 0.0
    for ulo, uhi in used:
        total += max(0.0, min(hi, uhi) - max(lo, ulo))
    return total


def _pair_straight(
    segments: Sequence[Segment],
    fpp: float,
) -> Tuple[List[dict], Dict[int, List[dict]]]:
    """Pair parallel segments at wall-thickness offsets (Recipe B steps 2–3).

    Returns ``(pairs, entries_by_angle)``. Pairs are raw wall-pair records:
    ``{"angle_q", "u", "n", "off", "t0", "t1", "thickness_pt"}`` where
    ``u``/``n`` are the group direction / normal unit vectors and
    ``t0``/``t1`` bound the projection overlap along ``u``.
    ``entries_by_angle`` keeps every projected segment per angle bin so the
    chain merge can validate opening gaps against face-line coverage
    (dashed-line gaps break only ONE face; real door openings break both).
    """
    min_th = MIN_THICKNESS_FT / fpp
    max_th = MAX_THICKNESS_FT / fpp

    by_angle: Dict[int, List[Segment]] = defaultdict(list)
    for seg in segments:
        by_angle[_angle_bin(seg)].append(seg)

    pairs: List[dict] = []
    entries_by_angle: Dict[int, List[dict]] = {}
    for angle_q, group in by_angle.items():
        if len(group) < 2:
            continue
        theta = math.radians(angle_q * ANGLE_QUANT_DEG)
        ux, uy = math.cos(theta), math.sin(theta)
        nx, ny = -uy, ux

        entries = []
        for seg in group:
            t_a = seg[0] * ux + seg[1] * uy
            t_b = seg[2] * ux + seg[3] * uy
            mx, my = _seg_mid(seg)
            off = mx * nx + my * ny
            lo, hi = (t_a, t_b) if t_a <= t_b else (t_b, t_a)
            entries.append({"off": off, "lo": lo, "hi": hi, "len": hi - lo})
        entries.sort(key=lambda e: e["off"])
        entries_by_angle[angle_q] = entries

        candidates = []
        n_entries = len(entries)
        for i in range(n_entries):
            ei = entries[i]
            j = i + 1
            while j < n_entries and entries[j]["off"] - ei["off"] <= max_th:
                ej = entries[j]
                delta = ej["off"] - ei["off"]
                if delta >= min_th:
                    ov = min(ei["hi"], ej["hi"]) - max(ei["lo"], ej["lo"])
                    shorter = min(ei["len"], ej["len"])
                    if shorter > _EPS and ov >= MIN_PAIR_OVERLAP * shorter:
                        candidates.append((ov, -delta, i, j))
                j += 1

        # Greedy by overlap; a segment may serve several pairs only across
        # mostly-disjoint intervals (one continuous face vs broken pieces).
        candidates.sort(key=lambda c: (-c[0], c[1]))
        claimed: Dict[int, List[Tuple[float, float]]] = defaultdict(list)
        for ov, neg_delta, i, j in candidates:
            lo = max(entries[i]["lo"], entries[j]["lo"])
            hi = min(entries[i]["hi"], entries[j]["hi"])
            if hi - lo <= _EPS:
                continue
            reused_i = _interval_overlap_used((lo, hi), claimed[i])
            reused_j = _interval_overlap_used((lo, hi), claimed[j])
            if max(reused_i, reused_j) > MAX_REUSED_OVERLAP * (hi - lo):
                continue
            claimed[i].append((lo, hi))
            claimed[j].append((lo, hi))
            pairs.append(
                {
                    "angle_q": angle_q,
                    "u": (ux, uy),
                    "n": (nx, ny),
                    "off": (entries[i]["off"] + entries[j]["off"]) / 2.0,
                    "t0": lo,
                    "t1": hi,
                    "thickness_pt": -neg_delta,
                }
            )
    return pairs, entries_by_angle


def _gap_is_open_on_both_faces(
    gap_lo: float,
    gap_hi: float,
    off: float,
    thickness: float,
    entries: Sequence[dict],
) -> bool:
    """True when NO face line covers the gap interval (a real opening).

    Dashed wall lines (fire-rating, overhead tracks) produce periodic gaps on
    one face while the opposite face runs continuous — those must be bridged
    silently, never reported as door-opening candidates. A drawn opening
    breaks BOTH faces, so any near-face segment spanning the gap disproves it.
    """
    margin = max(0.1 * (gap_hi - gap_lo), _EPS)
    face_tol = max(0.5 * thickness, _EPS)
    for face_off in (off - thickness / 2.0, off + thickness / 2.0):
        for entry in entries:
            if abs(entry["off"] - face_off) > face_tol:
                continue
            if entry["lo"] <= gap_lo + margin and entry["hi"] >= gap_hi - margin:
                return False
    return True


def _point_seg_dist(p: Point, seg: Segment) -> float:
    px, py = p
    x0, y0, x1, y1 = seg
    dx, dy = x1 - x0, y1 - y0
    denom = dx * dx + dy * dy
    if denom < _EPS:
        return math.hypot(px - x0, py - y0)
    t = ((px - x0) * dx + (py - y0) * dy) / denom
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def _has_door_leaf(
    gap_a: Point,
    gap_b: Point,
    thickness: float,
    perp_segments: Sequence[Segment],
) -> bool:
    """True when a door-leaf-like segment corroborates the gap as an opening.

    Real doors on multi-line wall assemblies can keep one skin line running
    continuous across the opening (canopy/sill/panel lines), defeating the
    two-face-break test. The door LEAF is drawn perpendicular to the wall at
    roughly the opening width — a deterministic corroboration signal. Long
    perpendicular geometry (crossing walls) fails the length band.
    """
    gap_len = math.hypot(gap_b[0] - gap_a[0], gap_b[1] - gap_a[1])
    if gap_len < _EPS:
        return False
    gap_seg = (gap_a[0], gap_a[1], gap_b[0], gap_b[1])
    near_tol = max(2.0 * thickness, 0.5 * gap_len)
    lo_len = LEAF_LEN_MIN_FRAC * gap_len
    hi_len = LEAF_LEN_MAX_FRAC * gap_len
    for seg in perp_segments:
        length = _seg_len(seg)
        if not (lo_len <= length <= hi_len):
            continue
        for endpoint in ((seg[0], seg[1]), (seg[2], seg[3])):
            if _point_seg_dist(endpoint, gap_seg) <= near_tol:
                return True
    return False


# ── Collinear chain merge (Recipe B step 3) ───────────────────────────────────


def _merge_chains(
    pairs: Sequence[dict],
    fpp: float,
    entries_by_angle: Optional[Dict[int, List[dict]]] = None,
    segments: Optional[Sequence[Segment]] = None,
) -> List[WallSegment]:
    """Merge collinear wall pairs into chains; record opening gaps."""
    max_gap = MAX_OPENING_FT / fpp
    min_gap = MIN_OPENING_FT / fpp
    thick_tol = (CHAIN_THICKNESS_TOL_IN / 12.0) / fpp
    entries_by_angle = entries_by_angle or {}

    segs_by_bin: Dict[int, List[Segment]] = defaultdict(list)
    for seg in segments or []:
        segs_by_bin[_angle_bin(seg)].append(seg)

    def _perp_segments(angle_q: int) -> List[Segment]:
        base = (angle_q + _ANGLE_BINS // 2) % _ANGLE_BINS
        out: List[Segment] = []
        for delta in range(-LEAF_ANGLE_TOL_BINS, LEAF_ANGLE_TOL_BINS + 1):
            out.extend(segs_by_bin.get((base + delta) % _ANGLE_BINS, []))
        return out

    grouped: Dict[int, List[dict]] = defaultdict(list)
    for pair in pairs:
        grouped[pair["angle_q"]].append(pair)

    walls: List[WallSegment] = []
    for angle_q, group in grouped.items():
        group.sort(key=lambda p: (p["off"], p["t0"]))

        # Cluster by centerline offset: collinear when offsets agree within
        # half the wall thickness AND thickness agrees within one bin.
        clusters: List[List[dict]] = []
        for pair in group:
            placed = False
            for cluster in clusters:
                ref = cluster[-1]
                off_tol = 0.5 * max(pair["thickness_pt"], ref["thickness_pt"])
                if (
                    abs(pair["off"] - ref["off"]) <= off_tol
                    and abs(pair["thickness_pt"] - ref["thickness_pt"]) <= thick_tol
                ):
                    cluster.append(pair)
                    placed = True
                    break
            if not placed:
                clusters.append([pair])

        for cluster in clusters:
            # Union overlapping intervals first (duplicate coverage from
            # multi-pairing collapses here).
            cluster.sort(key=lambda p: p["t0"])
            pieces: List[List[float]] = []  # [t0, t1, weight·thickness, weight]
            for pair in cluster:
                t0, t1, th = pair["t0"], pair["t1"], pair["thickness_pt"]
                if pieces and t0 <= pieces[-1][1] + _EPS:
                    pieces[-1][1] = max(pieces[-1][1], t1)
                    pieces[-1][2] += (t1 - t0) * th
                    pieces[-1][3] += t1 - t0
                else:
                    pieces.append([t0, t1, (t1 - t0) * th, t1 - t0])

            # Walk pieces; bridge gaps ≤ door tolerance, else flush chain.
            u = cluster[0]["u"]
            n = cluster[0]["n"]
            off = sum(p["off"] for p in cluster) / len(cluster)

            def _xy(t: float) -> Point:
                return (t * u[0] + off * n[0], t * u[1] + off * n[1])

            chain: List[List[float]] = []
            openings: List[tuple] = []

            def _flush() -> None:
                if not chain:
                    return
                material = sum(p[1] - p[0] for p in chain)
                weight = sum(p[3] for p in chain) or _EPS
                thickness = sum(p[2] for p in chain) / weight
                start, end = chain[0][0], chain[-1][1]
                length_ft = material * fpp
                walls.append(
                    WallSegment(
                        centerline_pt=(_xy(start), _xy(end)),
                        length_pt=material,
                        thickness_pt=thickness,
                        angle_deg=angle_q * ANGLE_QUANT_DEG,
                        thickness_class="",
                        openings_pt=list(openings),
                        confidence=(
                            "high" if length_ft >= HIGH_CONFIDENCE_FT else "medium"
                        ),
                    )
                )
                del chain[:]
                del openings[:]

            angle_entries = entries_by_angle.get(angle_q, [])
            perp_segs = _perp_segments(angle_q)
            avg_thickness = (
                sum(p["thickness_pt"] for p in cluster) / len(cluster)
            )

            for piece in pieces:
                if chain:
                    gap = piece[0] - chain[-1][1]
                    if gap > max_gap:
                        _flush()
                    elif gap > min_gap:
                        gap_a = _xy(chain[-1][1])
                        gap_b = _xy(piece[0])
                        is_opening = _gap_is_open_on_both_faces(
                            chain[-1][1], piece[0], off, avg_thickness,
                            angle_entries,
                        ) or _has_door_leaf(
                            gap_a, gap_b, avg_thickness, perp_segs
                        )
                        if is_opening:
                            openings.append((gap_a, gap_b))
                chain.append(piece)
            _flush()
    return walls


# ── Curved-wall pairing (Pitfall 6: arc pairs at constant offset) ────────────


def _pair_curves(curves: Sequence[Sequence[Point]], fpp: float) -> List[WallSegment]:
    """Pair flattened curve polylines at constant wall-thickness offset."""
    if len(curves) < 2:
        return []
    try:
        from shapely.geometry import LineString, Point as ShapelyPoint
    except Exception:  # noqa: BLE001 — shapely is a hard dep, but stay safe
        return []

    min_th = MIN_THICKNESS_FT / fpp
    max_th = MAX_THICKNESS_FT / fpp

    open_curves = []
    for pts in curves:
        # Drop consecutive duplicates — zero-length sub-segments make GEOS
        # distance emit NaN on some versions.
        deduped: List[Point] = []
        for p in pts:
            if not (math.isfinite(p[0]) and math.isfinite(p[1])):
                continue
            if deduped and math.hypot(
                p[0] - deduped[-1][0], p[1] - deduped[-1][1]
            ) <= _EPS:
                continue
            deduped.append(p)
        if len(deduped) < 2:
            continue
        # Closed loops (circles = symbol geometry, Recipe D territory) are
        # excluded — wall arcs are open runs.
        if math.hypot(
            deduped[0][0] - deduped[-1][0], deduped[0][1] - deduped[-1][1]
        ) <= 1.0:
            continue
        open_curves.append(deduped)

    lines = [LineString(pts) for pts in open_curves]
    used: set = set()
    walls: List[WallSegment] = []

    for i in range(len(lines)):
        if i in used:
            continue
        best = None  # (spread, j, samples)
        for j in range(i + 1, len(lines)):
            if j in used:
                continue
            a, b = lines[i], lines[j]
            if a.length < _EPS or b.length < _EPS:
                continue
            ratio = min(a.length, b.length) / max(a.length, b.length)
            if ratio < CURVE_MIN_LENGTH_RATIO:
                continue
            # Bbox proximity gate before distance sampling.
            (ax0, ay0, ax1, ay1) = a.bounds
            (bx0, by0, bx1, by1) = b.bounds
            if (
                ax0 - max_th > bx1
                or bx0 - max_th > ax1
                or ay0 - max_th > by1
                or by0 - max_th > ay1
            ):
                continue
            short, other = (a, b) if a.length <= b.length else (b, a)
            n_samples = max(8, min(32, len(short.coords)))
            dists = []
            sample_pts = []
            for k in range(n_samples + 1):
                p = short.interpolate(short.length * k / n_samples)
                dists.append(other.distance(p))
                sample_pts.append(p)
            med = sorted(dists)[len(dists) // 2]
            if not (min_th <= med <= max_th):
                continue
            spread = max(dists) - min(dists)
            if spread > max(CURVE_OFFSET_SPREAD_FRAC * med, CURVE_OFFSET_SPREAD_MIN_PT):
                continue
            if best is None or spread < best[0]:
                best = (spread, j, (short, other, sample_pts, med))
        if best is None:
            continue
        _, j, (short, other, sample_pts, med) = best
        used.add(i)
        used.add(j)

        mids: List[Point] = []
        for p in sample_pts:
            q = other.interpolate(other.project(p))
            mids.append(((p.x + q.x) / 2.0, (p.y + q.y) / 2.0))
        length = _polyline_len(mids)
        if length < _EPS:
            continue
        chord_dx = mids[-1][0] - mids[0][0]
        chord_dy = mids[-1][1] - mids[0][1]
        angle = math.degrees(math.atan2(chord_dy, chord_dx)) % 180.0
        walls.append(
            WallSegment(
                centerline_pt=tuple(mids),
                length_pt=length,
                thickness_pt=med,
                angle_deg=round(angle, 1),
                thickness_class="",
                openings_pt=[],
                confidence=(
                    "high" if length * fpp >= HIGH_CONFIDENCE_FT else "medium"
                ),
            )
        )
    return walls


# ── Thickness classes ─────────────────────────────────────────────────────────


def _assign_thickness_classes(walls: List[WallSegment], fpp: float) -> None:
    """Quantize thickness into 0.5" bins → TC1, TC2… by total LF descending."""
    totals: Dict[float, float] = defaultdict(float)
    bins: List[float] = []
    for wall in walls:
        thickness_in = wall.thickness_pt * fpp * 12.0
        bin_in = round(thickness_in / THICKNESS_BIN_IN) * THICKNESS_BIN_IN
        bins.append(bin_in)
        totals[bin_in] += wall.length_pt

    order = sorted(totals, key=lambda b: (-totals[b], b))
    labels = {bin_in: "TC%d" % (rank + 1) for rank, bin_in in enumerate(order)}
    for wall, bin_in in zip(walls, bins):
        wall.thickness_class = labels[bin_in]
        wall.candidate_id = "WALL-%s" % labels[bin_in]


# ── Public API ────────────────────────────────────────────────────────────────


def extract_walls_detailed(
    page,
    fpp: float,
    exclude_rects: Optional[Sequence] = None,
) -> dict:
    """Full Recipe B pipeline with sheet-level metadata.

    Returns ``{"walls", "hatch_regions", "needs_review", "review_reasons"}``.
    ``hatch_regions`` keeps the collapsed hatch-class tags per region
    (Pitfall 2 — CMU vs concrete hatch is a vision labeling signal).
    One-page failure returns empty results, never raises (threat model).
    """
    result: dict = {
        "walls": [],
        "hatch_regions": [],
        "needs_review": False,
        "review_reasons": [],
    }
    if not fpp or fpp <= 0:
        logger.warning("Wall extraction requires a solved scale (fpp); skipping")
        return result
    try:
        doc = getattr(page, "parent", None)
        segments, curves, straight_len, curve_len = _harvest(
            page, doc, exclude_rects
        )

        total_len = straight_len + curve_len
        if total_len > 0 and curve_len / total_len >= CURVE_REVIEW_SHARE:
            result["needs_review"] = True
            result["review_reasons"].append("curve support verification")

        min_len_pt = MIN_WALL_SEG_FT / fpp
        segments = [s for s in segments if _seg_len(s) >= min_len_pt]
        curves = [c for c in curves if _polyline_len(c) >= min_len_pt]

        if len(segments) > MAX_SEGMENTS:
            logger.warning(
                "Wall extraction: %d segments exceed cap %d; skipping page",
                len(segments),
                MAX_SEGMENTS,
            )
            result["needs_review"] = True
            result["review_reasons"].append("segment cap exceeded")
            return result

        segments, hatch_regions = _collapse_hatch_fields(segments)
        result["hatch_regions"] = hatch_regions

        pairs, entries_by_angle = _pair_straight(segments, fpp)
        walls = _merge_chains(pairs, fpp, entries_by_angle, segments)
        walls.extend(_pair_curves(curves, fpp))
        _assign_thickness_classes(walls, fpp)
        walls.sort(key=lambda w: -w.length_pt)
        result["walls"] = walls
        return result
    except Exception as exc:  # noqa: BLE001 — untrusted PDF must not crash
        logger.warning("Wall extraction failed: %s", exc)
        return result


def extract_walls(
    page,
    fpp: float,
    exclude_rects: Optional[Sequence] = None,
) -> List[WallSegment]:
    """Recipe B: parallel-pair wall extraction. See ``extract_walls_detailed``."""
    return extract_walls_detailed(page, fpp, exclude_rects=exclude_rects)["walls"]


def wall_lf_by_class(walls: Sequence[WallSegment], fpp: float) -> Dict[str, float]:
    """Total wall LF per thickness class (pure fpp conversion — recompute-safe)."""
    if not fpp or fpp <= 0:
        return {}
    totals: Dict[str, float] = defaultdict(float)
    for wall in walls:
        if wall.thickness_class:
            totals[wall.thickness_class] += wall.length_pt * fpp
    return {cls: round(lf, 1) for cls, lf in totals.items()}


def opening_gap_widths(walls: Sequence[WallSegment], fpp: float) -> List[float]:
    """All wall-opening gap widths in feet — feeds scale-solver door_check."""
    if not fpp or fpp <= 0:
        return []
    widths: List[float] = []
    for wall in walls:
        for opening in wall.openings_pt:
            (x0, y0), (x1, y1) = opening
            widths.append(math.hypot(x1 - x0, y1 - y0) * fpp)
    return widths
