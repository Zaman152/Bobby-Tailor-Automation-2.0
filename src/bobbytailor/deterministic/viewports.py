"""Viewport segmentation (V3-ACC-02) — split a sheet into drawing regions.

A plan sheet is a composite: the main plan, detail callouts, a title block,
legends and schedule tables. Scale is only meaningful *per viewport*, so the
zero-calibration scale solver (``scale_solver``) needs each sheet segmented
into regions before any consensus solve.

Detection signal cascade (RESEARCH §2, priority order):

1. **Clip rectangles** — ``page.get_drawings(extended=True)`` exposes the clip
   hierarchy. CAD exporters often clip each viewport; when >= 2 substantial
   clip rects exist (each > 5% of page area) they are authoritative
   (``detection_method="clip_rect"``).
2. **Title-text anchors** — detail titles follow the "N / TITLE / SCALE: x"
   pattern under a drawing; ``extract_scale_callouts`` yields positioned
   anchors. A viewport is the geometry mass bound to its anchor, bounded by
   whitespace gutters (``detection_method="title_anchor"``).
3. **Density gutters** — segment density projected onto the x/y axes;
   low-density bands (< 5% of median density, >= 20pt wide) split regions
   (``detection_method="density_gutter"``).
4. **Fallback** — nearest-anchor bucketing equivalent to the historical
   ``geometry_takeoff._measure_viewports`` behavior, or the whole page as a
   single 'unknown' region (``detection_method="fallback"``).

The title block (bottom/right strip of dense small text) is always classified
and masked; caller-supplied ``table_bboxes`` (from ``tables.py``) are marked
``kind='schedule'`` so schedule/legend geometry never contaminates
measurement. Every page returns >= 1 viewport.

Coordinate space: PyMuPDF text extraction and ``get_drawings`` both report
coordinates in the UNROTATED page space, so all bboxes here are unrotated
PDF points (consistent with ``dimensions.DimensionSample``).
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Tier-1 clip-rect gates.
CLIP_MIN_PAGE_SHARE = 0.05    # substantial: > 5% of page area
CLIP_MAX_PAGE_SHARE = 0.90    # page-covering clips are not viewports
CLIP_DEDUPE_IOU = 0.85

# Tier-3 density-gutter gates (RESEARCH §2 signal 3).
GUTTER_BIN_PT = 8.0
GUTTER_MIN_WIDTH_PT = 20.0
GUTTER_DENSITY_FRACTION = 0.05   # < 5% of median bin density
GUTTER_EDGE_MARGIN = 0.05        # ignore cuts within 5% of the range ends

# Title-block detection.
TITLE_BLOCK_MAX_SHARE = 0.32     # strip must be <= 32% of the page dimension
TITLE_BLOCK_MIN_WORDS = 15
TITLE_BOUNDARY_MIN_SPAN = 0.55   # boundary segment spans >= 55% of the edge

# Region hygiene.
MIN_REGION_SEGMENTS = 12
BBOX_TRIM_FRACTION = 0.01        # percentile trim on segment endpoints
BBOX_PAD_PT = 6.0
CLAIM_MAX_DIST_PT = 300.0        # leftover segments join a region within this
WORD_LINE_GAP_PT = 60.0          # column split inside a text line bucket

# Detail classification: printed scales below this are detail scales
# (1/4" = 1'-0" is fpi 4 — anything smaller is a blow-up detail).
DETAIL_MAX_FPI = 4.0

_TITLEISH_RE = re.compile(
    r"\b(PLAN|ELEVATION|SECTION|DETAIL|SCHEDULE|LEGEND|SCALE)\b", re.IGNORECASE
)
_DETAILISH_RE = re.compile(r"\b(DETAIL|SECTION)\b", re.IGNORECASE)


@dataclass
class Viewport:
    """One segmented sheet region with detection provenance."""

    region_id: str            # "R1", "R2", ... assigned by area desc
    bbox_pt: tuple            # (x0, y0, x1, y1) unrotated PDF points
    kind: str                 # main_plan|detail|title_block|legend|schedule|unknown
    detection_method: str     # clip_rect|title_anchor|density_gutter|fallback
    title_text: str = ""
    printed_fpi: Optional[float] = None  # local scale callout bound to region
    segment_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ── Geometry harvest ──────────────────────────────────────────────────────────


def _drawings_extended(page) -> list:
    """Page drawings with the clip hierarchy (``extended=True``), best effort."""
    try:
        return page.get_drawings(extended=True)
    except Exception:  # noqa: BLE001 — older PyMuPDF / defective page
        try:
            return page.get_drawings()
        except Exception:  # noqa: BLE001
            return []


def _visible_paths(page, doc) -> list:
    """Extended drawings excluding paths on hidden optional-content layers."""
    from bobbytailor.deterministic.dimensions import _hidden_ocg_layers

    drawings = _drawings_extended(page)
    hidden = _hidden_ocg_layers(doc) if doc is not None else set()
    if not hidden:
        return drawings
    out = []
    for path in drawings:
        layer = path.get("layer") or ""
        if layer and layer in hidden:
            continue
        out.append(path)
    return out


def _segments_from_paths(paths) -> List[Tuple[float, float, float, float]]:
    """Straight segments from drawing paths, skipping clip/group entries."""
    out: List[Tuple[float, float, float, float]] = []
    for path in paths:
        if path.get("type") in ("clip", "group"):
            continue
        for it in path.get("items") or []:
            if it[0] == "l":
                a, b = it[1], it[2]
                out.append((a.x, a.y, b.x, b.y))
            elif it[0] == "re":
                r = it[1]
                out.extend(
                    [
                        (r.x0, r.y0, r.x1, r.y0),
                        (r.x1, r.y0, r.x1, r.y1),
                        (r.x1, r.y1, r.x0, r.y1),
                        (r.x0, r.y1, r.x0, r.y0),
                    ]
                )
    return out


def _seg_mid(seg) -> Tuple[float, float]:
    return ((seg[0] + seg[2]) / 2.0, (seg[1] + seg[3]) / 2.0)


def _page_dims(page) -> Tuple[float, float]:
    """Unrotated content-space width/height (text/drawings coordinate space)."""
    try:
        rect = page.rect
        if getattr(page, "rotation", 0) in (90, 270):
            return float(rect.height), float(rect.width)
        return float(rect.width), float(rect.height)
    except Exception:  # noqa: BLE001
        return 0.0, 0.0


def _point_in_bbox(pt: Tuple[float, float], bbox, margin: float = 0.0) -> bool:
    x, y = pt
    return (
        bbox[0] - margin <= x <= bbox[2] + margin
        and bbox[1] - margin <= y <= bbox[3] + margin
    )


def _bbox_area(bbox) -> float:
    return max(0.0, bbox[2] - bbox[0]) * max(0.0, bbox[3] - bbox[1])


def _bbox_iou(a, b) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = _bbox_area(a) + _bbox_area(b) - inter
    return inter / union if union > 0 else 0.0


def _trimmed_bbox(
    segments: Sequence[Tuple[float, float, float, float]],
    trim: float = BBOX_TRIM_FRACTION,
    pad: float = BBOX_PAD_PT,
) -> Optional[tuple]:
    """Percentile-trimmed bbox of segment endpoints (resists stray outliers)."""
    if not segments:
        return None
    xs = sorted([s[0] for s in segments] + [s[2] for s in segments])
    ys = sorted([s[1] for s in segments] + [s[3] for s in segments])
    n = len(xs)
    lo = min(n - 1, max(0, int(n * trim)))
    hi = max(0, min(n - 1, int(n * (1.0 - trim))))
    return (xs[lo] - pad, ys[lo] - pad, xs[hi] + pad, ys[hi] + pad)


# ── Words / title text ────────────────────────────────────────────────────────


def _page_words(page) -> list:
    try:
        return page.get_text("words") or []
    except Exception:  # noqa: BLE001
        return []


def _word_lines(words: list, rotated: bool) -> List[Tuple[tuple, str]]:
    """Group words into rough text lines -> [(line_bbox, text)].

    On rotated pages (rotation 90/270) visual text lines are stacked along
    the unrotated y axis at near-constant x, so grouping flips axes. Buckets
    are additionally split at large reading-axis gaps so words from separate
    columns at the same line position never merge into one title.
    """
    if not words:
        return []
    if rotated:
        keyed = sorted(words, key=lambda w: ((w[0] + w[2]) / 2.0, w[1]))
    else:
        keyed = sorted(words, key=lambda w: ((w[1] + w[3]) / 2.0, w[0]))

    lines: List[Tuple[tuple, str]] = []
    bucket: list = []

    def _flush() -> None:
        if not bucket:
            return
        # Split the bucket at large gaps along the reading axis (columns).
        ordered = sorted(bucket, key=lambda w: w[1] if rotated else w[0])
        runs: List[list] = [[ordered[0]]]
        for w in ordered[1:]:
            prev = runs[-1][-1]
            gap = (w[1] - prev[3]) if rotated else (w[0] - prev[2])
            if gap > WORD_LINE_GAP_PT:
                runs.append([w])
            else:
                runs[-1].append(w)
        for run in runs:
            x0 = min(w[0] for w in run)
            y0 = min(w[1] for w in run)
            x1 = max(w[2] for w in run)
            y1 = max(w[3] for w in run)
            lines.append(((x0, y0, x1, y1), " ".join(w[4] for w in run)))

    prev_key = None
    for w in keyed:
        key = (w[0] + w[2]) / 2.0 if rotated else (w[1] + w[3]) / 2.0
        if prev_key is not None and abs(key - prev_key) > 7.0:
            _flush()
            bucket = []
        bucket.append(w)
        prev_key = key
    _flush()
    return lines


def _titleish_text_in_bbox(lines: List[Tuple[tuple, str]], bbox) -> str:
    """Concatenate title-ish text lines inside (or, failing that, near) a bbox.

    Two-pass: lines whose center falls inside the region are preferred; when
    none exist the search widens slightly, because viewport titles ("N / TITLE
    / SCALE: x") conventionally sit just OUTSIDE the drawing's clip bounds.
    """
    for margin in (10.0, 45.0):
        hits: List[str] = []
        for lb, text in lines:
            cx, cy = (lb[0] + lb[2]) / 2.0, (lb[1] + lb[3]) / 2.0
            if not _point_in_bbox((cx, cy), bbox, margin=margin):
                continue
            if _TITLEISH_RE.search(text):
                hits.append(text.strip())
            if len(hits) >= 3:
                break
        if hits:
            return " / ".join(hits)
    return ""


# ── Title block detection ─────────────────────────────────────────────────────


def _detect_title_block(
    segments: Sequence[Tuple[float, float, float, float]],
    words: list,
    width: float,
    height: float,
) -> Optional[tuple]:
    """Locate the title block strip: a boundary line near an edge with dense text.

    Checks all four edges (rotation-agnostic — the visual bottom/right strip
    may map to any unrotated edge). A candidate boundary is a long segment
    parallel to the edge in the outer band; the strip beyond it must contain
    enough words. The densest qualifying strip wins.
    """
    if width <= 0 or height <= 0 or not segments:
        return None

    best: Optional[tuple] = None
    best_density = 0.0

    # (edge, axis) -> axis 0 = boundary is vertical (x = const), 1 = horizontal.
    edges = [
        ("right", 0), ("left", 0),
        ("bottom", 1), ("top", 1),
    ]
    for edge, axis in edges:
        span_dim = height if axis == 0 else width      # boundary segment length
        perp_dim = width if axis == 0 else height      # strip thickness base
        candidates: List[float] = []
        for s in segments:
            if axis == 0:
                if abs(s[0] - s[2]) > 2.0:  # not vertical
                    continue
                length = abs(s[3] - s[1])
                pos = (s[0] + s[2]) / 2.0
            else:
                if abs(s[1] - s[3]) > 2.0:  # not horizontal
                    continue
                length = abs(s[2] - s[0])
                pos = (s[1] + s[3]) / 2.0
            if length < TITLE_BOUNDARY_MIN_SPAN * span_dim:
                continue
            outer = perp_dim * TITLE_BLOCK_MAX_SHARE
            if edge in ("right", "bottom") and pos < perp_dim - outer:
                continue
            if edge in ("left", "top") and pos > outer:
                continue
            candidates.append(pos)

        for pos in candidates:
            if edge == "right":
                strip = (pos, 0.0, width, height)
            elif edge == "left":
                strip = (0.0, 0.0, pos, height)
            elif edge == "bottom":
                strip = (0.0, pos, width, height)
            else:
                strip = (0.0, 0.0, width, pos)
            area = _bbox_area(strip)
            if area <= 0 or area > TITLE_BLOCK_MAX_SHARE * width * height:
                continue
            n_words = sum(
                1
                for w in words
                if _point_in_bbox(((w[0] + w[2]) / 2.0, (w[1] + w[3]) / 2.0), strip)
            )
            if n_words < TITLE_BLOCK_MIN_WORDS:
                continue
            density = n_words / area
            if density > best_density:
                best_density = density
                best = strip
    return best


# ── Tier 1: clip rectangles ───────────────────────────────────────────────────


def _substantial_clip_rects(paths, page_area: float) -> List[tuple]:
    """Deduplicated substantial clip scissor rects (> 5%, < 90% page area)."""
    rects: List[tuple] = []
    for path in paths:
        if path.get("type") != "clip":
            continue
        scissor = path.get("scissor")
        if scissor is None:
            continue
        bbox = (
            min(scissor.x0, scissor.x1),
            min(scissor.y0, scissor.y1),
            max(scissor.x0, scissor.x1),
            max(scissor.y0, scissor.y1),
        )
        share = _bbox_area(bbox) / page_area if page_area else 0.0
        if not (CLIP_MIN_PAGE_SHARE < share <= CLIP_MAX_PAGE_SHARE):
            continue
        if any(_bbox_iou(bbox, kept) >= CLIP_DEDUPE_IOU for kept in rects):
            continue
        rects.append(bbox)
    # Deterministic: area desc, then position.
    rects.sort(key=lambda b: (-_bbox_area(b), b[0], b[1]))
    return rects


# ── Tier 3: density gutters ───────────────────────────────────────────────────


def _axis_gutters(
    segments: Sequence[Tuple[float, float, float, float]],
    lo: float,
    hi: float,
    axis: int,
) -> List[float]:
    """Low-density band centers along *axis* (0=x, 1=y) splitting [lo, hi]."""
    span = hi - lo
    if span < 4 * GUTTER_MIN_WIDTH_PT or not segments:
        return []
    n_bins = max(4, int(span / GUTTER_BIN_PT))
    bins = [0.0] * n_bins

    for s in segments:
        a = s[0] if axis == 0 else s[1]
        b = s[2] if axis == 0 else s[3]
        s0, s1 = (a, b) if a <= b else (b, a)
        i0 = int((max(s0, lo) - lo) / span * n_bins)
        i1 = int((min(s1, hi) - lo) / span * n_bins)
        i0 = min(n_bins - 1, max(0, i0))
        i1 = min(n_bins - 1, max(0, i1))
        for i in range(i0, i1 + 1):
            bins[i] += 1.0

    occupied = sorted(v for v in bins if v > 0)
    if not occupied:
        return []
    median_density = occupied[len(occupied) // 2]
    threshold = median_density * GUTTER_DENSITY_FRACTION

    cuts: List[float] = []
    band_start: Optional[int] = None
    for i, v in enumerate(bins + [median_density]):  # sentinel closes last band
        if v <= threshold:
            if band_start is None:
                band_start = i
            continue
        if band_start is not None:
            band_w = (i - band_start) * (span / n_bins)
            if band_w >= GUTTER_MIN_WIDTH_PT:
                center = lo + (band_start + (i - band_start) / 2.0) * (span / n_bins)
                if lo + GUTTER_EDGE_MARGIN * span < center < hi - GUTTER_EDGE_MARGIN * span:
                    cuts.append(center)
            band_start = None
    return cuts


def _gutter_cells(
    segments: Sequence[Tuple[float, float, float, float]],
    content_bbox: tuple,
) -> List[List[Tuple[float, float, float, float]]]:
    """Split segments into cells via y-gutters, then x-gutters per band."""
    x0, y0, x1, y1 = content_bbox
    y_cuts = _axis_gutters(segments, y0, y1, axis=1)
    y_bounds = [y0] + sorted(y_cuts) + [y1]

    cells: List[List[Tuple[float, float, float, float]]] = []
    for yi in range(len(y_bounds) - 1):
        b0, b1 = y_bounds[yi], y_bounds[yi + 1]
        band = [s for s in segments if b0 <= _seg_mid(s)[1] < b1]
        if not band:
            continue
        x_cuts = _axis_gutters(band, x0, x1, axis=0)
        x_bounds = [x0] + sorted(x_cuts) + [x1]
        for xi in range(len(x_bounds) - 1):
            c0, c1 = x_bounds[xi], x_bounds[xi + 1]
            cell = [s for s in band if c0 <= _seg_mid(s)[0] < c1]
            if len(cell) >= MIN_REGION_SEGMENTS:
                cells.append(cell)
    return cells


# ── Tier 2/4 helper: nearest-anchor bucketing ────────────────────────────────


def _bucket_by_anchor(
    segments: Sequence[Tuple[float, float, float, float]],
    anchors: Sequence[dict],
) -> List[List[Tuple[float, float, float, float]]]:
    """Nearest-anchor segment bucketing (the historical fallback behavior)."""
    buckets: List[List[Tuple[float, float, float, float]]] = [[] for _ in anchors]
    for s in segments:
        mx, my = _seg_mid(s)
        best_i, best_d = 0, float("inf")
        for i, a in enumerate(anchors):
            d = (mx - a["x"]) ** 2 + (my - a["y"]) ** 2
            if d < best_d:
                best_d, best_i = d, i
        buckets[best_i].append(s)
    return buckets


# ── Public API ───────────────────────────────────────────────────────────────


def segment_viewports(page, table_bboxes: Optional[Sequence] = None) -> List[Viewport]:
    """Segment *page* into viewports via the four-tier detection cascade.

    ``table_bboxes`` (from ``tables.py`` output) are marked ``kind='schedule'``
    and masked from all drawing regions. Every page returns >= 1 viewport
    (whole page as 'unknown' when nothing is detected).
    """
    try:
        return _segment_viewports_inner(page, table_bboxes)
    except Exception as exc:  # noqa: BLE001 — untrusted PDFs must not crash
        logger.warning("Viewport segmentation failed: %s", exc)
        width, height = _page_dims(page)
        return [
            Viewport(
                region_id="R1",
                bbox_pt=(0.0, 0.0, width or 1.0, height or 1.0),
                kind="unknown",
                detection_method="fallback",
            )
        ]


def _segment_viewports_inner(page, table_bboxes: Optional[Sequence]) -> List[Viewport]:
    from bobbytailor.deterministic.scale_extraction import extract_scale_callouts

    doc = getattr(page, "parent", None)
    width, height = _page_dims(page)
    page_area = width * height
    paths = _visible_paths(page, doc)
    segments = _segments_from_paths(paths)
    words = _page_words(page)
    rotated = getattr(page, "rotation", 0) in (90, 270)
    lines = _word_lines(words, rotated)

    # ── Masks: title block + schedule/legend tables ──────────────────────────
    masks: List[Viewport] = []
    title_bbox = _detect_title_block(segments, words, width, height)
    if title_bbox is not None:
        masks.append(
            Viewport(
                region_id="",  # assigned later
                bbox_pt=title_bbox,
                kind="title_block",
                detection_method="density_gutter",
            )
        )
    for tb in table_bboxes or []:
        try:
            bbox = (float(tb[0]), float(tb[1]), float(tb[2]), float(tb[3]))
        except (TypeError, ValueError, IndexError):
            continue
        if _bbox_area(bbox) <= 0:
            continue
        masks.append(
            Viewport(
                region_id="",
                bbox_pt=bbox,
                kind="schedule",
                detection_method="fallback",
            )
        )

    mask_bboxes = [m.bbox_pt for m in masks]

    def _masked(seg) -> bool:
        mid = _seg_mid(seg)
        return any(_point_in_bbox(mid, mb) for mb in mask_bboxes)

    content_segs = [s for s in segments if not _masked(s)]

    # Scale-callout anchors (drop any inside masks, e.g. title-block scales).
    try:
        anchors = [
            c
            for c in extract_scale_callouts(page)
            if not any(_point_in_bbox((c["x"], c["y"]), mb) for mb in mask_bboxes)
        ]
    except Exception:  # noqa: BLE001
        anchors = []

    # Proto-regions: (bbox, detection_method, segments) — materialized after
    # leftover claiming so peripheral geometry (dimension chains, grid bubbles
    # around a plan) and its scale callout end up in the right region.
    protos: List[list] = []  # [bbox, method, segs]

    # ── Tier 1: clip rectangles ──────────────────────────────────────────────
    clip_rects = _substantial_clip_rects(paths, page_area) if page_area else []
    if len(clip_rects) >= 2:
        for bbox in clip_rects:
            inside = [s for s in content_segs if _point_in_bbox(_seg_mid(s), bbox)]
            protos.append([bbox, "clip_rect", inside])
        claimed_set = clip_rects
        leftover = [
            s
            for s in content_segs
            if not any(_point_in_bbox(_seg_mid(s), c) for c in claimed_set)
        ]
        # A substantial unclipped mass keeps its own region.
        if len(leftover) >= max(MIN_REGION_SEGMENTS, int(0.10 * len(content_segs))):
            bbox = _trimmed_bbox(leftover)
            if bbox is not None:
                protos.append([bbox, "fallback", leftover])

    # ── Tier 2: title anchors bounded by whitespace gutters ─────────────────
    if not protos and anchors and content_segs:
        content_bbox = _trimmed_bbox(content_segs) or (0.0, 0.0, width, height)
        cells = _gutter_cells(content_segs, content_bbox)
        if not cells:
            cells = [content_segs]
        for cell in cells:
            # Anchor containment uses the UNTRIMMED cell extent: a small
            # drawing sharing a cell with a large one must still expose its
            # anchor for the split below (percentile trim would hide it).
            raw_bbox = _trimmed_bbox(cell, trim=0.0, pad=0.0)
            if raw_bbox is None:
                continue
            cell_anchors = [
                a
                for a in anchors
                if _point_in_bbox((a["x"], a["y"]), raw_bbox, margin=30.0)
            ]
            if len(cell_anchors) >= 2:
                # Multiple titled drawings share the cell: split by anchor.
                for bucket in _bucket_by_anchor(cell, cell_anchors):
                    if len(bucket) < MIN_REGION_SEGMENTS:
                        continue
                    bbox = _trimmed_bbox(bucket)
                    if bbox is not None:
                        protos.append([bbox, "title_anchor", bucket])
            else:
                bbox = _trimmed_bbox(cell)
                if bbox is None:
                    continue
                method = "title_anchor" if cell_anchors else "density_gutter"
                protos.append([bbox, method, cell])

    # ── Tier 3: density gutters only (no anchors) ────────────────────────────
    if not protos and content_segs:
        content_bbox = _trimmed_bbox(content_segs) or (0.0, 0.0, width, height)
        cells = _gutter_cells(content_segs, content_bbox)
        if len(cells) >= 2:
            for cell in cells:
                bbox = _trimmed_bbox(cell)
                if bbox is not None:
                    protos.append([bbox, "density_gutter", cell])

    # ── Tier 4: fallback ─────────────────────────────────────────────────────
    if not protos and content_segs:
        bbox = _trimmed_bbox(content_segs) or (0.0, 0.0, width, height)
        protos.append([bbox, "fallback", content_segs])

    # ── Claim leftovers: unassigned segments join the nearest region ────────
    if protos:
        _claim_leftover_segments(protos, content_segs)

    regions = [
        _make_region(tuple(bbox), method, segs, anchors, lines)
        for bbox, method, segs in protos
    ]
    if not regions:
        regions.append(
            Viewport(
                region_id="",
                bbox_pt=(0.0, 0.0, width or 1.0, height or 1.0),
                kind="unknown",
                detection_method="fallback",
            )
        )

    # ── Assemble: region_id "R1", "R2", ... deterministic by area desc ──────
    out = regions + masks
    out.sort(key=lambda v: (-_bbox_area(v.bbox_pt), v.bbox_pt[0], v.bbox_pt[1]))
    for i, vp in enumerate(out):
        vp.region_id = "R%d" % (i + 1)
    return out


def _bbox_point_dist(pt: Tuple[float, float], bbox) -> float:
    """Euclidean distance from a point to a bbox (0 when inside)."""
    dx = max(bbox[0] - pt[0], 0.0, pt[0] - bbox[2])
    dy = max(bbox[1] - pt[1], 0.0, pt[1] - bbox[3])
    return math.hypot(dx, dy)


def _claim_leftover_segments(
    protos: List[list],
    content_segs: Sequence[Tuple[float, float, float, float]],
) -> None:
    """Assign unclaimed segments to the nearest region and grow its bbox.

    Dimension chains, extension lines and grid bubbles sit OUTSIDE the dense
    drawing mass, so trimmed region bboxes exclude them — yet the scale solver
    needs exactly those dimension lines inside the viewport bounds. Distances
    are measured against the FROZEN original bboxes (no creeping growth) and
    capped at ``CLAIM_MAX_DIST_PT`` so distant stray marks stay out. Clip-rect
    regions are authoritative boundaries and never grow.
    """
    assigned: set = set()
    for _, _, segs in protos:
        assigned.update(id(s) for s in segs)

    frozen = [tuple(p[0]) for p in protos]
    growable = [i for i, p in enumerate(protos) if p[1] != "clip_rect"]
    if not growable:
        return

    for s in content_segs:
        if id(s) in assigned:
            continue
        mid = _seg_mid(s)
        best_i, best_d = -1, CLAIM_MAX_DIST_PT
        for i in growable:
            d = _bbox_point_dist(mid, frozen[i])
            if d < best_d:
                best_d, best_i = d, i
        if best_i < 0:
            continue
        bbox, method, segs = protos[best_i]
        segs.append(s)
        # Union with the segment MIDPOINT only: the solver tests dimension-line
        # midpoints against viewport bounds, and endpoint union would let one
        # long border segment explode the region to the whole sheet.
        protos[best_i][0] = (
            min(bbox[0], mid[0]),
            min(bbox[1], mid[1]),
            max(bbox[2], mid[0]),
            max(bbox[3], mid[1]),
        )


def _make_region(
    bbox: tuple,
    method: str,
    segs: Sequence[Tuple[float, float, float, float]],
    anchors: Sequence[dict],
    lines: List[Tuple[tuple, str]],
) -> Viewport:
    """Build a drawing-region Viewport with title text and local printed scale."""
    local = [
        a
        for a in anchors
        if _point_in_bbox((a["x"], a["y"]), bbox, margin=40.0)
    ]
    printed_fpi: Optional[float] = None
    if local:
        distinct = sorted({round(a["feet_per_inch"], 6) for a in local})
        if len(distinct) == 1:
            printed_fpi = distinct[0]

    title_text = _titleish_text_in_bbox(lines, bbox)
    upper = title_text.upper()
    kind = "unknown"
    if "LEGEND" in upper and "PLAN" not in upper:
        kind = "legend"
    elif "SCHEDULE" in upper and "PLAN" not in upper:
        kind = "schedule"
    elif (printed_fpi is not None and printed_fpi < DETAIL_MAX_FPI) or (
        _DETAILISH_RE.search(title_text) and "PLAN" not in upper
    ):
        kind = "detail"

    return Viewport(
        region_id="",
        bbox_pt=bbox,
        kind=kind,
        detection_method=method,
        title_text=title_text,
        printed_fpi=printed_fpi,
        segment_count=len(segs),
    )
