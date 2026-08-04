"""Room polygon closure (Recipe C) — deterministic room/floor SF.

Builds a noded line network from wall centerlines (plus straight closures
across door-opening gaps and junction snap connectors), polygonizes it into
faces, and binds room-name labels from the PDF text layer:

1. ``extract_walls`` centerline chains span their opening gaps end-to-end,
   so the network already closes across doors.
2. Junction snapping: a centerline chain stops half a wall thickness short
   of the crossing wall's centerline — endpoints within a snap tolerance get
   a straight connector so ``polygonize`` can close the faces.
3. ``shapely.ops.polygonize`` over ``unary_union`` (noding) → candidate
   faces; discard faces outside the viewport, slivers < 10 SF-equivalent,
   and exterior envelope faces; islands are subtracted (holes respected —
   the atrium/irregular-footprint fix).
4. Labels are bound deterministically by point-in-polygon over
   ``get_text("words")`` room-name tokens; vision is only a fallback for
   rooms left with ``label_source='none'`` (fusion layer, 21-11+).

``building_footprint`` unions room faces with wall footprints into the
exterior envelope — replacing the rectangular assumption and the
0.72–0.87× trimmed-extent error — and cross-checks the result against the
overall-dims footprint (``footprint_takeoff``). Both are deterministic, so
they should agree within 2%; disagreement flags review, never silently
picks a winner.

All polygon math is shapely (Don't Hand-Roll); invalid polygons are
repaired via ``buffer(0)`` or dropped. One-page failure returns empty
results, never raises (threat model).
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.strtree import STRtree

from bobbytailor.deterministic.dimensions import parse_feet_inches

logger = logging.getLogger(__name__)

# ── Tuning constants (Recipe C) ───────────────────────────────────────────────

# Faces below this real area are drafting slivers, not rooms.
MIN_ROOM_SF = 10.0
# Junction snap: connect a chain endpoint to a nearby centerline within this
# real distance (junction gaps are half the crossing wall's thickness).
SNAP_TOL_FT = 1.5
# Resource-exhaustion cap (threat model): above this many centerline
# segments, skip room extraction with a logged warning.
MAX_NETWORK_SEGMENTS = 50_000
# Footprint dual-method agreement threshold (RESEARCH Recipe C: ≤ 2%).
FOOTPRINT_AGREE_TOL = 0.02
# Coordinate precision grid (points) applied to network inputs before
# unary_union: connector endpoints computed by ``interpolate`` round off the
# target line in floating point, so GEOS never nodes them and polygonize
# leaves cut edges (faces silently merge). 1e-6 pt is far below drawing
# tolerance and makes the noding robust.
NETWORK_PRECISION_GRID = 1e-6
# A candidate face whose contained-island area exceeds this share is an
# exterior envelope (e.g. sheet/viewport border ring), not a room.
MAX_HOLE_SHARE = 0.6

# Room-name tokens: uppercase alpha words ("OFFICE", "WAREHOUSE", "STOR.")
# or room numbers ("101", "A101").
_ROOM_WORD_RE = re.compile(r"^[A-Z][A-Z&./\-']{2,}$")
_ROOM_NUM_RE = re.compile(r"^[A-Z]?\d{1,4}$")
# Drafting annotations that are never room names (label noise filter).
_LABEL_STOPWORDS = frozenset(
    {
        "TYP", "TYP.", "MATCHLINE", "SEE", "DWG", "DWG.", "DWGS", "SHEET",
        "SCALE", "NOTE", "NOTES", "DETAIL", "SIM", "SIM.", "NORTH", "SOUTH",
        "EAST", "WEST", "PLAN", "FLOOR", "REF", "REF.", "OVERHEAD",
        "DRIVE-IN", "STRUCTURAL", "BRACING",
    }
)

_EPS = 1e-9


@dataclass
class RoomPolygon:
    """One closed room face with deterministic label binding."""

    polygon_wkt: str
    area_pt2: float
    label: str
    label_source: str        # 'text_in_polygon' | 'vision' | 'none'
    candidate_id: str        # "ROOM-1", "ROOM-2", ... by area descending
    confidence: str

    def to_dict(self) -> dict:
        return asdict(self)


# ── Network construction ──────────────────────────────────────────────────────


def _wall_lines(walls: Sequence) -> List[LineString]:
    """Wall centerline chains as LineStrings (opening gaps already spanned)."""
    lines: List[LineString] = []
    for wall in walls:
        pts = [
            (float(x), float(y))
            for x, y in getattr(wall, "centerline_pt", ()) or ()
            if math.isfinite(x) and math.isfinite(y)
        ]
        deduped: List[Tuple[float, float]] = []
        for p in pts:
            if deduped and math.hypot(
                p[0] - deduped[-1][0], p[1] - deduped[-1][1]
            ) <= _EPS:
                continue
            deduped.append(p)
        if len(deduped) >= 2:
            lines.append(LineString(deduped))
    return lines


def _snap_connectors(lines: Sequence[LineString], snap_tol: float) -> List[LineString]:
    """Straight connectors from chain endpoints to nearby centerlines.

    Wall centerlines stop half the crossing wall's thickness short of the
    junction; without these closures polygonize cannot form faces.
    """
    if not lines or snap_tol <= 0:
        return []
    tree = STRtree(list(lines))
    connectors: List[LineString] = []
    for i, line in enumerate(lines):
        coords = list(line.coords)
        for endpoint in (coords[0], coords[-1]):
            p = Point(endpoint)
            query = box(
                endpoint[0] - snap_tol,
                endpoint[1] - snap_tol,
                endpoint[0] + snap_tol,
                endpoint[1] + snap_tol,
            )
            best_d = snap_tol
            best_q: Optional[Point] = None
            for idx in tree.query(query):
                j = int(idx)
                if j == i:
                    continue
                other = lines[j]
                d = other.distance(p)
                if _EPS < d <= best_d:
                    best_d = d
                    best_q = other.interpolate(other.project(p))
            if best_q is not None:
                connectors.append(
                    LineString([endpoint, (best_q.x, best_q.y)])
                )
    return connectors


# ── Face filtering ────────────────────────────────────────────────────────────


def _valid_polygon(geom) -> Optional[Polygon]:
    """Repair via buffer(0) or drop (threat-model precision trap)."""
    try:
        if geom.is_empty:
            return None
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty:
            return None
        if isinstance(geom, Polygon):
            return geom
        # buffer(0) may return a MultiPolygon — keep the largest part.
        parts = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
        if parts:
            return max(parts, key=lambda g: g.area)
    except Exception:  # noqa: BLE001
        return None
    return None


def _filter_faces(
    faces: Sequence[Polygon],
    viewport_bbox: Optional[Sequence],
    min_area_pt2: float,
) -> List[Polygon]:
    """Recipe C step 2: viewport / sliver / exterior-envelope filtering."""
    vp = None
    if viewport_bbox:
        try:
            x0, y0, x1, y1 = viewport_bbox
            vp = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        except (TypeError, ValueError):
            vp = None

    candidates: List[Polygon] = []
    for face in faces:
        poly = _valid_polygon(face)
        if poly is None:
            continue
        if poly.area < min_area_pt2:
            continue
        if vp is not None and not vp.contains(poly.representative_point()):
            continue
        candidates.append(poly)

    # Envelope handling: a face containing other faces gets its islands
    # subtracted (holes respected). If most of its area was islands, it is
    # the exterior envelope (border ring), not a room — drop it.
    out: List[Polygon] = []
    for i, poly in enumerate(candidates):
        islands = [
            other
            for j, other in enumerate(candidates)
            if j != i
            and other.area < poly.area
            and poly.contains(other.representative_point())
        ]
        if islands:
            original_area = poly.area
            try:
                reduced = poly.difference(unary_union(islands))
            except Exception:  # noqa: BLE001
                reduced = poly
            reduced = _valid_polygon(reduced)
            if reduced is None or reduced.area < min_area_pt2:
                continue
            if (original_area - reduced.area) / original_area > MAX_HOLE_SHARE:
                continue  # exterior envelope — mostly other faces
            poly = reduced
        out.append(poly)
    return out


# ── Label binding (text-in-polygon) ───────────────────────────────────────────


def _room_label_words(page) -> List[Tuple[float, float, str]]:
    """(cx, cy, token) for words that read like room names or numbers."""
    try:
        words = page.get_text("words")
    except Exception:  # noqa: BLE001
        return []
    out: List[Tuple[float, float, str]] = []
    for w in words or []:
        try:
            x0, y0, x1, y1, token = w[0], w[1], w[2], w[3], str(w[4]).strip()
        except (IndexError, TypeError, ValueError):
            continue
        if not token:
            continue
        if parse_feet_inches(token) is not None:
            continue  # dimension strings are not room names
        if token.upper() in _LABEL_STOPWORDS:
            continue
        if _ROOM_WORD_RE.match(token) or _ROOM_NUM_RE.match(token):
            out.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0, token))
    return out


def _bind_labels(
    faces: Sequence[Polygon],
    label_words: Sequence[Tuple[float, float, str]],
) -> List[Tuple[str, str]]:
    """Per face: (label, label_source) via point-in-polygon in reading order."""
    results: List[Tuple[str, str]] = []
    for face in faces:
        hits = [
            (cy, cx, token)
            for cx, cy, token in label_words
            if face.contains(Point(cx, cy))
        ]
        if not hits:
            results.append(("", "none"))
            continue
        hits.sort()
        label = " ".join(token for _, _, token in hits)[:60].strip()
        results.append((label, "text_in_polygon"))
    return results


# ── Public API ────────────────────────────────────────────────────────────────


def extract_rooms(
    page,
    walls: Sequence,
    viewport_bbox: Optional[Sequence],
    fpp: float,
) -> List[RoomPolygon]:
    """Recipe C: polygonize the wall centerline network into labeled rooms.

    ``walls`` are ``WallSegment``s from ``extract_walls`` (their centerline
    chains span opening gaps, providing the door closures). Returns rooms
    ordered by area descending with candidate ids "ROOM-1"…; unlabeled
    rooms carry ``label_source='none'`` for the vision fallback.
    """
    try:
        if not fpp or fpp <= 0 or not walls:
            return []
        lines = _wall_lines(walls)
        if not lines:
            return []

        n_segments = sum(len(line.coords) - 1 for line in lines)
        if n_segments > MAX_NETWORK_SEGMENTS:
            logger.warning(
                "Room extraction: %d network segments exceed cap %d; "
                "skipping page (needs_review)",
                n_segments,
                MAX_NETWORK_SEGMENTS,
            )
            return []

        connectors = _snap_connectors(lines, SNAP_TOL_FT / fpp)
        members = lines + connectors
        try:
            import shapely as _shapely

            members = [
                _shapely.set_precision(g, NETWORK_PRECISION_GRID)
                for g in members
            ]
        except (ImportError, AttributeError):  # pragma: no cover — shapely<2
            pass
        network = unary_union(members)
        faces = list(polygonize(network))
        if not faces:
            return []

        min_area_pt2 = MIN_ROOM_SF / (fpp * fpp)
        rooms_polys = _filter_faces(faces, viewport_bbox, min_area_pt2)
        if not rooms_polys:
            return []

        rooms_polys.sort(key=lambda p: -p.area)
        labels = _bind_labels(rooms_polys, _room_label_words(page))

        rooms: List[RoomPolygon] = []
        for rank, (poly, (label, source)) in enumerate(
            zip(rooms_polys, labels), start=1
        ):
            rooms.append(
                RoomPolygon(
                    polygon_wkt=poly.wkt,
                    area_pt2=poly.area,
                    label=label,
                    label_source=source,
                    candidate_id="ROOM-%d" % rank,
                    confidence="high" if source == "text_in_polygon" else "medium",
                )
            )
        return rooms
    except Exception as exc:  # noqa: BLE001 — untrusted PDF must not crash
        logger.warning("Room extraction failed: %s", exc)
        return []


def building_footprint(
    rooms: Sequence,
    fpp: float,
    walls: Optional[Sequence] = None,
    page=None,
) -> dict:
    """Exterior footprint union with the overall-dims cross-check.

    Unions room faces with wall footprint ribbons (centerline buffered by
    half thickness) and fills the exterior ring — the exact-footprint
    replacement for the rectangular assumption. When *page* is given, the
    overall-dims footprint (``footprint_takeoff``) is computed on the same
    page and ``dims_crosscheck`` records the relative delta; > 2% (both
    methods are deterministic) flags ``needs_review`` — disagreement is
    surfaced, never silently resolved.
    """
    out: dict = {
        "area_sf": None,
        "perimeter_lf": None,
        "area_pt2": None,
        "perimeter_pt": None,
        "polygon_wkt": None,
        "dims_area_sf": None,
        "dims_crosscheck": None,
        "needs_review": False,
        "review_reason": "",
    }
    if not fpp or fpp <= 0:
        out["needs_review"] = True
        out["review_reason"] = "no solved scale (fpp)"
        return out
    try:
        from shapely import wkt as shapely_wkt

        geoms = []
        for room in rooms or []:
            try:
                poly = _valid_polygon(shapely_wkt.loads(room.polygon_wkt))
            except Exception:  # noqa: BLE001
                poly = None
            if poly is not None:
                geoms.append(poly)

        for wall in walls or []:
            pts = [
                (float(x), float(y))
                for x, y in getattr(wall, "centerline_pt", ()) or ()
                if math.isfinite(x) and math.isfinite(y)
            ]
            if len(pts) < 2:
                continue
            line = LineString(pts)
            half = max(float(getattr(wall, "thickness_pt", 0.0)) / 2.0, _EPS)
            if line.length > _EPS:
                try:
                    geoms.append(line.buffer(half, cap_style="square"))
                except (TypeError, ValueError):
                    geoms.append(line.buffer(half, cap_style=3))

        if not geoms:
            out["needs_review"] = True
            out["review_reason"] = "no rooms or walls to union"
            return out

        union = unary_union(geoms)
        if not union.is_valid:
            union = union.buffer(0)
        parts = (
            [g for g in getattr(union, "geoms", []) if isinstance(g, Polygon)]
            if not isinstance(union, Polygon)
            else [union]
        )
        parts = [p for p in parts if not p.is_empty]
        if not parts:
            out["needs_review"] = True
            out["review_reason"] = "footprint union is empty"
            return out

        # Exterior polygon union: fill interior holes/gaps, keep the largest
        # connected building envelope.
        filled = unary_union([Polygon(p.exterior) for p in parts])
        if isinstance(filled, Polygon):
            envelope = filled
        else:
            envelope = max(
                (g for g in filled.geoms if isinstance(g, Polygon)),
                key=lambda g: g.area,
            )
        envelope = _valid_polygon(envelope)
        if envelope is None:
            out["needs_review"] = True
            out["review_reason"] = "footprint envelope invalid"
            return out

        area_pt2 = envelope.area
        perimeter_pt = envelope.exterior.length
        out["area_pt2"] = round(area_pt2, 2)
        out["perimeter_pt"] = round(perimeter_pt, 2)
        out["area_sf"] = round(area_pt2 * fpp * fpp, 1)
        out["perimeter_lf"] = round(perimeter_pt * fpp, 1)
        out["polygon_wkt"] = envelope.wkt

        # Overall-dims cross-check (footprint_takeoff — the proven anchor).
        if page is not None:
            from bobbytailor.deterministic.footprint_takeoff import (
                footprint_from_page,
            )

            dims_fp = footprint_from_page(page)
            if dims_fp and dims_fp.area_sf and dims_fp.area_sf > 0:
                out["dims_area_sf"] = dims_fp.area_sf
                delta = abs(out["area_sf"] - dims_fp.area_sf) / dims_fp.area_sf
                out["dims_crosscheck"] = round(delta, 4)
                if delta > FOOTPRINT_AGREE_TOL:
                    out["needs_review"] = True
                    out["review_reason"] = "footprint methods disagree"
            else:
                out["needs_review"] = True
                out["review_reason"] = (
                    "overall-dims cross-check unavailable on this page"
                )
        return out
    except Exception as exc:  # noqa: BLE001 — untrusted PDF must not crash
        logger.warning("Footprint union failed: %s", exc)
        out["needs_review"] = True
        out["review_reason"] = "footprint computation failed"
        return out


def rooms_to_legend(rooms: Sequence, fpp: float) -> Optional[dict]:
    """Room areas as an authoritative takeoff legend (geometry provenance).

    Mirrors ``footprint_takeoff.footprint_to_legend`` output shape so room
    SF enters the pipeline as authoritative rows; ``_provenance:
    "geometry"`` marks the quantities as deterministic geometry math for
    merge logic and the reporter (vision-provenance quantities ≈ 0 on
    vector fixtures).
    """
    if not rooms or not fpp or fpp <= 0:
        return None
    rows: List[dict] = []
    confidences: List[str] = []
    for room in rooms:
        area_sf = round(room.area_pt2 * fpp * fpp, 1)
        if area_sf <= 0:
            continue
        item = room.label or room.candidate_id
        rows.append(
            {
                "ITEM": item,
                "DESCRIPTION": item,
                "QTY": str(area_sf),
                "QUANTITY": str(area_sf),
                "UNIT": "SF",
            }
        )
        confidences.append(room.confidence)
    if not rows:
        return None

    labeled = sum(1 for c in confidences if c == "high")
    note = (
        "Room floor areas measured deterministically from the wall-centerline "
        "polygon network (%d rooms, %d label-bound). Areas rescale exactly "
        "with any verified scale correction." % (len(rows), labeled)
    )
    return {
        "name": "Room Areas (measured from wall geometry)",
        "table_purpose": "takeoff_legend",
        # Machine-read off the plans — NOT a human input file, so it must
        # never publish as HUMAN INPUT (C4): measured from this plan's own wall geometry.
        "legend_origin": "plan_parsed",
        "schedule_type": "area",
        "use_for_takeoff": True,
        "description": note,
        "rows": rows,
        "_confidence": "high" if labeled == len(rows) else "medium",
        "_provenance": "geometry",
    }
