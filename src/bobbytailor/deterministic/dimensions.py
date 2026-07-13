"""Dimension-line association engine (Recipe A).

Harvests dimension strings from the PDF text layer, pairs each with a
grammar-verified dimension line (terminators + extension lines), and emits
``DimensionSample`` records for the scale solver (21-07).

Replaces the brute-force nearest-segment calibration in ``geometry_takeoff``
whose mispairing caused the 1"=24' vs 1"=20' Crow failure.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence, Tuple

from shapely.geometry import LineString, box
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)

# Plausible dimension extents (feet). Unlike overall-footprint parsing, room
# and bay dims go down to inches-scale — do NOT copy footprint's 50-ft floor.
MIN_DIM_FT = 0.5
MAX_DIM_FT = 2000.0

MAX_SEGMENTS_PER_PAGE = 500_000
DIRECTION_TOL_DEG = 3.0
PERP_MIN_PT = 0.0
PERP_MAX_PT = 15.0
TERMINATOR_SEARCH_PT = 4.0
TERMINATOR_EXT_PT = 12.0
SHORT_SEG_MAX_PT = 6.0
EXTENSION_MIN_PT = 8.0
MIN_TERMINATOR_SCORE = 2

# Feet-inch dimension tokens — linear regex (no nested quantifiers / ReDoS).
_DIM_FRAC_RE = re.compile(
    r"^\s*(\d{1,4})\s*'\s*[-–]?\s*(\d{1,2})?(?:\s+(\d+)\s*/\s*(\d+))?\s*\"?\s*$"
)
_DIM_BARE_RE = re.compile(r"^\s*(\d{1,4})\s*'\s*$")

# Elevation / slope guards (ACCURACY-08 class).
_ELEVATION_CTX_RE = re.compile(
    r"\b(GL|INV|EL|T\.O\.|B\.O\.|TO\.|BO\.)\b",
    re.IGNORECASE,
)
_SLOPE_CTX_RE = re.compile(r"\d+\s*%|/FT", re.IGNORECASE)


@dataclass
class DimensionSample:
    feet: float
    points: float
    text_bbox: tuple
    line_bbox: tuple
    rotation: tuple
    score: float
    page_index: int

    def to_dict(self) -> dict:
        return asdict(self)


def parse_feet_inches(text: str) -> Optional[float]:
    """Parse a feet-inch dimension string to decimal feet, or None."""
    raw = (text or "").strip()
    if not raw:
        return None

    m = _DIM_FRAC_RE.match(raw)
    if m:
        feet = int(m.group(1))
        inches_whole = int(m.group(2)) if m.group(2) else 0
        if inches_whole >= 12:
            return None
        frac = 0.0
        if m.group(3) and m.group(4):
            den = int(m.group(4))
            if den == 0:
                return None
            frac = int(m.group(3)) / den
        total_in = inches_whole + frac
        val = feet + total_in / 12.0
        if not (MIN_DIM_FT <= val <= MAX_DIM_FT):
            return None
        return val

    m = _DIM_BARE_RE.match(raw)
    if m:
        val = float(int(m.group(1)))
        if not (MIN_DIM_FT <= val <= MAX_DIM_FT):
            return None
        return val

    return None


def _line_chars(line) -> List[Tuple[float, float, str]]:
    out: List[Tuple[float, float, str]] = []
    for span in line.get("spans", []):
        for ch in span.get("chars", []):
            b = ch["bbox"]
            out.append((b[0], b[1], ch.get("c", "")))
    return out


def _reconstruct_span_from_chars(chars: List[Tuple[float, float, str]]) -> str:
    """Rebuild span text from chars, recovering stacked fractions when needed."""
    if not chars:
        return ""
    text = "".join(c for _, _, c in chars)
    if parse_feet_inches(text) is not None:
        return text

    # Stacked-fraction recovery — logic from scale_extraction._paper_inches_from_chars,
    # adapted for feet-inch dimension strings (e.g. 1'-6 with ¹/₂ stacked).
    from bobbytailor.deterministic.scale_extraction import _paper_inches_from_chars

    # Try to find feet + stacked inch fraction in the char run.
    feet_m = re.search(r"(\d+)\s*'", text)
    if feet_m:
        feet = int(feet_m.group(1))
        after = text[feet_m.end():]
        inch_chars = [(x, y, c) for x, y, c in chars if c.isdigit() or c == "/"]
        if inch_chars:
            frac = _paper_inches_from_chars(inch_chars)
            if frac is not None:
                whole_m = re.match(r"\s*[-–]?\s*(\d{1,2})?", after)
                whole_in = int(whole_m.group(1)) if whole_m and whole_m.group(1) else 0
                if whole_in < 12:
                    val = feet + (whole_in + frac) / 12.0
                    if MIN_DIM_FT <= val <= MAX_DIM_FT:
                        return f"{feet}'-{whole_in} {frac:g}\""

    return text


def _normalize_dir(dir_: Sequence[float]) -> Tuple[float, float]:
    dx, dy = dir_[0], dir_[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return (1.0, 0.0)
    return (dx / length, dy / length)


def _is_elevation_or_slope_context(line_text: str) -> bool:
    if _ELEVATION_CTX_RE.search(line_text or ""):
        return True
    return bool(_SLOPE_CTX_RE.search(line_text or ""))


def _harvest_dimension_texts(page) -> List[dict]:
    """Harvest parsed dimension strings with rotation and geometry metadata."""
    try:
        data = page.get_text("rawdict")
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, dict):
        return []

    hits: List[dict] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            line_text = "".join(
                span.get("text", "")
                for span in line.get("spans", [])
            )
            if _is_elevation_or_slope_context(line_text):
                continue

            dir_ = _normalize_dir(line.get("dir", (1.0, 0.0)) or (1.0, 0.0))
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                chars = _line_chars({"spans": [span]})
                if chars and parse_feet_inches(span_text) is None:
                    span_text = _reconstruct_span_from_chars(chars)

                feet = parse_feet_inches(span_text)
                if feet is None:
                    continue

                bbox = span.get("bbox")
                if not bbox or len(bbox) < 4:
                    continue
                x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
                cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
                hits.append(
                    {
                        "text": span_text.strip(),
                        "feet": feet,
                        "center": (cx, cy),
                        "bbox": (x0, y0, x1, y1),
                        "dir": dir_,
                    }
                )
    return hits


def _hidden_ocg_layers(doc) -> set:
    """Return layer names that are OFF in optional-content configuration."""
    hidden: set = set()
    try:
        doc.get_ocgs()
        configs = doc.layer_ui_configs()
        if isinstance(configs, dict):
            for name, cfg in configs.items():
                if isinstance(cfg, dict) and cfg.get("on") is False:
                    hidden.add(name)
        elif isinstance(configs, list):
            for cfg in configs:
                if isinstance(cfg, dict) and cfg.get("on") is False:
                    layer = cfg.get("text") or cfg.get("layer") or cfg.get("name")
                    if layer:
                        hidden.add(layer)
    except Exception:  # noqa: BLE001
        return set()
    return hidden


def _visible_drawings(page, doc) -> list:
    """Return page drawings, excluding paths on hidden optional-content layers."""
    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001
        return []

    hidden_layers = _hidden_ocg_layers(doc)
    if not hidden_layers:
        return drawings

    visible = []
    for path in drawings:
        layer = path.get("layer") or ""
        if layer and layer in hidden_layers:
            continue
        visible.append(path)
    return visible


def _segments_from_drawings(drawings) -> List[Tuple[float, float, float, float]]:
    """Straight line segments from drawing paths as (x0, y0, x1, y1)."""
    out: List[Tuple[float, float, float, float]] = []
    for path in drawings:
        for it in path.get("items", []):
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


def _seg_len(seg: Tuple[float, float, float, float]) -> float:
    return math.hypot(seg[2] - seg[0], seg[3] - seg[1])


def _seg_dir(seg: Tuple[float, float, float, float]) -> Tuple[float, float]:
    length = _seg_len(seg)
    if length < 1e-9:
        return (1.0, 0.0)
    return ((seg[2] - seg[0]) / length, (seg[3] - seg[1]) / length)


def _angle_diff_deg(d1: Tuple[float, float], d2: Tuple[float, float]) -> float:
    dot = abs(d1[0] * d2[0] + d1[1] * d2[1])
    dot = min(1.0, max(-1.0, dot))
    return math.degrees(math.acos(dot))


def _perp_distance_to_bbox(
    mid: Tuple[float, float],
    bbox: Tuple[float, float, float, float],
    text_dir: Tuple[float, float],
) -> float:
    """Perpendicular distance from segment midpoint to the text bbox."""
    mx, my = mid
    x0, y0, x1, y1 = bbox
    tx, ty = text_dir
    if abs(tx) >= abs(ty):
        if my < y0:
            return y0 - my
        if my > y1:
            return my - y1
        return 0.0
    if mx < x0:
        return x0 - mx
    if mx > x1:
        return mx - x1
    return 0.0


def _seg_mid(seg: Tuple[float, float, float, float]) -> Tuple[float, float]:
    return ((seg[0] + seg[2]) / 2.0, (seg[1] + seg[3]) / 2.0)


def _point_near(a: Tuple[float, float], b: Tuple[float, float], radius: float) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= radius


def _segments_near_point(
    point: Tuple[float, float],
    segments: Sequence[Tuple[float, float, float, float]],
    radius: float,
) -> List[Tuple[float, float, float, float]]:
    return [
        s
        for s in segments
        if _point_near(point, (s[0], s[1]), radius)
        or _point_near(point, (s[2], s[3]), radius)
        or _point_near(point, _seg_mid(s), radius)
    ]


def _endpoint_signals(
    endpoint: Tuple[float, float],
    seg: Tuple[float, float, float, float],
    segments: Sequence[Tuple[float, float, float, float]],
    text_dir: Tuple[float, float],
) -> int:
    """Terminator/extension signals at one endpoint (0–2)."""
    signals = 0
    tick_nearby = _segments_near_point(endpoint, segments, TERMINATOR_SEARCH_PT)
    short_count = sum(
        1 for s in tick_nearby if s is not seg and _seg_len(s) < SHORT_SEG_MAX_PT
    )
    if short_count >= 2:
        signals += 1

    ext_nearby = _segments_near_point(endpoint, segments, TERMINATOR_EXT_PT)
    seg_d = _seg_dir(seg)
    for s in ext_nearby:
        if s is seg:
            continue
        s_d = _seg_dir(s)
        if _angle_diff_deg(s_d, text_dir) <= DIRECTION_TOL_DEG + 2:
            continue
        if _angle_diff_deg(s_d, seg_d) <= 90 - DIRECTION_TOL_DEG:
            continue
        if _seg_len(s) < EXTENSION_MIN_PT:
            continue
        mid = _seg_mid(s)
        if _point_near(endpoint, mid, TERMINATOR_EXT_PT):
            signals += 1
            break
    return signals


def _terminator_score(
    seg: Tuple[float, float, float, float],
    segments: Sequence[Tuple[float, float, float, float]],
    text_dir: Tuple[float, float],
) -> int:
    """Count terminator/extension signals at both endpoints (0–4)."""
    score = 0
    for endpoint in ((seg[0], seg[1]), (seg[2], seg[3])):
        score += _endpoint_signals(endpoint, seg, segments, text_dir)
    return score


def _line_bbox(seg: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    return (
        min(seg[0], seg[2]),
        min(seg[1], seg[3]),
        max(seg[0], seg[2]),
        max(seg[1], seg[3]),
    )


def _mid_in_exclude_rects(
    mid: Tuple[float, float],
    exclude_rects: Optional[Sequence],
) -> bool:
    if not exclude_rects:
        return False
    mx, my = mid
    for rect in exclude_rects:
        try:
            x0, y0, x1, y1 = rect
        except (TypeError, ValueError):
            continue
        if x0 <= mx <= x1 and y0 <= my <= y1:
            return True
    return False


def _text_center_on_segment(
    center: Tuple[float, float],
    seg: Tuple[float, float, float, float],
    text_dir: Tuple[float, float],
    margin: float = 15.0,
) -> bool:
    """True when *center* sits over the segment span along the dimension axis."""
    cx, cy = center
    mx, my = _seg_mid(seg)
    half = _seg_len(seg) / 2.0
    tx, ty = text_dir
    if abs(tx) >= abs(ty):
        return abs(cx - mx) <= half + margin
    return abs(cy - my) <= half + margin


def _corridor_candidates(
    dim: dict,
    segments: Sequence[Tuple[float, float, float, float]],
    tree: STRtree,
) -> List[Tuple[float, float, float, float]]:
    """Return dimension-line candidates for one harvested text hit."""
    bbox = dim["bbox"]
    text_dir = dim["dir"]
    x0, y0, x1, y1 = bbox
    pad = PERP_MAX_PT + 5.0
    query = box(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
    candidates: List[Tuple[float, float, float, float]] = []

    for idx in tree.query(query):
        seg = segments[int(idx)]
        if _seg_len(seg) < 5.0:
            continue
        if _angle_diff_deg(_seg_dir(seg), text_dir) > DIRECTION_TOL_DEG:
            continue
        perp = _perp_distance_to_bbox(_seg_mid(seg), bbox, text_dir)
        if not (PERP_MIN_PT <= perp <= PERP_MAX_PT):
            continue
        if not _text_center_on_segment(dim["center"], seg, text_dir):
            continue
        candidates.append(seg)

    return candidates


def _pick_best_segment(
    candidates: Sequence[Tuple[float, float, float, float]],
    segments: Sequence[Tuple[float, float, float, float]],
    text_dir: Tuple[float, float],
    feet: float,
) -> Optional[Tuple[Tuple[float, float, float, float], int]]:
    """Pick grammar-verified candidate; overall dims prefer longest span."""
    scored: List[Tuple[Tuple[float, float, float, float], int, float]] = []
    for seg in candidates:
        score = _terminator_score(seg, segments, text_dir)
        if score < MIN_TERMINATOR_SCORE:
            continue
        scored.append((seg, score, _seg_len(seg)))

    if not scored:
        return None

    if feet >= 100.0:
        seg, score, _ = max(scored, key=lambda row: (row[1], row[2]))
        return seg, score

    lengths = sorted(row[2] for row in scored)
    median_len = lengths[len(lengths) // 2]
    cap = max(median_len * 5.0, 120.0)
    local = [row for row in scored if row[2] <= cap]
    pool = local or scored
    seg, score, _ = max(pool, key=lambda row: (row[1], row[2]))
    return seg, score


def _project_t_on_segment(
    point: Tuple[float, float],
    seg: Tuple[float, float, float, float],
) -> float:
    """Project *point* onto *seg*; return parameter t in [0, 1]."""
    px, py = point
    x0, y0, x1, y1 = seg
    dx, dy = x1 - x0, y1 - y0
    denom = dx * dx + dy * dy
    if denom < 1e-9:
        return 0.5
    t = ((px - x0) * dx + (py - y0) * dy) / denom
    return max(0.0, min(1.0, t))


def _subsegment_between(
    seg: Tuple[float, float, float, float],
    t0: float,
    t1: float,
) -> Tuple[float, float, float, float]:
    x0, y0, x1, y1 = seg
    return (
        x0 + t0 * (x1 - x0),
        y0 + t0 * (y1 - y0),
        x0 + t1 * (x1 - x0),
        y0 + t1 * (y1 - y0),
    )


def _subsegments_for_chained_dims(
    seg: Tuple[float, float, float, float],
    dims: Sequence[dict],
    segments: Sequence[Tuple[float, float, float, float]],
    text_dir: Tuple[float, float],
) -> List[Tuple[float, float, float, float]]:
    """Split *seg* for multiple dimension texts along one chain."""
    ext_parts = _subsegment_at_crossings(seg, segments, text_dir)
    if len(ext_parts) >= len(dims):
        return ext_parts

    ordered = sorted(dims, key=lambda d: _project_t_on_segment(d["center"], seg))
    ts = [_project_t_on_segment(d["center"], seg) for d in ordered]
    if len(set(round(t, 3) for t in ts)) < len(ts):
        return []

    bounds = [0.0]
    for i in range(len(ts) - 1):
        bounds.append((ts[i] + ts[i + 1]) / 2.0)
    bounds.append(1.0)

    out: List[Tuple[float, float, float, float]] = []
    for i in range(len(ts)):
        sub = _subsegment_between(seg, bounds[i], bounds[i + 1])
        if _seg_len(sub) < 1.0:
            return []
        out.append(sub)
    return out


def _subsegment_at_crossings(
    seg: Tuple[float, float, float, float],
    segments: Sequence[Tuple[float, float, float, float]],
    text_dir: Tuple[float, float],
) -> List[Tuple[float, float, float, float]]:
    """Split a dimension line at extension-line crossings for chained dims."""
    seg_d = _seg_dir(seg)
    crossings: List[float] = [0.0, 1.0]
    seg_len = _seg_len(seg)
    if seg_len < 1e-9:
        return [seg]

    for s in segments:
        if s is seg:
            continue
        s_d = _seg_dir(s)
        if _angle_diff_deg(s_d, text_dir) <= DIRECTION_TOL_DEG + 2:
            continue
        if _angle_diff_deg(s_d, seg_d) <= 90 - DIRECTION_TOL_DEG:
            continue
        mid = _seg_mid(s)
        for t in (0.0, 1.0):
            ep = (
                seg[0] + t * (seg[2] - seg[0]),
                seg[1] + t * (seg[3] - seg[1]),
            )
            if _point_near(ep, mid, TERMINATOR_SEARCH_PT + 2):
                # Project crossing onto the segment parameter.
                dx, dy = seg[2] - seg[0], seg[3] - seg[1]
                if abs(dx) >= abs(dy):
                    crossings.append((mid[0] - seg[0]) / dx if dx else 0.0)
                else:
                    crossings.append((mid[1] - seg[1]) / dy if dy else 0.0)

    crossings = sorted({max(0.0, min(1.0, t)) for t in crossings})
    if len(crossings) <= 2:
        return [seg]

    subsegments: List[Tuple[float, float, float, float]] = []
    for i in range(len(crossings) - 1):
        t0, t1 = crossings[i], crossings[i + 1]
        if t1 - t0 < 0.02:
            continue
        x0 = seg[0] + t0 * (seg[2] - seg[0])
        y0 = seg[1] + t0 * (seg[3] - seg[1])
        x1 = seg[0] + t1 * (seg[2] - seg[0])
        y1 = seg[1] + t1 * (seg[3] - seg[1])
        subsegments.append((x0, y0, x1, y1))
    return subsegments or [seg]


def _dedupe_mispaired_duplicates(samples: List[DimensionSample]) -> List[DimensionSample]:
    """Drop duplicate feet values mispaired to much shorter decoy segments."""
    from collections import defaultdict

    groups: dict = defaultdict(list)
    for sample in samples:
        groups[round(sample.feet, 3)].append(sample)

    out: List[DimensionSample] = []
    for group in groups.values():
        if len(group) == 1:
            out.append(group[0])
            continue
        max_pts = max(s.points for s in group)
        min_pts = min(s.points for s in group)
        if max_pts > 0 and (max_pts - min_pts) / max_pts > 0.5:
            out.extend(s for s in group if s.points >= 0.8 * max_pts)
        else:
            out.extend(group)
    return out


def extract_dimension_samples(
    page,
    exclude_rects: Optional[Sequence] = None,
    *,
    page_index: int = 0,
    doc=None,
) -> List[DimensionSample]:
    """Run the full Recipe A pipeline on one page."""
    try:
        if doc is None:
            doc = page.parent

        drawings = _visible_drawings(page, doc)
        segments = _segments_from_drawings(drawings)
        if exclude_rects:
            segments = [
                s
                for s in segments
                if not _mid_in_exclude_rects(_seg_mid(s), exclude_rects)
            ]

        if len(segments) > MAX_SEGMENTS_PER_PAGE:
            logger.warning(
                "Dimension harvest: page %d has %d segments (> %d); skipping",
                page_index,
                len(segments),
                MAX_SEGMENTS_PER_PAGE,
            )
            return []

        if not segments:
            return []

        geoms = [LineString([(s[0], s[1]), (s[2], s[3])]) for s in segments]
        tree = STRtree(geoms)

        dim_texts = _harvest_dimension_texts(page)
        pairings: List[Tuple[dict, Tuple[float, float, float, float], int]] = []

        for dim in dim_texts:
            candidates = _corridor_candidates(dim, segments, tree)
            picked = _pick_best_segment(candidates, segments, dim["dir"], dim["feet"])
            if not picked:
                continue
            seg, score = picked
            pairings.append((dim, seg, score))

        # Chained-dimension deconfliction: multiple texts on the same segment.
        seg_to_dims: dict = {}
        for dim, seg, score in pairings:
            seg_to_dims.setdefault(seg, []).append((dim, score))

        samples: List[DimensionSample] = []
        for seg, dims in seg_to_dims.items():
            if len(dims) == 1:
                dim, score = dims[0]
                length = _seg_len(seg)
                samples.append(
                    DimensionSample(
                        feet=dim["feet"],
                        points=length,
                        text_bbox=dim["bbox"],
                        line_bbox=_line_bbox(seg),
                        rotation=dim["dir"],
                        score=float(score),
                        page_index=page_index,
                    )
                )
                continue

            dim_dicts = [d for d, _ in dims]
            text_dir = dim_dicts[0]["dir"]
            ordered = sorted(
                dims,
                key=lambda ds: _project_t_on_segment(ds[0]["center"], seg),
            )
            subsegments = _subsegments_for_chained_dims(
                seg,
                [d for d, _ in ordered],
                segments,
                text_dir,
            )
            if len(subsegments) != len(ordered):
                continue

            for (dim, score), sub in zip(ordered, subsegments):
                samples.append(
                    DimensionSample(
                        feet=dim["feet"],
                        points=_seg_len(sub),
                        text_bbox=dim["bbox"],
                        line_bbox=_line_bbox(sub),
                        rotation=dim["dir"],
                        score=float(score),
                        page_index=page_index,
                    )
                )

        return _dedupe_mispaired_duplicates(samples)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Dimension harvest failed on page %d: %s",
            page_index,
            exc,
        )
        return []
