"""Symbol instance clustering (Recipe D) — deterministic EA counting.

Repeated CAD blocks (bollards, columns, fixtures, sprinkler heads) are
byte-identical geometry clusters repeated at translations, sometimes with
rotations/mirrors. This module enumerates every instance deterministically:

1. Harvest visible drawing primitives (lines, rects, quads, Béziers).
2. Collapse hatch fields first (Pitfall 2) so dense same-angle same-spacing
   stroke groups cannot poison clustering.
3. Connected components over a spatial grid hash — primitives whose endpoints
   are within ``ENDPOINT_EPS_PT`` belong to the same drawing cluster.
   Components are partitioned by path style class (stroke/fill/width): CAD
   blocks are drawn with consistent styling, while the connective wall/grid
   network is separate hairline stroke work. Without this partition, symbol
   blocks that touch walls (e.g. columns embedded in the perimeter) merge
   into one page-sized component and can never be enumerated.
4. Translation-normalized shape signature per cluster: a multiset of
   ``(item_type, quantized dx, dy, len, angle)`` tuples hashed over the
   8 dihedral transforms (min hash → rotation/mirror invariance).
5. Group clusters by signature → instance groups with exact counts.

The output is a *candidate registry*: each ``SymbolGroup`` carries a stable
``candidate_id`` plus every instance bbox in PDF points, so the fusion layer
can hand representative crops to vision for LABELING ONLY — the count is a
deterministic group size, never an eye-count. This is the fix for the
"Columns 90 vs 132" and "Bollards 0–17 vs 28" benchmark failures.
"""
from __future__ import annotations

import hashlib
import logging
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from bobbytailor.deterministic.dimensions import _visible_drawings

logger = logging.getLogger(__name__)

# ── Tuning constants (Recipe D) ───────────────────────────────────────────────

# Spatial grid hash cell for endpoint union (Recipe D step 1: cell ≈ 2–5 pt).
GRID_CELL_PT = 3.0
# Endpoints within this distance belong to the same drawing cluster.
ENDPOINT_EPS_PT = 1.0
# Signature quantization (Recipe D step 2: ~0.5 pt).
QUANT_PT = 0.5
QUANT_ANGLE_DEG = 1.0
# Coarse quantization used for near-duplicate signature merging.
COARSE_QUANT_PT = 1.0
COARSE_QUANT_ANGLE_DEG = 2.0
# Group filters (Recipe D step 3).
MIN_INSTANCES = 3
MIN_SYMBOL_FT = 0.5
MAX_SYMBOL_FT = 15.0
# A meaningful symbol block has at least two primitives; single-segment
# clusters are dashes/leader ticks, never countable symbols.
MIN_CLUSTER_PRIMITIVES = 2
# Resource-exhaustion cap (threat model): above this, return [] with warning.
MAX_PRIMITIVES = 200_000

# Hatch-field collapse (Pitfall 2).
HATCH_MIN_RUN = 8
HATCH_MAX_SPACING_PT = 6.0
HATCH_SPACING_TOL = 0.35          # max relative deviation from median spacing
HATCH_OFFSET_LEVEL_TOL = 0.25     # offsets within this collapse to one level

_EPS = 1e-9

# The 8 dihedral transforms as (a, b, c, d): x' = a·x + b·y, y' = c·x + d·y.
_DIHEDRAL = (
    (1, 0, 0, 1),     # identity
    (0, -1, 1, 0),    # rot 90
    (-1, 0, 0, -1),   # rot 180
    (0, 1, -1, 0),    # rot 270
    (-1, 0, 0, 1),    # mirror x
    (1, 0, 0, -1),    # mirror y
    (0, 1, 1, 0),     # mirror diag
    (0, -1, -1, 0),   # mirror anti-diag
)

Point = Tuple[float, float]
Segment = Tuple[float, float, float, float]


@dataclass
class SymbolGroup:
    """One group of geometrically identical symbol instances."""

    candidate_id: str
    count: int
    signature_hash: str
    instance_bboxes_pt: List[tuple]
    representative_bbox_pt: tuple
    bbox_size_ft: tuple
    contained_texts: List[str]
    confidence: str
    needs_review: bool
    text_subcounts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Primitive harvest ─────────────────────────────────────────────────────────


@dataclass
class _Primitive:
    kind: str            # "l" (line) or "c" (Bézier chord)
    e1: Point
    e2: Point
    style: int = 0       # path style class id (stroke/fill/width partition)


def _style_key(path) -> tuple:
    """Stable style class for a drawing path (stroke/fill/width)."""

    def _color(value):
        if value is None:
            return None
        try:
            return tuple(round(float(ch), 3) for ch in value)
        except TypeError:
            return str(value)

    width = path.get("width")
    return (
        path.get("type"),
        _color(path.get("stroke") or path.get("color")),
        _color(path.get("fill")),
        round(float(width), 2) if width is not None else None,
    )


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


def _harvest_primitives(drawings) -> List[_Primitive]:
    """Flatten drawing paths into style-classed line/curve primitives."""
    prims: List[_Primitive] = []
    style_ids: Dict[tuple, int] = {}
    for path in drawings:
        style = style_ids.setdefault(_style_key(path), len(style_ids))
        for it in path.get("items", []):
            op = it[0]
            if op == "l":
                a, b = it[1], it[2]
                prims.append(_Primitive("l", (a.x, a.y), (b.x, b.y), style))
            elif op == "re":
                for x0, y0, x1, y1 in _rect_edges(it[1]):
                    prims.append(_Primitive("l", (x0, y0), (x1, y1), style))
            elif op == "qu":
                try:
                    edges = _quad_edges(it[1])
                except AttributeError:
                    continue
                for x0, y0, x1, y1 in edges:
                    prims.append(_Primitive("l", (x0, y0), (x1, y1), style))
            elif op == "c":
                p1, p4 = it[1], it[4]
                prims.append(_Primitive("c", (p1.x, p1.y), (p4.x, p4.y), style))
    return prims


# ── Hatch-field collapse (Pitfall 2) ─────────────────────────────────────────


def _seg_len(s: Segment) -> float:
    return math.hypot(s[2] - s[0], s[3] - s[1])


def _collapse_hatch_fields(
    segments: Sequence[Segment],
) -> Tuple[List[Segment], List[dict]]:
    """Collapse dense same-angle same-spacing segment groups (hatch fields).

    Hatched regions explode into thousands of tiny parallel segments that
    dominate primitive counts and would otherwise form enormous bogus
    "symbol groups". Detect evenly spaced parallel runs and drop their
    members, keeping one hatch-region record per run (boundary geometry is
    untouched — it lies at other angles and survives naturally).

    Returns ``(kept_segments, hatch_regions)`` where each region is
    ``{"bbox_pt", "angle_deg", "spacing_pt", "count"}`` for downstream
    hatch-class labeling (CMU hatch vs concrete hatch is a vision signal).
    """
    drop, regions = _hatch_drop_indices(segments)
    kept = [s for i, s in enumerate(segments) if i not in drop]
    return kept, regions


def _hatch_drop_indices(
    segments: Sequence[Segment],
) -> Tuple[set, List[dict]]:
    """Indices of hatch-field member segments plus the region records."""
    by_angle: Dict[int, List[int]] = defaultdict(list)
    for idx, seg in enumerate(segments):
        if _seg_len(seg) < _EPS:
            continue
        angle = math.degrees(math.atan2(seg[3] - seg[1], seg[2] - seg[0])) % 180.0
        by_angle[int(round(angle / QUANT_ANGLE_DEG)) % 180].append(idx)

    drop: set = set()
    regions: List[dict] = []

    for angle_q, idxs in by_angle.items():
        if len(idxs) < HATCH_MIN_RUN:
            continue
        theta = math.radians(angle_q * QUANT_ANGLE_DEG)
        ux, uy = math.cos(theta), math.sin(theta)
        nx, ny = -uy, ux

        # Project midpoints on the normal axis; group into offset levels.
        entries = []
        for idx in idxs:
            s = segments[idx]
            mx, my = (s[0] + s[2]) / 2.0, (s[1] + s[3]) / 2.0
            off = mx * nx + my * ny
            t0 = s[0] * ux + s[1] * uy
            t1 = s[2] * ux + s[3] * uy
            entries.append((off, min(t0, t1), max(t0, t1), idx))
        entries.sort(key=lambda e: e[0])

        levels: List[List[tuple]] = []
        for entry in entries:
            if levels and entry[0] - levels[-1][0][0] <= HATCH_OFFSET_LEVEL_TOL:
                levels[-1].append(entry)
            else:
                levels.append([entry])

        # Walk offset levels; runs of consistent small gaps are hatch fields.
        run: List[List[tuple]] = [levels[0]] if levels else []
        for lvl in levels[1:]:
            gap = lvl[0][0] - run[-1][0][0]
            if HATCH_OFFSET_LEVEL_TOL < gap <= HATCH_MAX_SPACING_PT:
                run.append(lvl)
            else:
                _flush_hatch_run(run, segments, angle_q, drop, regions)
                run = [lvl]
        _flush_hatch_run(run, segments, angle_q, drop, regions)

    return drop, regions


def _flush_hatch_run(
    run: List[List[tuple]],
    segments: Sequence[Segment],
    angle_q: int,
    drop: set,
    regions: List[dict],
) -> None:
    """Validate a candidate hatch run; on success drop members, record region."""
    if len(run) < HATCH_MIN_RUN:
        return

    gaps = [run[i + 1][0][0] - run[i][0][0] for i in range(len(run) - 1)]
    gaps = [g for g in gaps if g > _EPS]
    if not gaps:
        return
    gaps_sorted = sorted(gaps)
    median_gap = gaps_sorted[len(gaps_sorted) // 2]
    if median_gap <= _EPS or median_gap > HATCH_MAX_SPACING_PT:
        return
    if any(abs(g - median_gap) > HATCH_SPACING_TOL * median_gap for g in gaps):
        return

    # Consecutive strokes must overlap along the direction axis (a hatch is a
    # laterally contiguous band; symbol rows at matching spacing are not).
    for i in range(len(run) - 1):
        lo_a = min(e[1] for e in run[i])
        hi_a = max(e[2] for e in run[i])
        lo_b = min(e[1] for e in run[i + 1])
        hi_b = max(e[2] for e in run[i + 1])
        if min(hi_a, hi_b) - max(lo_a, lo_b) < -_EPS:
            return

    member_idxs = [e[3] for lvl in run for e in lvl]
    xs: List[float] = []
    ys: List[float] = []
    for idx in member_idxs:
        s = segments[idx]
        xs.extend((s[0], s[2]))
        ys.extend((s[1], s[3]))
    drop.update(member_idxs)
    regions.append(
        {
            "bbox_pt": (min(xs), min(ys), max(xs), max(ys)),
            "angle_deg": angle_q * QUANT_ANGLE_DEG,
            "spacing_pt": round(median_gap, 3),
            "count": len(member_idxs),
        }
    )


# ── Connected components over a spatial grid hash ────────────────────────────


class _UnionFind:
    __slots__ = ("parent", "rank")

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        parent = self.parent
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _connected_components(prims: Sequence[_Primitive]) -> List[List[int]]:
    """Union primitives whose endpoints are within ``ENDPOINT_EPS_PT``.

    The union is partitioned by style class: symbol blocks keep their own
    styling, while walls/gridlines are the page-wide hairline network. All
    bucket keys carry the style id so endpoints of different styles never
    compare, keeping the whole pass near O(n).
    """
    uf = _UnionFind(len(prims))

    # Stage 1: exact-bucket dedupe — endpoints sharing a fine bucket union in
    # O(n) and collapse to one representative entry, so dense coincident
    # endpoints never trigger quadratic in-cell comparisons.
    fine: Dict[Tuple[int, int, int], Tuple[float, float, int]] = {}
    unique_pts: List[Tuple[float, float, int, int]] = []
    inv = 1.0 / QUANT_PT
    for idx, prim in enumerate(prims):
        for x, y in (prim.e1, prim.e2):
            key = (prim.style, int(round(x * inv)), int(round(y * inv)))
            hit = fine.get(key)
            if hit is None:
                fine[key] = (x, y, idx)
                unique_pts.append((x, y, idx, prim.style))
            else:
                uf.union(hit[2], idx)

    # Stage 2: grid hash over unique points; union near-neighbors (≤ eps).
    grid: Dict[Tuple[int, int, int], List[Tuple[float, float, int]]] = defaultdict(list)
    for x, y, idx, style in unique_pts:
        grid[(style, int(x // GRID_CELL_PT), int(y // GRID_CELL_PT))].append((x, y, idx))

    eps2 = ENDPOINT_EPS_PT * ENDPOINT_EPS_PT
    for (style, cx, cy), pts in grid.items():
        neighborhood = list(pts)
        for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
            neighborhood.extend(grid.get((style, cx + dx, cy + dy), ()))
        n = len(neighborhood)
        for i in range(len(pts)):
            xi, yi, pi = pts[i]
            for j in range(i + 1, n):
                xj, yj, pj = neighborhood[j]
                if (xi - xj) ** 2 + (yi - yj) ** 2 <= eps2:
                    uf.union(pi, pj)

    comps: Dict[int, List[int]] = defaultdict(list)
    for idx in range(len(prims)):
        comps[uf.find(idx)].append(idx)
    return list(comps.values())


# ── Shape signature (translation-normalized, dihedral-invariant) ─────────────


def _cluster_centroid(prims: Sequence[_Primitive]) -> Point:
    sx = sy = 0.0
    for p in prims:
        sx += (p.e1[0] + p.e2[0]) / 2.0
        sy += (p.e1[1] + p.e2[1]) / 2.0
    n = max(len(prims), 1)
    return (sx / n, sy / n)


def _signature_tuples(
    prims: Sequence[_Primitive],
    centroid: Point,
    transform: Tuple[int, int, int, int],
    quant_pt: float,
    quant_angle: float,
) -> List[tuple]:
    """Quantized tuple multiset for one dihedral transform."""
    a, b, c, d = transform
    cx, cy = centroid
    out: List[tuple] = []
    for p in prims:
        x1, y1 = p.e1[0] - cx, p.e1[1] - cy
        x2, y2 = p.e2[0] - cx, p.e2[1] - cy
        t1 = (a * x1 + b * y1, c * x1 + d * y1)
        t2 = (a * x2 + b * y2, c * x2 + d * y2)
        lo, hi = (t1, t2) if t1 <= t2 else (t2, t1)
        mx, my = (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0
        dx, dy = hi[0] - lo[0], hi[1] - lo[1]
        length = math.hypot(dx, dy)
        angle = math.degrees(math.atan2(dy, dx)) % 180.0
        out.append(
            (
                p.kind,
                int(round(mx / quant_pt)),
                int(round(my / quant_pt)),
                int(round(length / quant_pt)),
                int(round(angle / quant_angle)) % int(round(180 / quant_angle)),
            )
        )
    out.sort()
    return out


def _shape_signature(
    prims: Sequence[_Primitive],
    *,
    quant_pt: float = QUANT_PT,
    quant_angle: float = QUANT_ANGLE_DEG,
) -> str:
    """Min hash over the 8 dihedral transforms → rotation/mirror invariance."""
    centroid = _cluster_centroid(prims)
    best: Optional[str] = None
    for transform in _DIHEDRAL:
        tuples = _signature_tuples(prims, centroid, transform, quant_pt, quant_angle)
        digest = hashlib.sha1(repr(tuples).encode("utf-8")).hexdigest()[:16]
        if best is None or digest < best:
            best = digest
    return best or ""


# ── Cluster records and grouping ──────────────────────────────────────────────


@dataclass
class _Cluster:
    prims: List[_Primitive]
    bbox: Tuple[float, float, float, float]
    kind_counts: Tuple[tuple, ...]
    signature: str = ""
    coarse_signature: str = ""


def _cluster_bbox(prims: Sequence[_Primitive]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for p in prims:
        xs.extend((p.e1[0], p.e2[0]))
        ys.extend((p.e1[1], p.e2[1]))
    return (min(xs), min(ys), max(xs), max(ys))


def _center_in_rects(
    bbox: Tuple[float, float, float, float],
    rects: Optional[Sequence],
) -> bool:
    if not rects:
        return False
    cx, cy = (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    for rect in rects:
        try:
            x0, y0, x1, y1 = rect
        except (TypeError, ValueError):
            continue
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return True
    return False


def _page_words(page) -> List[tuple]:
    try:
        return page.get_text("words") or []
    except Exception:  # noqa: BLE001
        return []


def _texts_in_bbox(
    bbox: Tuple[float, float, float, float],
    words: Sequence[tuple],
    pad: float = 0.5,
) -> List[str]:
    x0, y0, x1, y1 = bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad
    hits = []
    for w in words:
        wx, wy = (w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0
        if x0 <= wx <= x1 and y0 <= wy <= y1:
            hits.append((w[1], w[0], str(w[4])))
    hits.sort()
    return [h[2] for h in hits]


def cluster_symbols(
    page,
    fpp: float,
    exclude_rects: Optional[Sequence] = None,
    *,
    doc=None,
    page_index: int = 0,
) -> List[SymbolGroup]:
    """Run the full Recipe D pipeline on one page.

    ``fpp`` is feet-per-point from the scale solver; it parameterizes the
    plausible-symbol size filter (0.5–15 ft). ``exclude_rects`` masks
    schedule/legend/title-block regions (PDF-point rects) out of clustering.
    """
    try:
        if doc is None:
            doc = page.parent

        drawings = _visible_drawings(page, doc)
        prims = _harvest_primitives(drawings)
        if len(prims) > MAX_PRIMITIVES:
            logger.warning(
                "Symbol clustering: page %d has %d primitives (> %d); skipping",
                page_index,
                len(prims),
                MAX_PRIMITIVES,
            )
            return []
        if not prims:
            return []

        # Pitfall 2: collapse hatch fields BEFORE clustering (style-preserving).
        line_idx = [i for i, p in enumerate(prims) if p.kind == "l"]
        line_segs = [
            (prims[i].e1[0], prims[i].e1[1], prims[i].e2[0], prims[i].e2[1])
            for i in line_idx
        ]
        drop_local, hatch_regions = _hatch_drop_indices(line_segs)
        if hatch_regions:
            logger.info(
                "Symbol clustering: page %d collapsed %d hatch region(s)",
                page_index,
                len(hatch_regions),
            )
            drop_global = {line_idx[k] for k in drop_local}
            prims = [p for i, p in enumerate(prims) if i not in drop_global]
        if not prims:
            return []

        components = _connected_components(prims)

        # Size/exclusion filters before the (more expensive) signature step.
        clusters: List[_Cluster] = []
        for comp in components:
            if len(comp) < MIN_CLUSTER_PRIMITIVES:
                continue
            cprims = [prims[i] for i in comp]
            bbox = _cluster_bbox(cprims)
            if fpp and fpp > 0:
                size_ft = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * fpp
                if not (MIN_SYMBOL_FT - _EPS <= size_ft <= MAX_SYMBOL_FT + _EPS):
                    continue
            if _center_in_rects(bbox, exclude_rects):
                continue
            kind_counts = tuple(sorted(Counter(p.kind for p in cprims).items()))
            clusters.append(_Cluster(cprims, bbox, kind_counts))

        if not clusters:
            return []

        for cl in clusters:
            cl.signature = _shape_signature(cl.prims)
            cl.coarse_signature = _shape_signature(
                cl.prims,
                quant_pt=COARSE_QUANT_PT,
                quant_angle=COARSE_QUANT_ANGLE_DEG,
            )

        # Group by fine signature, then merge near-duplicates: fine groups
        # sharing a coarse signature AND primitive-kind counts collapse into
        # one group (signature-distance tolerance per Recipe D caveats).
        fine_groups: Dict[str, List[_Cluster]] = defaultdict(list)
        for cl in clusters:
            fine_groups[cl.signature].append(cl)

        merged: Dict[tuple, List[_Cluster]] = defaultdict(list)
        for sig, members in fine_groups.items():
            key = (members[0].coarse_signature, members[0].kind_counts, len(members[0].prims))
            merged[key].extend(members)

        words = _page_words(page)
        groups: List[SymbolGroup] = []
        for key, members in merged.items():
            if len(members) < MIN_INSTANCES:
                continue
            members.sort(key=lambda c: (c.bbox[1], c.bbox[0]))
            bboxes = [tuple(round(v, 3) for v in c.bbox) for c in members]

            # Split-by-text support (Kreo "Split by Text"): differing text
            # tags across instances → needs_review + per-text subcounts.
            instance_tags = []
            for c in members:
                tag = " ".join(_texts_in_bbox(c.bbox, words))
                instance_tags.append(tag)
            distinct = sorted({t for t in instance_tags if t})
            needs_review = len(distinct) > 1
            subcounts: Dict[str, int] = {}
            if needs_review:
                counter = Counter(t if t else "(no text)" for t in instance_tags)
                subcounts = dict(sorted(counter.items()))

            rep = bboxes[0]
            width_ft = round((rep[2] - rep[0]) * fpp, 3) if fpp and fpp > 0 else 0.0
            height_ft = round((rep[3] - rep[1]) * fpp, 3) if fpp and fpp > 0 else 0.0
            # Fine-signature hash of the dominant sub-group is the stable id.
            dominant_sig = Counter(c.signature for c in members).most_common(1)[0][0]
            groups.append(
                SymbolGroup(
                    candidate_id="",
                    count=len(members),
                    signature_hash=dominant_sig,
                    instance_bboxes_pt=bboxes,
                    representative_bbox_pt=rep,
                    bbox_size_ft=(width_ft, height_ft),
                    contained_texts=distinct,
                    confidence="medium" if needs_review else "high",
                    needs_review=needs_review,
                    text_subcounts=subcounts,
                )
            )

        groups.sort(key=lambda g: (-g.count, g.signature_hash))
        for n, group in enumerate(groups, start=1):
            group.candidate_id = f"SYM-{n}"
        return groups
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Symbol clustering failed on page %d: %s",
            page_index,
            exc,
        )
        return []
