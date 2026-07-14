"""Zero-calibration scale solving (V3-ACC-02) — RANSAC consensus per viewport.

Dimension strings on a drawing give the exact distance-in-feet between two
geometric points, so scale is solvable deterministically per viewport with no
manual calibration: every ``DimensionSample`` (21-03) is a ratio
``r_i = feet_i / points_i`` and all valid ratios inside one viewport are the
same value up to noise. A RANSAC-style consensus resists the two known
killers — mispairings and detail-scale contamination (RESEARCH §2, Pitfall 5).

Consensus is measured in **paper length explained** (sum of the inlier
samples' point-lengths), not raw sample count: grammar-verified long spans
(overall building dims, full dimension chains) are the strongest evidence on
a sheet, while mispaired decoys repeat identical short/medium segments. On
the Bob's Discount fixture, count-voting is captured by six identical decoy
pairings while the 200'/250' overall dims carry ~2x their paper length and
recover the printed 3/32" = 1'-0" truth.

Priority chain (``resolve_scale_v2``, RESEARCH Pitfall 11):

    override > dimension-solved > printed notation (cross-check, demoted)
             > learned prior (anti-amplification: never outranks the others)

Printed notation is demoted because it lies on half-size prints and "NTS"
sheets; the dimension solve survives re-scaling because dims and geometry
shrink together. Degenerate inputs (no samples) return confidence ``none``
and fall through the chain — never a guessed value (flag-don't-guess).

Every viewport solve persists ``{fpp, n_inliers, share, printed_agreement,
door_check}`` so the report/UI can surface per-viewport confidence
(consumed by 21-13).
"""
from __future__ import annotations

import logging
import statistics
from dataclasses import asdict, dataclass
from typing import List, Optional, Sequence, Tuple

from bobbytailor.deterministic.geometry_takeoff import POINTS_PER_INCH, ScaleResult
from bobbytailor.deterministic.scale_extraction import dominant_scale, snap_fpi
from bobbytailor.deterministic.viewports import Viewport, segment_viewports

logger = logging.getLogger(__name__)

# RANSAC estimator knobs (RESEARCH §2 "Solving feet-per-point per viewport").
RANSAC_MAX_HYPOTHESES = 50
RANSAC_INLIER_TOL = 0.02          # +/- 2% relative

# Cross-check tolerances.
PRINTED_AGREE_TOL = 0.01          # solved vs printed within 1% -> agreement
LADDER_FLAG_TOL = 0.02            # solved vs ladder snap > 2% -> off-ladder flag

# Confidence rubric (blocking acceptance criterion — the HIGH conjunction is
# the structural mitigation against wrong-but-confident output).
HIGH_MIN_INLIERS = 8
HIGH_MIN_SHARE = 0.8
MEDIUM_MIN_INLIERS = 4

# Viewport-bounds filter: dimension-line midpoint must sit within the region
# (small margin for lines hugging the boundary).
VIEWPORT_MARGIN_PT = 12.0

# Main-plan selection: viewports within this fraction of the largest real
# area count as ties, broken by floor-plan text labels.
MAIN_PLAN_AREA_TIE = 0.90

_MASK_KINDS = ("title_block", "legend", "schedule")


@dataclass
class ViewportScale:
    """Per-viewport solve record surfaced in reports/UI (V3-ACC-02)."""

    fpp: Optional[float]              # feet per PDF point
    fpi: Optional[float]              # feet per paper inch (fpp * 72)
    confidence: str                   # high | medium | low | none
    n_inliers: int
    inlier_share: float               # paper-length share of the consensus set
    printed_agreement: Optional[bool]  # solved vs printed callout within 1%
    door_check: Optional[bool]        # populated later by walls (21-10)
    method: str                       # ransac_consensus[_offladder] | none

    def to_dict(self) -> dict:
        return asdict(self)


def _no_scale(printed_agreement: Optional[bool] = None,
              door_check: Optional[bool] = None) -> ViewportScale:
    return ViewportScale(
        fpp=None,
        fpi=None,
        confidence="none",
        n_inliers=0,
        inlier_share=0.0,
        printed_agreement=printed_agreement,
        door_check=door_check,
        method="none",
    )


def _samples_in_viewport(samples: Sequence, viewport: Viewport) -> List:
    """Samples whose dimension-line midpoint falls inside the viewport."""
    x0, y0, x1, y1 = viewport.bbox_pt
    out = []
    for s in samples:
        lb = s.line_bbox
        mx = (lb[0] + lb[2]) / 2.0
        my = (lb[1] + lb[3]) / 2.0
        if (
            x0 - VIEWPORT_MARGIN_PT <= mx <= x1 + VIEWPORT_MARGIN_PT
            and y0 - VIEWPORT_MARGIN_PT <= my <= y1 + VIEWPORT_MARGIN_PT
        ):
            out.append(s)
    return out


def _ransac_consensus(
    ratios: Sequence[float],
    weights: Sequence[float],
) -> Tuple[Optional[float], int, float]:
    """Largest-consensus median over ratio hypotheses.

    Returns ``(median_ratio, n_inliers, inlier_weight_share)``. Deterministic:
    every sample ratio is tried as a hypothesis (the k = min(n, 50) iteration
    budget from RESEARCH §2 — when n > 50 the 50 largest-weight samples are
    the hypothesis pool, since long verified spans are the best seeds).
    Consensus size is the summed paper length (weight) of the inliers.
    """
    n = len(ratios)
    if n == 0:
        return None, 0, 0.0

    total_weight = sum(weights) or 1.0
    order = sorted(range(n), key=lambda i: (-weights[i], ratios[i]))
    hypotheses = order[:RANSAC_MAX_HYPOTHESES]

    best_key: Optional[tuple] = None
    best_inliers: List[int] = []
    for h in hypotheses:
        rh = ratios[h]
        if rh <= 0:
            continue
        inliers = [
            i for i in range(n) if abs(ratios[i] - rh) / rh <= RANSAC_INLIER_TOL
        ]
        w = sum(weights[i] for i in inliers)
        # Deterministic tie-break: heavier consensus, then more samples, then
        # the smaller ratio (stable across input orderings).
        key = (w, len(inliers), -rh)
        if best_key is None or key > best_key:
            best_key = key
            best_inliers = inliers

    if not best_inliers or best_key is None:
        return None, 0, 0.0

    median_ratio = statistics.median(ratios[i] for i in best_inliers)
    share = best_key[0] / total_weight
    return median_ratio, len(best_inliers), share


def solve_viewport_scale(
    samples: Sequence,
    viewport: Viewport,
    printed_fpi: Optional[float] = None,
    door_check: Optional[bool] = None,
) -> ViewportScale:
    """RANSAC consensus solve over the ``DimensionSample``s inside *viewport*.

    ``printed_fpi`` is the printed-notation cross-check ONLY — it never
    changes the solved value, only the agreement flag and confidence.
    ``door_check`` is a pass-through populated later by walls (21-10).
    """
    vp_samples = _samples_in_viewport(samples, viewport)
    vp_samples = [s for s in vp_samples if s.points > 0 and s.feet > 0]
    if not vp_samples:
        return _no_scale(door_check=door_check)

    ratios = [s.feet / s.points for s in vp_samples]
    weights = [float(s.points) for s in vp_samples]
    fpp, n_inliers, share = _ransac_consensus(ratios, weights)
    if fpp is None or fpp <= 0:
        return _no_scale(door_check=door_check)

    fpi = fpp * POINTS_PER_INCH

    # Ladder snap is a CROSS-CHECK only: solved wins when they disagree, but
    # the off-ladder condition is flagged in the method (some site plans use
    # non-ladder scales, e.g. 1" = 25').
    snapped = snap_fpi(fpi)
    off_ladder = snapped is None or abs(fpi - snapped) / snapped > LADDER_FLAG_TOL
    method = "ransac_consensus_offladder" if off_ladder else "ransac_consensus"

    printed_agreement: Optional[bool] = None
    if printed_fpi and printed_fpi > 0:
        printed_ref = snap_fpi(printed_fpi) or printed_fpi
        printed_agreement = abs(fpi - printed_ref) / printed_ref <= PRINTED_AGREE_TOL

    confidence = _confidence(n_inliers, share, printed_agreement)

    return ViewportScale(
        fpp=fpp,
        fpi=fpi,
        confidence=confidence,
        n_inliers=n_inliers,
        inlier_share=share,
        printed_agreement=printed_agreement,
        door_check=door_check,
        method=method,
    )


def _confidence(
    n_inliers: int,
    share: float,
    printed_agreement: Optional[bool],
) -> str:
    """Confidence rubric (RESEARCH §2) — the HIGH tier is a three-condition
    conjunction so a wrong scale can never be HIGH without independent
    printed-notation corroboration:

        HIGH   = n_inliers >= 8 AND inlier_share >= 0.8
                 AND printed_agreement is True
        MEDIUM = >= 4 inliers without printed conflict, or printed agreement
        LOW    = fewer inliers, or a printed-scale conflict
    """
    if (
        n_inliers >= HIGH_MIN_INLIERS
        and share >= HIGH_MIN_SHARE
        and printed_agreement is True
    ):
        return "high"
    if printed_agreement is True:
        return "medium"
    if n_inliers >= MEDIUM_MIN_INLIERS and printed_agreement is not False:
        return "medium"
    return "low"


# ── Main-plan selection ───────────────────────────────────────────────────────


def _real_area_sf(viewport: Viewport, scale: ViewportScale) -> float:
    """Viewport area in square feet under its OWN solved scale."""
    if not scale.fpp:
        return 0.0
    x0, y0, x1, y1 = viewport.bbox_pt
    return max(0.0, x1 - x0) * max(0.0, y1 - y0) * scale.fpp * scale.fpp


def _plan_label_score(viewport: Viewport) -> int:
    """1 when the viewport's title text reads like a floor plan."""
    text = (viewport.title_text or "").upper()
    if "PLAN" not in text:
        return 0
    if any(word in text for word in ("ELEVATION", "SECTION", "DETAIL")):
        return 0
    return 1


def select_main_plan(
    viewports_with_scales: Sequence[Tuple[Viewport, ViewportScale]],
) -> Optional[str]:
    """Pick the main-plan viewport: largest REAL area after per-viewport scale.

    Frequency of detail callouts can no longer win — detail viewports are many
    but tiny once their own scale is applied. Floor-plan text labels break
    near-ties (within ``MAIN_PLAN_AREA_TIE`` of the largest real area). Only
    solved viewports at medium+ confidence are eligible: a LOW/conflicted
    solve must not silently drive every downstream quantity.
    """
    candidates = [
        (vp, vs)
        for vp, vs in viewports_with_scales
        if vp.kind not in _MASK_KINDS
        and vs.fpp
        and vs.confidence in ("high", "medium")
    ]
    if not candidates:
        return None

    areas = {vp.region_id: _real_area_sf(vp, vs) for vp, vs in candidates}
    max_area = max(areas.values())
    if max_area <= 0:
        return None

    best = max(
        candidates,
        key=lambda pair: (
            1 if areas[pair[0].region_id] >= MAIN_PLAN_AREA_TIE * max_area else 0,
            _plan_label_score(pair[0]),
            areas[pair[0].region_id],
            pair[0].region_id,  # deterministic final tie-break
        ),
    )
    return best[0].region_id


# ── Priority chain (resolve_scale v2) ────────────────────────────────────────


def resolve_scale_v2(
    page,
    viewports_with_scales: Optional[Sequence[Tuple[Viewport, ViewportScale]]] = None,
    override_feet_per_inch: Optional[float] = None,
    learned_prior: Optional[float] = None,
    scale_text: Optional[str] = None,
) -> ScaleResult:
    """Resolve the sheet scale via the v2 priority chain (Pitfall 11).

    Returns the EXISTING ``ScaleResult`` contract from ``geometry_takeoff``
    (downstream ``scale_recalc``/calibration UI/reporter consume the dict
    shape unchanged); ``method`` values extended with ``dimension_solve`` and
    ``learned_prior``.

    Chain: (1) explicit override -> (2) dimension-solved main-plan viewport ->
    (3) printed notation (demoted; confidence capped at medium when it stands
    alone) -> (4) learned prior (ONLY when tiers 2-3 are unavailable — the
    anti-amplification rule: a learned prior NEVER outranks a solved or
    printed scale) -> (5) none.
    """
    # (1) Explicit override — most reliable.
    if override_feet_per_inch and override_feet_per_inch > 0:
        return ScaleResult(
            feet_per_point=override_feet_per_inch / POINTS_PER_INCH,
            confidence="high",
            method="override",
            detail="%g ft per inch (supplied)" % override_feet_per_inch,
        )

    # (2) Dimension-solved main-plan viewport scale.
    vws = list(viewports_with_scales or [])
    main_id = select_main_plan(vws)
    if main_id is not None:
        for vp, vs in vws:
            if vp.region_id != main_id or not vs.fpp:
                continue
            detail = (
                "%.2f ft/in solved from %d dims (share %.0f%%) in viewport %s"
                % (vs.fpi or 0.0, vs.n_inliers, vs.inlier_share * 100, vp.region_id)
            )
            if vs.printed_agreement is False:
                detail += "; CONFLICTS with printed scale — solved value kept"
            if vs.method == "ransac_consensus_offladder":
                detail += "; off standard scale ladder"
            return ScaleResult(
                feet_per_point=vs.fpp,
                confidence=vs.confidence,
                method="dimension_solve",
                detail=detail,
            )

    # (3) Printed scale notation — demoted to a cross-check tier. Without a
    # dimension solve backing it, confidence is capped at medium (Pitfall 11:
    # printed scale lies on half-size prints / NTS / mislabeled details).
    try:
        fpi, conf, detail = dominant_scale(page, scale_text)
    except Exception:  # noqa: BLE001 — untrusted PDF must not break the chain
        fpi, conf, detail = None, "none", ""
    if fpi:
        conf = "medium" if conf == "high" else conf
        return ScaleResult(
            feet_per_point=fpi / POINTS_PER_INCH,
            confidence=conf,
            method="printed_scale",
            detail=detail + " (printed notation only — unverified by dimensions)",
        )

    # (4) Learned prior — last resort, never outranks solved/printed.
    if learned_prior and learned_prior > 0:
        return ScaleResult(
            feet_per_point=learned_prior / POINTS_PER_INCH,
            confidence="low",
            method="learned_prior",
            detail=(
                "%g ft/in learned prior (no solved or printed scale available)"
                % learned_prior
            ),
        )

    # (5) Nothing — flag, don't guess.
    return ScaleResult(feet_per_point=None, confidence="none", method="none")


# ── Page-level orchestration (consumed by tests and 21-13) ───────────────────


def solve_page_viewports(
    page,
    table_bboxes: Optional[Sequence] = None,
    *,
    page_index: int = 0,
    doc=None,
) -> List[Tuple[Viewport, ViewportScale]]:
    """Segment *page* and solve every drawing viewport's scale.

    Mask regions (title block / legend / schedule) are excluded from both
    dimension harvesting and solving. The per-viewport printed cross-check
    comes from, in order: the viewport's own bound callout anchor, a scale
    notation in the viewport's title text, or the page's printed notation —
    the last ONLY when the sheet carries exactly one distinct printed scale
    (a page-level value must not cross-check the wrong viewport on a genuine
    multi-scale sheet).
    """
    from bobbytailor.deterministic.dimensions import extract_dimension_samples
    from bobbytailor.deterministic.scale_extraction import extract_scales_from_text

    viewports = segment_viewports(page, table_bboxes=table_bboxes)
    mask_rects = [vp.bbox_pt for vp in viewports if vp.kind in _MASK_KINDS]

    samples = extract_dimension_samples(
        page, exclude_rects=mask_rects, page_index=page_index, doc=doc
    )

    def _title_printed(vp: Viewport) -> Optional[float]:
        if not vp.title_text:
            return None
        try:
            found = extract_scales_from_text(vp.title_text)
        except Exception:  # noqa: BLE001
            return None
        distinct = sorted({fpi for fpi, _ in found})
        return distinct[0] if len(distinct) == 1 else None

    page_printed: Optional[float] = None
    local_fpis = {
        round(vp.printed_fpi, 6)
        for vp in viewports
        if vp.printed_fpi and vp.kind not in _MASK_KINDS
    }
    try:
        dom_fpi, _, _ = dominant_scale(page)
    except Exception:  # noqa: BLE001
        dom_fpi = None
    if dom_fpi and len(local_fpis | {round(dom_fpi, 6)}) <= 1:
        page_printed = dom_fpi

    out: List[Tuple[Viewport, ViewportScale]] = []
    for vp in viewports:
        if vp.kind in _MASK_KINDS:
            out.append((vp, _no_scale()))
            continue
        printed = vp.printed_fpi or _title_printed(vp) or page_printed
        out.append((vp, solve_viewport_scale(samples, vp, printed_fpi=printed)))
    return out
