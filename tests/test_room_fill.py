"""Enclosed-region room measurement (Recipe E) — offline, ZERO API.

Synthetic fixtures with a KNOWN answer: a room drawn at a known scale must
measure its known area. Pins the contract that made this engine necessary —
the vector room engine returns 17 SF fragments where the room is 353 SF because
the drawing has no closed room path, so a room must be found as a region
enclosed by ink, not as a polygon in the file.
"""
from __future__ import annotations

import fitz
import pytest

from bobbytailor.deterministic.room_fill import (
    MAX_REGION_SF,
    RoomFillResult,
    flag_implausible_unit,
    from_page_space,
    measure_enclosed_area,
    select_fill_for_basis,
    to_page_space,
    total_for_units,
)

# 1/4" = 1'-0"  ->  4 ft per inch  ->  4/72 ft per point (Moxy's guestroom scale)
FPP_QUARTER = 4.0 / 72.0


def _page_with_room(width_ft, height_ft, fpp=FPP_QUARTER, wall_pt=2.0, inner=None):
    """A page holding one rectangular room of a known size, drawn as strokes.

    Walls are STROKES (not a closed filled path) — the Moxy style that defeats
    centerline polygonization — so the fill is doing the real work.
    """
    doc = fitz.open()
    page = doc.new_page(width=800, height=800)
    w_pt, h_pt = width_ft / fpp, height_ft / fpp
    x0, y0 = 100.0, 100.0
    x1, y1 = x0 + w_pt, y0 + h_pt
    # four separate strokes — deliberately NOT a closed path
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                 ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        page.draw_line(fitz.Point(*a), fitz.Point(*b), width=wall_pt)
    if inner:  # an interior partition splitting off a sub-room (a bathroom)
        ix = x0 + inner / fpp
        page.draw_line(fitz.Point(ix, y0), fitz.Point(ix, y1), width=wall_pt)
    return doc, page, fitz.Rect(x0 - 40, y0 - 40, x1 + 40, y1 + 40)


# ── page-space transform (23-07 / SP-1 / INV-03 §4.2) ───────────────────────
#
# page.get_text and page.get_drawings answer in the UNROTATED mediabox; the
# rasteriser's clip and every "above/below" judgement live in page.rect. On the
# real fixtures those are the same space on 76 of 83 pages and 90 degrees apart
# on the other 7, which is why the bug stayed invisible for so long.


def _rotated_page(rot, width=600, height=800):
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.set_rotation(rot)
    return doc, page


_UNROTATED_CASES = [
    fitz.Rect(100, 200, 300, 500),
    fitz.Rect(0, 0, 600, 800),       # the whole page
    fitz.Rect(0, 0, 10, 10),         # touching the top-left page edge
    fitz.Rect(590, 790, 600, 800),   # touching the bottom-right page edge
]


@pytest.mark.parametrize("rect", _UNROTATED_CASES)
def test_to_page_space_is_the_identity_on_an_unrotated_page(rect):
    """76 of the 83 pages across the four real fixtures are unrotated.

    They must take a LITERALLY unchanged path, not an equal-valued one — this
    is the whole safety argument for a transform applied at three consumer
    sites at once (T-23-26). The caller's own object is handed back.
    """
    doc, page = _rotated_page(0)
    out = to_page_space(page, rect)
    assert out == rect
    assert out is rect, "the unrotated path must not even rebuild the rectangle"
    doc.close()


def test_to_page_space_maps_the_hand_computed_corners_at_90_degrees():
    """rot 90 sends (x, y) -> (mediabox_height - y, x)."""
    doc, page = _rotated_page(90)
    assert tuple(page.rect) == (0.0, 0.0, 800.0, 600.0)
    # corners (100,200) and (300,500) -> (800-200, 100) and (800-500, 300)
    #      = (600, 100) and (300, 300), normalised to (300, 100, 600, 300)
    out = to_page_space(page, fitz.Rect(100, 200, 300, 500))
    assert tuple(out) == (300.0, 100.0, 600.0, 300.0)
    assert out.x0 <= out.x1 and out.y0 <= out.y1, "the result is normalised"
    doc.close()


def test_to_page_space_maps_the_hand_computed_corners_at_270_degrees():
    """rot 270 sends (x, y) -> (y, mediabox_width - x). Bob's rotation."""
    doc, page = _rotated_page(270)
    assert tuple(page.rect) == (0.0, 0.0, 800.0, 600.0)
    # corners (100,200) and (300,500) -> (200, 600-100) and (500, 600-300)
    #      = (200, 500) and (500, 300), normalised to (200, 300, 500, 500)
    out = to_page_space(page, fitz.Rect(100, 200, 300, 500))
    assert tuple(out) == (200.0, 300.0, 500.0, 500.0)
    assert out.x0 <= out.x1 and out.y0 <= out.y1
    doc.close()


@pytest.mark.parametrize("rot", [90, 270])
def test_a_rotation_preserves_area_and_lands_inside_the_displayed_page(rot):
    """A rotation is rigid: the region measured is the region asked for.

    This is T-23-25's mitigation — a crafted /Rotate cannot make the clip name
    a bigger region than the caller did.
    """
    doc, page = _rotated_page(rot)
    for rect in _UNROTATED_CASES:
        out = to_page_space(page, rect)
        assert (out.x1 - out.x0) * (out.y1 - out.y0) == pytest.approx(
            (rect.x1 - rect.x0) * (rect.y1 - rect.y0)
        )
        assert out in page.rect or page.rect.intersect(out) == out, (
            "the mapped clip stays on the displayed page"
        )
    doc.close()


@pytest.mark.parametrize("rot", [0, 90, 180, 270])
def test_from_page_space_is_the_exact_inverse(rot):
    doc, page = _rotated_page(rot)
    for rect in _UNROTATED_CASES:
        assert tuple(from_page_space(page, to_page_space(page, rect))) == tuple(rect)
    doc.close()


def test_the_transform_never_raises_on_a_page_that_cannot_answer():
    """A test stub or a defective file must degrade to today's behaviour."""
    class _Stub:
        pass

    class _Liar:
        rotation = 90
        rotation_matrix = "not a matrix"
        derotation_matrix = None

    rect = fitz.Rect(1, 2, 3, 4)
    assert to_page_space(_Stub(), rect) is rect
    assert to_page_space(_Liar(), rect) is rect
    assert from_page_space(_Liar(), rect) is rect
    assert to_page_space(None, rect) is rect


def test_the_raster_clip_renders_the_named_region_on_a_rotated_page():
    """The engine's own bug, on a synthetic page with a known answer.

    A 20' x 15' room is drawn at 1/4"=1'-0" and the page is then rotated 90
    degrees. The clip is in drawing space, exactly as every caller's is. Before
    this change the raw rectangle went to the rasteriser and the room was lost;
    the measurement must now be the same 300 SF the unrotated page yields,
    because rotating the sheet does not resize the room.
    """
    doc, page, clip = _page_with_room(20.0, 15.0)
    flat = measure_enclosed_area(page, clip, FPP_QUARTER)
    assert flat is not None and flat.area_sf == pytest.approx(300.0, rel=0.06)
    page.set_rotation(90)
    turned = measure_enclosed_area(page, clip, FPP_QUARTER)
    assert turned is not None, "a rotated sheet measured NOTHING before this change"
    assert turned.area_sf == pytest.approx(flat.area_sf, rel=0.02)
    doc.close()


def test_measures_a_known_room_area():
    """20' x 15' = 300 SF, drawn at 1/4" = 1'-0"."""
    doc, page, clip = _page_with_room(20.0, 15.0)
    r = measure_enclosed_area(page, clip, FPP_QUARTER, candidate_id="R1")
    assert r is not None
    assert r.area_sf == pytest.approx(300.0, rel=0.06)
    assert r.candidate_id == "R1"
    assert r.scale_fpi == pytest.approx(4.0, rel=1e-3)
    doc.close()


def test_sums_every_enclosed_region_not_just_the_biggest():
    """A unit's ceiling covers bedroom + bathroom. Filling from one seed stops
    at the partition and lands a systematic ~30% under — the exact error this
    engine was built to remove."""
    doc, page, clip = _page_with_room(20.0, 15.0, inner=6.0)  # split into 6' + 14'
    r = measure_enclosed_area(page, clip, FPP_QUARTER)
    assert r is not None
    assert len(r.regions) >= 2, "both sub-rooms must be found"
    # total still ~300 SF (minus the partition's own ink)
    assert r.area_sf == pytest.approx(300.0, rel=0.08)
    assert r.area_sf > max(r.regions), "the sum must exceed the largest single room"
    doc.close()


def test_scale_drives_the_area_and_is_never_assumed():
    """Area scales by the SQUARE: the same drawing at 1/8" is 4x the area.
    Measuring a sheet at an assumed project scale is how Moxy lost every room."""
    # 12' x 10' = 120 SF at 1/4"; the same ink reads 480 SF at 1/8" — both stay
    # inside the plausible-room band so the guard is not what is being tested.
    doc, page, clip = _page_with_room(12.0, 10.0)
    quarter = measure_enclosed_area(page, clip, FPP_QUARTER)
    eighth = measure_enclosed_area(page, clip, 8.0 / 72.0)
    assert quarter and eighth
    assert quarter.area_sf == pytest.approx(120.0, rel=0.08)
    assert eighth.area_sf == pytest.approx(4.0 * quarter.area_sf, rel=0.02)
    doc.close()


def test_outside_region_is_discarded():
    """The region touching the clip edge is the OUTSIDE, never a room."""
    doc, page, clip = _page_with_room(20.0, 15.0)
    r = measure_enclosed_area(page, clip, FPP_QUARTER)
    assert r is not None
    # 300 SF room only — the surrounding page is not counted
    assert r.area_sf < 400.0
    doc.close()


def test_no_enclosed_region_returns_none():
    """An empty page has nothing enclosed — callers keep prior behaviour."""
    doc = fitz.open()
    page = doc.new_page(width=400, height=400)
    assert measure_enclosed_area(page, fitz.Rect(0, 0, 400, 400), FPP_QUARTER) is None
    doc.close()


def test_zero_or_missing_scale_returns_none():
    doc, page, clip = _page_with_room(20.0, 15.0)
    assert measure_enclosed_area(page, clip, 0.0) is None
    assert measure_enclosed_area(page, clip, None) is None
    doc.close()


# ── flag-don't-guess ─────────────────────────────────────────────────────────


def test_oversize_unit_is_flagged_never_silently_halved():
    """A clip overlapping the neighbouring opposite-hand plan measures TWO units
    and reports ~2x (real: Moxy ID-412 = 458 SF vs 231). Halving it would be a
    guess, so it is FLAGGED for the human instead."""
    r = RoomFillResult(area_sf=458.3, regions=[292.0, 64.0, 63.0], candidate_id="ID-412-RCP")
    out = flag_implausible_unit(r, expect_max_sf=420.0)
    assert out.needs_review is True
    assert out.area_sf == 458.3, "the measurement is preserved, never rewritten"
    assert "verify" in out.review_reason.lower()


def test_plausible_unit_is_not_flagged():
    r = RoomFillResult(area_sf=341.7, regions=[217.0, 38.0], candidate_id="ID-411-RCP")
    out = flag_implausible_unit(r, expect_max_sf=420.0)
    assert out.needs_review is False
    assert out.review_reason == ""


# ── prototype-unit x count ───────────────────────────────────────────────────


def test_total_for_units_multiplies_measured_area_by_the_room_mix():
    """Moxy ID-413: one QQ A measured 272.6 SF x 90 units in the mix."""
    assert total_for_units(272.6, 90) == pytest.approx(24534.0, rel=1e-3)


def test_total_for_units_without_a_count_returns_the_single_unit():
    """No count supplied -> the measured area stands alone (never zeroed)."""
    assert total_for_units(272.6, None) == pytest.approx(272.6)
    assert total_for_units(272.6, 0) == pytest.approx(272.6)


def test_max_region_guard_rejects_sheet_scale_regions():
    """A region larger than any plausible unit is not a room."""
    doc, page, clip = _page_with_room(60.0, 40.0)  # 2400 SF — sheet-scale
    r = measure_enclosed_area(page, clip, FPP_QUARTER, max_region_sf=MAX_REGION_SF)
    assert r is None
    doc.close()


# ── the oversize rejection leaves a trace (23-03 / INV-08 §4 step 7) ─────────


def test_oversize_rejection_is_recorded_when_an_out_list_is_supplied():
    """The rejection is CORRECT and, until now, invisible.

    A 2,400 SF region silently discarded and a drawing that measured nothing
    are the same `None` to every caller, so the ledger could never say *"one
    region of 2,400 SF was rejected as larger than one unit"*. Recording it is
    in scope; MOVING the threshold to make it pass is the coincidence trap
    INV-08 risk 6 forbids, and the constant is asserted untouched below.
    """
    # 40' x 30' = 1,200 SF at 1/8" = 1'-0". Drawn at EIGHTH so the whole region
    # fits on the page and is genuinely ENCLOSED — the pre-existing 60x40-at-
    # quarter fixture overflows an 800 pt page, so its region touches the clip
    # edge and is discarded as the outside before the size filter is reached.
    fpp_eighth = 8.0 / 72.0
    doc, page, clip = _page_with_room(40.0, 30.0, fpp=fpp_eighth)
    dropped = []
    r = measure_enclosed_area(
        page, clip, fpp_eighth, max_region_sf=MAX_REGION_SF,
        dropped_regions=dropped,
    )
    assert r is None, "the return value is unchanged by observing the drop"
    assert len(dropped) == 1
    assert dropped[0] > MAX_REGION_SF
    assert dropped[0] == pytest.approx(1200.0, rel=0.08)
    doc.close()


def test_the_out_list_is_optional_and_changes_nothing():
    """Passing the list must not perturb a measurement that succeeds."""
    doc, page, clip = _page_with_room(20.0, 15.0)
    without = measure_enclosed_area(page, clip, FPP_QUARTER, candidate_id="R1")
    dropped = []
    with_list = measure_enclosed_area(
        page, clip, FPP_QUARTER, candidate_id="R1", dropped_regions=dropped,
    )
    assert without is not None and with_list is not None
    assert with_list.to_dict() == without.to_dict()
    assert dropped == [], "nothing was oversize, so nothing is reported oversize"
    doc.close()


def test_a_region_below_the_minimum_is_not_reported_as_oversize():
    """MIN and MAX are different rejections. A fixture outline is not a room
    that was too big; conflating them would make the ledger lie."""
    doc, page, clip = _page_with_room(20.0, 15.0)
    dropped = []
    r = measure_enclosed_area(
        page, clip, FPP_QUARTER, min_region_sf=1000.0, dropped_regions=dropped,
    )
    assert r is None
    assert dropped == []
    doc.close()


def test_the_size_constant_is_untouched():
    """INV-08 risk 6 / §14.2: fix the clip, not the threshold."""
    assert MAX_REGION_SF == 900.0


# ── flag-don't-drop in the selector (23-03 / INV-08 §2 rows S8-S9) ───────────


def _fill(kind, area, needs_review=False, name="KING A"):
    return RoomFillResult(
        area_sf=area, candidate_id="FILL-%s-%.0f" % (kind, area),
        plan_kind=kind, plan_name=name, needs_review=needs_review,
        review_reason="flagged" if needs_review else "",
    )


def test_a_flagged_fill_is_returned_with_its_flag_not_dropped():
    """`and not f.needs_review` made a flagged fill VANISH.

    A discipline whose every drawing was flagged returned None, the caller
    `continue`d, and the row disappeared — flag-don't-guess degrading into
    drop-and-be-silent, which is exactly what this function's own docstring
    says must never happen.
    """
    fills = [_fill("RCP", 458.5, needs_review=True)]
    pick = select_fill_for_basis(fills, "ceiling_area")
    assert pick is not None, "a flagged measurement is still a measurement"
    assert pick.needs_review is True, "the flag must survive the selection"
    assert pick.area_sf == 458.5, "the number is never rewritten"


def test_an_unflagged_candidate_still_wins_over_a_flagged_one():
    """Existing behaviour preserved: the clean measurement is preferred."""
    fills = [_fill("RCP", 229.4), _fill("RCP", 200.0, needs_review=True)]
    pick = select_fill_for_basis(fills, "ceiling_area")
    assert pick.needs_review is False
    assert pick.area_sf == 229.4, (
        "the smallest-of-the-unflagged rule must not reach across the flag"
    )


def test_the_smallest_of_several_flagged_candidates_is_taken():
    """Same opposite-hand rule as before: the larger spans both units."""
    fills = [_fill("RCP", 458.5, needs_review=True),
             _fill("RCP", 231.0, needs_review=True)]
    assert select_fill_for_basis(fills, "ceiling_area").area_sf == 231.0


def test_the_wrong_discipline_is_still_never_substituted():
    """A ceiling comes off the RCP. Returning the AR plan's area would be a
    guess, and no amount of flagging makes a guess acceptable."""
    assert select_fill_for_basis([_fill("AR", 300.0)], "ceiling_area") is None
    assert select_fill_for_basis([_fill("RCP", 300.0)], "floor_area") is None


def test_the_discipline_mapping_is_unchanged():
    """23-13 owns any change here; this plan must not move it."""
    from bobbytailor.deterministic.room_fill import BASIS_PLAN_KIND
    assert BASIS_PLAN_KIND == {
        "ceiling_area": "RCP",
        "roof_area": "RCP",
        "floor_area": "AR",
        "wall_area": "AR",
        "area": "AR",
    }


def test_an_unknown_basis_still_selects_nothing():
    assert select_fill_for_basis([_fill("RCP", 300.0)], "linear") is None
    assert select_fill_for_basis([_fill("RCP", 300.0)], "") is None
