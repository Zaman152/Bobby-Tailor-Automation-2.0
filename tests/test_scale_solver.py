"""Layer-2 gate tests for zero-calibration scale solving (V3-ACC-02, 21-07).

Gates (21-VALIDATION.md layer 2):
  Gate A — the solver's main-plan fpi lands within ±2% of the hand-recorded
           ``scale_truth.json`` value on 100% of truth-table sheets.
  Gate B (blocking) — NO viewport anywhere returns confidence == "high" with
           an fpi off-truth by more than 2%: the worst failure class
           (wrong-but-confident) is structurally prevented.

Crow acceptance note: the historical failure solved 1"=24' on the Crow
overall floor plan. The hand-verified truth for that sheet is 1"=40'
(printed "SCALE: 1\" = 40'-0\"" + the 1136'/350' overall dims at
39.74/39.16 fpi — a 20-fpi reading is geometrically impossible since 1136ft
at 20 fpi needs 4090pt on a 3024pt-wide page; see the 21-03 STATE decision).
The 1"=20' scale on this set exists only on the page-1 elevation viewports.
"""
from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from bobbytailor.deterministic.dimensions import DimensionSample
from bobbytailor.deterministic.scale_solver import (
    ViewportScale,
    resolve_scale_v2,
    select_main_plan,
    solve_page_viewports,
    solve_viewport_scale,
)
from bobbytailor.deterministic.viewports import Viewport, segment_viewports

FIXTURES = Path(__file__).parent / "fixtures"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"
BOBS_PDF = FIXTURES / "bobs_discount" / "bobs_discount_plans.pdf"
CROW_TRUTH = FIXTURES / "crow_cass" / "scale_truth.json"
BOBS_TRUTH = FIXTURES / "bobs_discount" / "scale_truth.json"

REL_TOL = 0.02  # gate tolerance: ±2% relative


def _load_truth(path: Path) -> dict:
    return json.loads(path.read_text())


def _bboxes_intersect(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def _within(value: float, truth: float, tol: float = REL_TOL) -> bool:
    return abs(value - truth) / truth <= tol


def _solve_project(pdf_path: Path) -> dict:
    """Solve every page -> {page_index: [(Viewport, ViewportScale)]}."""
    doc = fitz.open(str(pdf_path))
    try:
        return {
            i: solve_page_viewports(doc[i], page_index=i, doc=doc)
            for i in range(len(doc))
        }
    finally:
        doc.close()


@pytest.fixture(scope="module")
def crow_solutions():
    return _solve_project(CROW_PDF)


@pytest.fixture(scope="module")
def bob_solutions():
    return _solve_project(BOBS_PDF)


# ── Gate A: 100% main-plan truth ─────────────────────────────────────────────


def _assert_gate_a(solutions: dict, truth: dict) -> None:
    checked = 0
    for page_entry in truth["pages"]:
        mains = [
            v
            for v in page_entry["viewports"]
            if v.get("is_main") and v.get("fpi") is not None
        ]
        if not mains:
            continue
        truth_vp = mains[0]
        vws = solutions[page_entry["page"]]
        main_id = select_main_plan(vws)
        assert main_id is not None, (
            "page %d: no main-plan viewport selected (truth expects fpi %s)"
            % (page_entry["page"], truth_vp["fpi"])
        )
        vp, vs = next(pair for pair in vws if pair[0].region_id == main_id)
        assert _bboxes_intersect(vp.bbox_pt, truth_vp["approx_bbox_pt"]), (
            "page %d: selected main viewport %s at %s does not overlap the "
            "truth region %s"
            % (page_entry["page"], main_id, vp.bbox_pt, truth_vp["approx_bbox_pt"])
        )
        assert vs.fpi is not None and _within(vs.fpi, truth_vp["fpi"]), (
            "page %d: main-plan fpi %.3f not within ±2%% of truth %.4f"
            % (page_entry["page"], vs.fpi or -1.0, truth_vp["fpi"])
        )
        checked += 1
    assert checked > 0, "truth table contains no main-plan entries"


def test_gate_a_crow_main_plans_match_truth(crow_solutions):
    _assert_gate_a(crow_solutions, _load_truth(CROW_TRUTH))


def test_gate_a_bob_main_plans_match_truth(bob_solutions):
    _assert_gate_a(bob_solutions, _load_truth(BOBS_TRUTH))


# ── Gate B (blocking): no HIGH-confidence wrong scales anywhere ──────────────


def _assert_gate_b(solutions: dict, truth: dict) -> None:
    truth_by_page = {p["page"]: p["viewports"] for p in truth["pages"]}
    for page_index, vws in solutions.items():
        for vp, vs in vws:
            if vs.confidence != "high":
                continue
            # Structural rubric: HIGH is only reachable through the
            # three-condition conjunction (>=8 inliers, >=80% share,
            # printed agreement) — assert it held on real output.
            assert vs.printed_agreement is True, (
                "page %d %s: HIGH confidence without printed agreement"
                % (page_index, vp.region_id)
            )
            assert vs.n_inliers >= 8 and vs.inlier_share >= 0.8, (
                "page %d %s: HIGH confidence with n=%d share=%.2f"
                % (page_index, vp.region_id, vs.n_inliers, vs.inlier_share)
            )
            # Wrongness check: a HIGH viewport overlapping any hand-recorded
            # truth region must match that truth within ±2%.
            overlapping = [
                t
                for t in truth_by_page.get(page_index, [])
                if t.get("fpi") is not None
                and t.get("approx_bbox_pt")
                and _bboxes_intersect(vp.bbox_pt, t["approx_bbox_pt"])
            ]
            for t in overlapping:
                wrong = not _within(vs.fpi, t["fpi"])
                assert not (vs.confidence == "high" and wrong), (
                    "page %d %s: HIGH-confidence WRONG scale %.3f vs truth %.4f"
                    % (page_index, vp.region_id, vs.fpi, t["fpi"])
                )


def test_gate_b_crow_no_high_confidence_wrong(crow_solutions):
    _assert_gate_b(crow_solutions, _load_truth(CROW_TRUTH))


def test_gate_b_bob_no_high_confidence_wrong(bob_solutions):
    _assert_gate_b(bob_solutions, _load_truth(BOBS_TRUTH))


# ── Crow acceptance: the 1136'x350' sheet, not 24', not a detail scale ──────


def test_crow_overall_plan_solves_verified_truth_not_24(crow_solutions):
    """The page carrying the 1136'x350' overall dims solves the hand-verified
    1"=40' truth — NOT within 2% of the historical 24.0 failure, and NOT a
    detail scale. (The plan's original 20.0 expectation traced to a stale
    research note; see module docstring and the 21-03 STATE decision.)"""
    vws = crow_solutions[0]
    main_id = select_main_plan(vws)
    assert main_id is not None
    vp, vs = next(pair for pair in vws if pair[0].region_id == main_id)
    assert vs.fpi is not None
    assert _within(vs.fpi, 40.0), "main-plan fpi %.3f not at 1\"=40' truth" % vs.fpi
    assert not _within(vs.fpi, 24.0), "solver reproduced the 1\"=24' failure"
    assert vs.fpi > 4.0, "main plan landed on a detail scale (%.3f)" % vs.fpi


def test_crow_main_plan_reaches_high_confidence(crow_solutions):
    """Crow p0 has 30+ verified dims agreeing with the printed scale — the
    rubric must award HIGH there (proves HIGH is attainable, not vacuous)."""
    vws = crow_solutions[0]
    main_id = select_main_plan(vws)
    vp, vs = next(pair for pair in vws if pair[0].region_id == main_id)
    assert vs.confidence == "high"
    assert vs.printed_agreement is True
    assert vs.method == "ransac_consensus"


def test_bob_weighted_consensus_beats_decoy_cluster(bob_solutions):
    """Bob p1: six identical mispaired 216pt decoys suggest 10.0 fpi; the
    200'/250' overall dims carry ~2x their paper length and recover the
    printed 3/32"=1'-0" truth (10.6667)."""
    vws = bob_solutions[1]
    main_id = select_main_plan(vws)
    assert main_id is not None
    vp, vs = next(pair for pair in vws if pair[0].region_id == main_id)
    assert vs.fpi is not None
    assert _within(vs.fpi, 10.6667), "fpi %.3f missed the printed truth" % vs.fpi
    assert not _within(vs.fpi, 10.0), "decoy cluster captured the consensus"


# ── Synthetic helpers ────────────────────────────────────────────────────────


def _vp(region_id="R1", bbox=(0.0, 0.0, 1000.0, 1000.0), kind="unknown",
        title=""):
    return Viewport(
        region_id=region_id,
        bbox_pt=bbox,
        kind=kind,
        detection_method="fallback",
        title_text=title,
    )


def _sample(feet: float, points: float, x: float = 100.0, y: float = 100.0):
    return DimensionSample(
        feet=feet,
        points=points,
        text_bbox=(x, y - 12, x + 40, y),
        line_bbox=(x, y, x + points, y),
        rotation=(1.0, 0.0),
        score=2.0,
        page_index=0,
    )


def _samples_at_fpi(fpi: float, feet_values, y0: float = 50.0):
    return [
        _sample(f, f * 72.0 / fpi, x=20.0, y=y0 + 20.0 * i)
        for i, f in enumerate(feet_values)
    ]


def _scale(fpi: float, confidence: str = "medium", n: int = 6, share: float = 0.7,
           printed=None) -> ViewportScale:
    return ViewportScale(
        fpp=fpi / 72.0,
        fpi=fpi,
        confidence=confidence,
        n_inliers=n,
        inlier_share=share,
        printed_agreement=printed,
        door_check=None,
        method="ransac_consensus",
    )


# ── resolve_scale_v2 tier tests ──────────────────────────────────────────────

SOLVED = [(_vp(title="OVERALL FLOOR PLAN"), _scale(25.0, printed=False))]
PRINTED_TEXT = '1" = 20\'-0"'


def test_resolve_v2_override_wins_over_everything():
    res = resolve_scale_v2(
        None,
        SOLVED,
        override_feet_per_inch=30.0,
        learned_prior=40.0,
        scale_text=PRINTED_TEXT,
    )
    assert res.method == "override"
    assert res.confidence == "high"
    assert res.feet_per_point == pytest.approx(30.0 / 72.0)


def test_resolve_v2_solved_beats_printed_when_apart_and_flags():
    """Pitfall 11: the dimension solve wins over a printed scale >2% apart,
    with the disagreement flagged in the detail."""
    res = resolve_scale_v2(None, SOLVED, scale_text=PRINTED_TEXT)
    assert res.method == "dimension_solve"
    assert res.feet_per_point == pytest.approx(25.0 / 72.0)
    assert "CONFLICTS" in res.detail


def test_resolve_v2_printed_used_when_no_solve_and_capped_medium():
    """Printed notation fills in when no viewport solved — demoted: its
    confidence is capped at medium, and it still beats a learned prior."""
    res = resolve_scale_v2(None, [], learned_prior=40.0, scale_text=PRINTED_TEXT)
    assert res.method == "printed_scale"
    assert res.confidence == "medium"
    assert res.feet_per_point == pytest.approx(20.0 / 72.0)


def test_resolve_v2_low_confidence_solve_falls_through_to_printed():
    """A LOW/conflicted solve must not drive downstream quantities: the chain
    falls through to the printed tier."""
    low = [(_vp(), _scale(93.0, confidence="low", n=1, share=0.3))]
    res = resolve_scale_v2(None, low, scale_text=PRINTED_TEXT)
    assert res.method == "printed_scale"


def test_resolve_v2_learned_prior_only_when_tiers_empty():
    """Anti-amplification: the learned prior is used ONLY when neither a
    solved nor a printed scale exists, and always lands at low confidence."""
    res = resolve_scale_v2(None, [], learned_prior=40.0)
    assert res.method == "learned_prior"
    assert res.confidence == "low"
    assert res.feet_per_point == pytest.approx(40.0 / 72.0)

    # A solved viewport present -> the prior must NOT be consulted.
    res2 = resolve_scale_v2(None, SOLVED, learned_prior=40.0)
    assert res2.method == "dimension_solve"


def test_resolve_v2_none_when_nothing_available():
    res = resolve_scale_v2(None, [])
    assert res.method == "none"
    assert res.confidence == "none"
    assert res.feet_per_point is None


# ── RANSAC estimator behavior ────────────────────────────────────────────────


def test_ransac_contamination_recovers_majority_scale():
    """Pitfall 5: 40% detail-scale contamination in the sample set — the
    solver still recovers the majority scale, and the diluted inlier share
    caps confidence at medium (a near-split vote can never be HIGH)."""
    main = _samples_at_fpi(40.0, [20, 25, 30, 35, 40, 50, 60, 70, 80, 100, 45, 55])
    detail = _samples_at_fpi(8.0, [2, 3, 4, 5, 6, 7, 8, 5], y0=600.0)
    vs = solve_viewport_scale(main + detail, _vp(), printed_fpi=40.0)
    assert vs.fpi == pytest.approx(40.0, rel=REL_TOL)
    assert vs.n_inliers == 12
    assert vs.inlier_share < 0.8
    assert vs.confidence in ("medium", "low")
    assert vs.confidence != "high"


def test_solve_no_samples_returns_none_confidence():
    """Degenerate input (threat model): zero samples -> confidence 'none',
    never a guessed value."""
    vs = solve_viewport_scale([], _vp(), printed_fpi=20.0)
    assert vs.fpp is None
    assert vs.fpi is None
    assert vs.confidence == "none"
    assert vs.n_inliers == 0
    assert vs.method == "none"


def test_high_requires_printed_agreement_conjunction():
    """HIGH is a three-condition conjunction: a clean consensus without
    printed corroboration stays MEDIUM; a printed conflict drops to LOW."""
    clean = _samples_at_fpi(40.0, [20, 25, 30, 35, 40, 50, 60, 70, 80, 100])

    no_printed = solve_viewport_scale(clean, _vp())
    assert no_printed.n_inliers >= 8 and no_printed.inlier_share >= 0.8
    assert no_printed.confidence == "medium"
    assert no_printed.printed_agreement is None

    agreeing = solve_viewport_scale(clean, _vp(), printed_fpi=40.0)
    assert agreeing.confidence == "high"
    assert agreeing.printed_agreement is True

    conflicting = solve_viewport_scale(clean, _vp(), printed_fpi=20.0)
    assert conflicting.confidence == "low"
    assert conflicting.printed_agreement is False


def test_solve_filters_samples_to_viewport_bounds():
    """Samples outside the viewport bbox never enter the consensus."""
    inside = _samples_at_fpi(40.0, [20, 30, 40, 50], y0=100.0)
    outside = _samples_at_fpi(8.0, [2, 3, 4, 5, 6, 7], y0=5000.0)
    vs = solve_viewport_scale(inside + outside, _vp(bbox=(0, 0, 1000, 1000)))
    assert vs.fpi == pytest.approx(40.0, rel=REL_TOL)
    assert vs.n_inliers == 4


def test_off_ladder_solve_kept_but_flagged():
    """A non-ladder scale (e.g. 1"=25' site plans) keeps the solved value and
    flags the method — the ladder snap is a cross-check, never a correction."""
    vs = solve_viewport_scale(_samples_at_fpi(25.0, [20, 30, 40, 50, 60]), _vp())
    assert vs.fpi == pytest.approx(25.0, rel=REL_TOL)
    assert vs.method == "ransac_consensus_offladder"


# ── Main-plan selection ──────────────────────────────────────────────────────


def test_select_main_plan_real_area_beats_detail_frequency():
    """Five detail viewports outnumber one plan viewport, but real area after
    per-viewport scale picks the plan (frequency can no longer win)."""
    plan = (_vp("R1", bbox=(0, 0, 2000, 1500), title="OVERALL FLOOR PLAN"),
            _scale(40.0, n=10, share=0.9))
    details = [
        (_vp("R%d" % (i + 2), bbox=(i * 210.0, 1600.0, i * 210.0 + 200.0, 1800.0),
             title="TYPICAL DETAIL"),
         _scale(0.6667, n=5, share=0.9))
        for i in range(5)
    ]
    assert select_main_plan([plan] + details) == "R1"


def test_select_main_plan_label_breaks_near_ties():
    """Near-equal real areas: the floor-plan-labelled viewport wins."""
    labelled = (_vp("R1", bbox=(0, 0, 1000, 1000), title="FLOOR FINISH PLAN"),
                _scale(10.0, n=6, share=0.8))
    unlabelled = (_vp("R2", bbox=(1100, 0, 2105, 1000), title="OVERALL EAST ELEVATION"),
                  _scale(10.0, n=6, share=0.8))
    assert select_main_plan([unlabelled, labelled]) == "R1"


def test_select_main_plan_ignores_masks_and_unsolved():
    """Mask kinds and low/none-confidence viewports are never main-plan
    candidates; with nothing eligible the selection returns None."""
    entries = [
        (_vp("R1", kind="title_block"), _scale(40.0)),
        (_vp("R2", kind="schedule"), _scale(40.0)),
        (_vp("R3"), _scale(93.0, confidence="low")),
        (_vp("R4"), ViewportScale(None, None, "none", 0, 0.0, None, None, "none")),
    ]
    assert select_main_plan(entries) is None


# ── Truth tables + segmentation smoke (Task 1 acceptance) ────────────────────


def test_truth_tables_exist_with_expected_values():
    crow = _load_truth(CROW_TRUTH)
    bob = _load_truth(BOBS_TRUTH)
    crow_fpis = [
        v["fpi"] for p in crow["pages"] for v in p["viewports"] if v["fpi"]
    ]
    assert 20 in crow_fpis and 40 in crow_fpis
    assert len(crow["pages"]) == 4, "all Crow pages must be recorded"
    assert len(bob["pages"]) == 7, "all Bob pages must be recorded"
    bob_mains = [
        v["fpi"]
        for p in bob["pages"]
        for v in p["viewports"]
        if v.get("is_main")
    ]
    assert bob_mains == [10.6667, 10.6667]


def test_segment_viewports_crow_page0_regions_and_title_block():
    doc = fitz.open(str(CROW_PDF))
    try:
        vps = segment_viewports(doc[0])
    finally:
        doc.close()
    assert len(vps) >= 2
    assert sum(1 for v in vps if v.kind == "title_block") == 1
    valid_methods = {"clip_rect", "title_anchor", "density_gutter", "fallback"}
    assert all(v.detection_method in valid_methods for v in vps)
    d = vps[0].to_dict()
    assert "region_id" in d and "bbox_pt" in d


def test_segment_viewports_bob_uses_authoritative_clip_rects():
    doc = fitz.open(str(BOBS_PDF))
    try:
        vps = segment_viewports(doc[1])
    finally:
        doc.close()
    clip_regions = [v for v in vps if v.detection_method == "clip_rect"]
    assert len(clip_regions) >= 2
    main_clip = next(
        v for v in clip_regions if _bboxes_intersect(v.bbox_pt, (72, 99, 2124, 2295))
    )
    assert main_clip.segment_count > 1000


def test_viewport_scale_record_surfaces_confidence_fields():
    """V3-ACC-02: the per-viewport record persists fpp/n_inliers/share/
    printed_agreement/door_check for the report and UI (consumed by 21-13)."""
    vs = solve_viewport_scale(
        _samples_at_fpi(40.0, [20, 30, 40, 50, 60, 70, 80, 90]), _vp(),
        printed_fpi=40.0,
    )
    d = vs.to_dict()
    for key in ("fpp", "fpi", "confidence", "n_inliers", "inlier_share",
                "printed_agreement", "door_check", "method"):
        assert key in d, "ViewportScale.to_dict missing %s" % key
    assert d["door_check"] is None  # populated later by walls (21-10)
