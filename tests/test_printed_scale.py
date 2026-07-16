"""Offline tests for printed-scale reading (PRIMARY scale source).

No PDF, no network, no paid calls — synthetic fitz-like pages and viewports.
"""
from __future__ import annotations

import pytest

from bobbytailor.deterministic.geometry_takeoff import ScaleResult
from bobbytailor.deterministic.printed_scale import (
    PrintedScale,
    extract_printed_scales,
    identify_main_plan_scale,
    match_scales_to_viewports,
    parse_scale_ratio,
)
from bobbytailor.deterministic.scale_solver import ViewportScale, resolve_scale_v2
from bobbytailor.deterministic.viewports import Viewport


# ── parse_scale_ratio ─────────────────────────────────────────────────────────


def test_parse_engineering_forty():
    assert parse_scale_ratio('SCALE: 1" = 40\'-0"') == 40.0


def test_parse_engineering_twenty_no_inches():
    assert parse_scale_ratio('1" = 20\'') == 20.0


def test_parse_quarter_inch():
    assert parse_scale_ratio('1/4" = 1\'-0"') == 4.0


def test_parse_eighth_inch():
    assert parse_scale_ratio('1/8" = 1\'-0"') == 8.0


def test_parse_three_thirtyseconds():
    assert abs(parse_scale_ratio('3/32" = 1\'-0"') - 10.667) < 0.01


def test_parse_one_and_half_inch():
    assert abs(parse_scale_ratio('1 1/2" = 1\'-0"') - 0.6667) < 1e-3


def test_parse_half_inch():
    assert parse_scale_ratio('1/2" = 1\'-0"') == 2.0


def test_parse_three_quarter_inch():
    assert abs(parse_scale_ratio('3/4" = 1\'-0"') - 1.333) < 1e-3


def test_parse_smart_quotes_and_whitespace():
    # Curly double-prime / prime and messy spacing must still parse.
    assert parse_scale_ratio('SCALE:  1″  =  40′-0″') == 40.0


# ── Dropped-slash stacked-fraction repair ─────────────────────────────────────
#
# CAD exports typeset the fraction as ONE stacked glyph in its own text span, so
# the PDF text layer flattens '1/8" = 1'-0"' to '18" = 1'-0"' (real spans from
# Bob's page 4: ['SCALE: ', '18', '" = 1\'-0"']). Read literally that is 0.056
# ft/in instead of 8.0 — a 144x scale error that corrupts every quantity on the
# sheet. The literal readings ("18 paper inches = 1 foot") are architecturally
# impossible, so the repair cannot rewrite a legitimate scale.


@pytest.mark.parametrize("text,expected", [
    ('SCALE: 18" = 1\'-0"', 8.0),          # 1/8"  = 1'-0"
    ('SCALE: 14" = 1\'-0"', 4.0),          # 1/4"  = 1'-0"
    ('SCALE: 12" = 1\'-0"', 2.0),          # 1/2"  = 1'-0"
    ('SCALE: 34" = 1\'-0"', 4.0 / 3.0),    # 3/4"  = 1'-0"
    ('SCALE: 38" = 1\'-0"', 8.0 / 3.0),    # 3/8"  = 1'-0"
    ('SCALE: 316" = 1\'-0"', 16.0 / 3.0),  # 3/16" = 1'-0"
    ('SCALE: 116" = 1\'-0"', 16.0),        # 1/16" = 1'-0"
    ('SCALE: 132" = 1\'-0"', 32.0),        # 1/32" = 1'-0"
    ('SCALE: 332" = 1\'-0"', 32.0 / 3.0),  # 3/32" = 1'-0"
])
def test_parse_dropped_slash_stacked_fraction(text, expected):
    assert abs(parse_scale_ratio(text) - expected) < 1e-3


@pytest.mark.parametrize("text,expected", [
    ('SCALE: 1" = 40\'-0"', 40.0),         # whole inch — untouched
    ('SCALE: 3" = 1\'-0"', 1.0 / 3.0),     # legit whole-inch detail scale
    ('SCALE: 1 1/2" = 1\'-0"', 2.0 / 3.0),  # mixed number — untouched
    ('SCALE: 1/8" = 1\'-0"', 8.0),         # literal slash still wins
])
def test_dropped_slash_repair_never_rewrites_a_valid_scale(text, expected):
    assert abs(parse_scale_ratio(text) - expected) < 1e-3


def test_parse_garbage_returns_none():
    assert parse_scale_ratio("OVERALL FLOOR PLAN") is None
    assert parse_scale_ratio("") is None
    assert parse_scale_ratio(None) is None


# ── Synthetic fitz page ───────────────────────────────────────────────────────


class _FakePage:
    """Minimal stand-in exposing get_text('blocks')."""

    def __init__(self, blocks):
        self._blocks = blocks

    def get_text(self, kind):  # noqa: D401
        if kind == "blocks":
            return self._blocks
        return []


def test_extract_printed_scales_two_blocks():
    # (x0, y0, x1, y1, text, block_no, block_type)
    blocks = [
        (2100, 1990, 2470, 2050,
         'SCALE: 1" = 40\'-0"  1  OVERALL FLOOR PLAN', 0, 0),
        (2180, 320, 2500, 380,
         'SCALE: 1 1/2" = 1\'-0"  2  TYP. S.C.C.P. MITERED CORNER', 1, 0),
    ]
    scales = extract_printed_scales(_FakePage(blocks))
    assert len(scales) == 2

    main = scales[0]
    assert main.feet_per_inch == 40.0
    assert abs(main.feet_per_point - 40.0 / 72.0) < 1e-9
    assert main.drawing_number == "1"
    assert "OVERALL FLOOR PLAN" in main.title.upper()
    assert main.center_pt == (2285.0, 2020.0)

    detail = scales[1]
    assert abs(detail.feet_per_inch - 0.6667) < 1e-3
    assert abs(detail.feet_per_point - detail.feet_per_inch / 72.0) < 1e-9
    assert detail.drawing_number == "2"
    assert "CORNER" in detail.title.upper()


def _vp(region_id, bbox, kind="unknown"):
    return Viewport(
        region_id=region_id, bbox_pt=bbox, kind=kind, detection_method="fallback"
    )


def test_match_label_inside_viewport_bbox():
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(300.0, 500.0), bbox_pt=(250.0, 480.0, 350.0, 520.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    inside = _vp("R1", (100.0, 100.0, 600.0, 600.0))
    other = _vp("R2", (700.0, 100.0, 900.0, 300.0))
    matched = match_scales_to_viewports([ps], [inside, other])
    assert matched == {"R1": ps}


def test_match_label_below_viewport_binds_above_region():
    # Label sits just BELOW the drawing (outside its bbox) — bind to the region
    # directly above it, not the far-away region.
    ps = PrintedScale(
        scale_text='1/4" = 1\'-0"', feet_per_inch=4.0, feet_per_point=4.0 / 72.0,
        center_pt=(300.0, 630.0), bbox_pt=(250.0, 615.0, 350.0, 645.0),
        drawing_number="3", title="ENLARGED PLAN",
    )
    above = _vp("R1", (100.0, 100.0, 500.0, 600.0))
    far = _vp("R2", (100.0, 1000.0, 500.0, 1400.0))
    matched = match_scales_to_viewports([ps], [above, far])
    assert list(matched.keys()) == ["R1"]


def test_match_skips_mask_kinds():
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(300.0, 300.0), bbox_pt=(250.0, 280.0, 350.0, 320.0),
        drawing_number="1", title="FLOOR PLAN",
    )
    title_block = _vp("R1", (0.0, 0.0, 600.0, 600.0), kind="title_block")
    drawing = _vp("R2", (100.0, 100.0, 500.0, 500.0), kind="main_plan")
    matched = match_scales_to_viewports([ps], [title_block, drawing])
    assert matched == {"R2": ps}


def test_identify_main_plan_prefers_overall_floor_plan():
    main = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(2285.0, 2020.0), bbox_pt=(2100.0, 1990.0, 2470.0, 2050.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    detail = PrintedScale(
        scale_text='1 1/2" = 1\'-0"', feet_per_inch=0.6667,
        feet_per_point=0.6667 / 72.0, center_pt=(2340.0, 348.0),
        bbox_pt=(2180.0, 320.0, 2500.0, 380.0), drawing_number="2",
        title="TYPICAL DETAIL",
    )
    chosen = identify_main_plan_scale([detail, main])
    assert chosen is main


def test_identify_main_plan_none_when_only_details():
    detail = PrintedScale(
        scale_text='1 1/2" = 1\'-0"', feet_per_inch=0.6667,
        feet_per_point=0.6667 / 72.0, center_pt=(0.0, 0.0),
        bbox_pt=(0.0, 0.0, 10.0, 10.0), drawing_number="2",
        title="TYPICAL S.C.C.P. JOINT DETAIL",
    )
    assert identify_main_plan_scale([detail]) is None


# ── Priority chain: printed label wins over RANSAC ────────────────────────────


def _solved(fpp, region="R1"):
    return ViewportScale(
        fpp=fpp, fpi=fpp * 72.0, confidence="high", n_inliers=10,
        inlier_share=0.9, printed_agreement=True, door_check=None,
        method="ransac_consensus",
    )


def test_printed_label_wins_over_ransac():
    vp = _vp("R1", (100.0, 100.0, 900.0, 900.0), kind="main_plan")
    # RANSAC solved a (deliberately different) value; printed label must win.
    solved = _solved(0.60)  # ~43.2 ft/in
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(500.0, 500.0), bbox_pt=(480.0, 480.0, 520.0, 520.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    result = resolve_scale_v2(
        page=None,
        viewports_with_scales=[(vp, solved)],
        printed_scales={"R1": ps},
    )
    assert isinstance(result, ScaleResult)
    assert result.method == "printed_label"
    assert result.confidence == "high"
    assert abs(result.feet_per_point - 40.0 / 72.0) < 1e-9
    # RANSAC disagreed > 5% -> cross-check note flags it but printed is kept.
    assert "needs_review" in result.detail


def test_printed_label_crosscheck_agrees():
    vp = _vp("R1", (100.0, 100.0, 900.0, 900.0), kind="main_plan")
    solved = _solved(40.0 / 72.0)  # agrees with the printed 40 ft/in
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(500.0, 500.0), bbox_pt=(480.0, 480.0, 520.0, 520.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    result = resolve_scale_v2(
        page=None, viewports_with_scales=[(vp, solved)], printed_scales={"R1": ps}
    )
    assert result.method == "printed_label"
    assert "agrees" in result.detail
    assert "needs_review" not in result.detail


def test_no_printed_label_uses_ransac_unchanged():
    vp = _vp("R1", (100.0, 100.0, 900.0, 900.0), kind="main_plan")
    solved = _solved(0.60)
    # No printed_scales / main_plan_scale supplied -> RANSAC dimension solve.
    result = resolve_scale_v2(page=None, viewports_with_scales=[(vp, solved)])
    assert result.method == "dimension_solve"
    assert abs(result.feet_per_point - 0.60) < 1e-9


def test_override_still_outranks_printed_label():
    vp = _vp("R1", (100.0, 100.0, 900.0, 900.0), kind="main_plan")
    solved = _solved(0.60)
    ps = PrintedScale(
        scale_text='1" = 40\'-0"', feet_per_inch=40.0, feet_per_point=40.0 / 72.0,
        center_pt=(500.0, 500.0), bbox_pt=(480.0, 480.0, 520.0, 520.0),
        drawing_number="1", title="OVERALL FLOOR PLAN",
    )
    result = resolve_scale_v2(
        page=None, viewports_with_scales=[(vp, solved)],
        override_feet_per_inch=48.0, printed_scales={"R1": ps},
    )
    assert result.method == "override"
    assert abs(result.feet_per_point - 48.0 / 72.0) < 1e-9
