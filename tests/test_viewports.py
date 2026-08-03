"""Viewport kind assignment — a drawing that MENTIONS a schedule is not one.

The real-PDF assertions here are the ones that matter. `schedule` and `legend`
sit in BOTH ``takeoff_pipeline._MASK_VIEWPORT_KINDS`` and
``printed_scale._MASK_KINDS``, so one wrong kind masks a drawing's geometry out
of every measurement AND bars it from owning a printed scale — and one wrong
promotion in the other direction lets a table's ruled grid into wall
extraction (T-23-40). Both directions are pinned below on the real fixtures.
"""
from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from bobbytailor.deterministic.printed_scale import (
    extract_printed_scales,
    match_scales_to_viewports,
)
from bobbytailor.deterministic.viewports import (
    TITLE_BAND_OUT_PT,
    _title_band,
    segment_viewports,
)

FIXTURES = Path(__file__).parent / "fixtures"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"
BOBS_PDF = FIXTURES / "bobs_discount" / "bobs_discount_plans.pdf"

MASK_KINDS = ("title_block", "legend", "schedule")

# INV-06 §1.5: the region that holds four of the five estimator rail marks.
STAIR_PLAN_BBOX = (1428.0, 755.0, 1921.0, 1374.0)

# INV-06 §1.3: the estimator's own rail measurement polylines, read out of the
# take-off PDF's coloured markup. An ANSWER KEY, never pipeline input.
RAIL_MARKS = (
    (273.0, 167.0, 1229.0, 167.0),
    (1771.0, 869.0, 1771.0, 1168.0),
    (1607.0, 870.0, 1607.0, 1169.0),
    (1783.0, 937.0, 1783.0, 1315.0),
    (1591.0, 936.0, 1591.0, 1315.0),
)


def _region_near(viewports, bbox, tol=30.0):
    for vp in viewports:
        if all(abs(a - b) <= tol for a, b in zip(vp.bbox_pt, bbox)):
            return vp
    return None


@pytest.fixture(scope="module")
def crow_page2():
    doc = fitz.open(CROW_PDF)
    page = doc[2]
    vps = segment_viewports(page)
    printed = extract_printed_scales(page)
    by_region = match_scales_to_viewports(printed, vps, page=page)
    yield page, vps, printed, by_region
    doc.close()


# ── The drawing that mentions a schedule ─────────────────────────────────────


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_the_stair_plan_region_is_not_a_schedule(crow_page2):
    """It was one purely because it contains 'SEE CONC. DOOR OPENING SCHEDULE'."""
    _page, vps, _printed, _by = crow_page2
    region = _region_near(vps, STAIR_PLAN_BBOX)
    assert region is not None, "INV-06's region is no longer segmented"
    assert "SCHEDULE" in region.title_text.upper(), (
        "the in-drawing note that used to rename this drawing must still be "
        "inside it — otherwise this test is asserting nothing"
    )
    assert region.kind != "schedule"
    assert region.kind not in MASK_KINDS
    assert region.printed_fpi == pytest.approx(2.0)


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_the_stair_plan_label_now_binds_to_that_region(crow_page2):
    _page, vps, printed, by_region = crow_page2
    region = _region_near(vps, STAIR_PLAN_BBOX)
    bound = by_region.get(region.region_id)
    assert bound is not None
    assert bound.title == "STAIR PLAN"
    assert bound.feet_per_inch == pytest.approx(2.0)


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_every_estimator_rail_mark_sits_in_a_measurable_scaled_viewport(
    crow_page2,
):
    """The whole point: all five marks are now reachable AND scaled.

    Four are in the STAIR PLAN region at 1/2" = 1'-0" and the fifth is in the
    ENLARGED RAMP PLAN region at 1/4" = 1'-0" — exactly the two scales INV-06
    §1.3 measured them at.
    """
    _page, vps, _printed, by_region = crow_page2
    seen = set()
    for x0, y0, x1, y1 in RAIL_MARKS:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        owners = [
            vp for vp in vps
            if vp.bbox_pt[0] <= cx <= vp.bbox_pt[2]
            and vp.bbox_pt[1] <= cy <= vp.bbox_pt[3]
        ]
        assert owners, "rail mark (%s,%s) sits in no viewport" % (cx, cy)
        owner = min(
            owners,
            key=lambda vp: (vp.bbox_pt[2] - vp.bbox_pt[0])
            * (vp.bbox_pt[3] - vp.bbox_pt[1]),
        )
        assert owner.kind not in MASK_KINDS, (
            "rail mark (%s,%s) is masked out of measurement by kind %r"
            % (cx, cy, owner.kind)
        )
        scale = by_region.get(owner.region_id)
        assert scale is not None, (
            "rail mark (%s,%s) is in a viewport with no printed scale"
            % (cx, cy)
        )
        seen.add(round(scale.feet_per_inch, 4))
    assert seen == {2.0, 4.0}


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_crow_page2_unbound_label_count(crow_page2):
    """4 -> 3, and the residual 3 is NOT this module's to fix.

    ``match_scales_to_viewports`` keeps at most ONE label per region, and Crow
    page 2 draws 13 captioned details into 11 non-title-block regions, so two
    labels cannot bind by pigeonhole alone. The third is lost because a caption
    sitting a few points ABOVE a region's top edge passes that region's
    symmetric 6 pt containment margin: R4's top is 623 and RAMP RAIL SECTION's
    caption is at y 620, R12's top is 1450 and Z-GUARD DETAIL's is at y 1445.
    Both live in ``printed_scale``, which this plan does not touch.
    """
    _page, vps, printed, by_region = crow_page2
    bound = {id(ps) for ps in by_region.values()}
    unbound = [ps.title for ps in printed if id(ps) not in bound]
    assert "STAIR PLAN" not in unbound
    assert len(unbound) == 3
    assert len(printed) == 13
    assert len([vp for vp in vps if vp.kind != "title_block"]) == 11


# ── The other direction: a table stays a table (T-23-40) ─────────────────────


def _table_page(doc, *, with_caption_scale=False, caption="DOOR SCHEDULE"):
    """A ruled table with its heading, optionally captioned like a drawing."""
    page = doc.new_page(width=800, height=800)
    page.insert_text(fitz.Point(120, 100), caption, fontsize=14)
    for i in range(14):
        y = 130 + i * 20
        page.draw_line(fitz.Point(100, y), fitz.Point(700, y), width=0.5)
    for i in range(9):
        x = 100 + i * 75
        page.draw_line(fitz.Point(x, 130), fitz.Point(x, 390), width=0.5)
    if with_caption_scale:
        page.insert_text(
            fitz.Point(300, 390 + TITLE_BAND_OUT_PT / 2.0),
            'SCALE: 1/4" = 1\'-0"',
            fontsize=12,
        )
    return page


def test_a_ruled_table_with_no_printed_scale_is_still_a_schedule():
    doc = fitz.open()
    page = _table_page(doc)
    vps = segment_viewports(page)
    doc.close()
    assert any(vp.kind == "schedule" for vp in vps), [
        (vp.kind, vp.title_text) for vp in vps
    ]


def test_a_scale_alone_does_not_release_a_table():
    """The rule INV-06 proposed is falsified on all four real fixtures.

    Five genuine schedule regions own a printed scale from the proximity halo
    they share with a neighbouring detail — Crow p1 GLASS SCHEDULE at 20 ft/in,
    Bob's A8.1 door schedule at 2.67, Chelsea p0 at 0.33 and two Moxy p15
    regions at 4.0. Releasing on that evidence alone put 429 LF of Bob's
    door-schedule grid into wall extraction (T-23-40).
    """
    doc = fitz.open()
    page = _table_page(doc, with_caption_scale=True)
    vps = segment_viewports(page)
    doc.close()
    tables = [vp for vp in vps if "SCHEDULE" in vp.title_text.upper()]
    assert tables
    # Non-vacuity: the table really does own a scale here.
    assert any(vp.printed_fpi is not None for vp in tables), [
        (vp.kind, vp.title_text, vp.printed_fpi) for vp in tables
    ]
    assert all(vp.kind == "schedule" for vp in tables), [
        (vp.kind, vp.title_text, vp.printed_fpi) for vp in tables
    ]


@pytest.mark.skipif(not BOBS_PDF.is_file(), reason="Bob's PDF fixture missing")
def test_bobs_door_schedule_sheet_keeps_its_schedule_regions():
    """A8.1 is a schedule sheet; its tables must not become drawings."""
    doc = fitz.open(BOBS_PDF)
    vps = segment_viewports(doc[5])
    doc.close()
    assert any(vp.kind == "schedule" for vp in vps), [
        (vp.region_id, vp.kind, vp.printed_fpi) for vp in vps
    ]


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_crow_page1_glass_schedule_stays_a_table_despite_owning_a_scale():
    doc = fitz.open(CROW_PDF)
    vps = segment_viewports(doc[1])
    doc.close()
    tables = [vp for vp in vps if "SCHEDULE" in vp.title_text.upper()]
    assert tables, "Crow page 1 no longer has a SCHEDULE-titled region"
    assert all(vp.kind in MASK_KINDS for vp in tables), [
        (vp.region_id, vp.kind, vp.printed_fpi) for vp in tables
    ]


# ── The title band itself ────────────────────────────────────────────────────


def test_the_title_band_hugs_the_bottom_edge():
    band = _title_band((100.0, 200.0, 400.0, 600.0), None)
    assert band[1] < 600.0 < band[3]
    assert band[3] - 600.0 == pytest.approx(TITLE_BAND_OUT_PT)
    assert band[0] < 100.0 and band[2] > 400.0


def test_the_title_band_is_taken_in_page_space_on_a_rotated_sheet():
    """A /Rotate 270 sheet's caption is where a reader sees it, not where the
    unrotated content stream puts it."""
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    page.set_rotation(270)
    rotated = _title_band((100.0, 200.0, 400.0, 500.0), page)
    upright = _title_band((100.0, 200.0, 400.0, 500.0), None)
    doc.close()
    assert rotated != upright


def test_an_unrotated_page_takes_the_identity_path():
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    same = _title_band((100.0, 200.0, 400.0, 500.0), page)
    doc.close()
    assert same == _title_band((100.0, 200.0, 400.0, 500.0), None)
