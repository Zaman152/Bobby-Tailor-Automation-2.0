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
    EXTENT_TOLERANCE,
    MAX_HONEST_SHAPE_RATIO,
    MAX_REGION_SF,
    RoomFillResult,
    cross_check_extent,
    drawing_ceiling_heights,
    from_page_space,
    label_mask,
    measure_enclosed_area,
    printed_extent_bound,
    resolve_drawing_height,
    select_fill_for_basis,
    to_page_space,
    total_for_units,
    wall_area_for_unit,
    wall_perimeter_for_unit,
)

# 1/4" = 1'-0"  ->  4 ft per inch  ->  4/72 ft per point (Moxy's guestroom scale)
FPP_QUARTER = 4.0 / 72.0

MOXY_PDF = "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"


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


# ── the title-to-scale adjacency is a PAGE-space question (23-07 Task 2) ─────


def _sheet_reading_upright(rot, page_pt=800.0):
    """One titled, scaled drawing whose PAGE-space layout is fixed at *rot*.

    A sheet that displays upright at ``/Rotate 90`` is AUTHORED sideways in the
    mediabox — that is Moxy pages 7-17, and it is why ``page.get_text`` reports
    a title as a tall narrow box while a reader sees a wide one. Both fixtures
    here put the room, the title and the callout at IDENTICAL page-space
    coordinates, so any difference in what they measure is a coordinate-space
    defect and nothing else.
    """
    doc = fitz.open()
    page = doc.new_page(width=page_pt, height=page_pt)

    def draw(px, py):
        """A page-space point, expressed in the mediabox this page authors in."""
        return (py, page_pt - px) if rot == 90 else (px, py)

    # A 20' x 15' room at 1/4" = 1'-0"  ->  360 x 270 pt, as four strokes.
    corners = [(100, 100), (460, 100), (460, 370), (100, 370)]
    pts = [fitz.Point(*draw(*c)) for c in corners]
    for a, b in zip(pts, pts[1:] + pts[:1]):
        page.draw_line(a, b, width=2.0)
    page.insert_text(fitz.Point(*draw(150, 400)), "LOBBY - AR PLAN",
                     fontsize=12, rotate=rot)
    page.insert_text(fitz.Point(*draw(150, 420)), '1/4" = 1\'-0"',
                     fontsize=10, rotate=rot)
    page.set_rotation(rot)
    return doc, page


def _fills(page):
    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    return pipe._measure_room_fills(page, [], {}, "SYNTH")


def test_the_same_sheet_measures_the_same_whether_it_is_rotated():
    """Rotating a sheet does not resize the room it draws.

    Before this change the adjacency gap was computed as callout-centre minus
    title-bottom in UNROTATED y. On a page rotated 90 degrees that is a large
    negative number, the guard rejects it, no scale binds and the drawing is
    skipped entirely — real consequence: Moxy pages 9 and 13 returned ZERO room
    fills.
    """
    flat_doc, flat = _sheet_reading_upright(0)
    turned_doc, turned = _sheet_reading_upright(90)
    flat_fills, flat_drops = _fills(flat)
    turned_fills, turned_drops = _fills(turned)

    assert len(flat_fills) == 1, "the control fixture must measure"
    assert len(turned_fills) == 1, (
        "the rotated sheet measured NOTHING before this change: %r"
        % ([d.reason for d in turned_drops],)
    )
    assert turned_fills[0].viewport_title == flat_fills[0].viewport_title
    assert turned_fills[0].scale_fpi == flat_fills[0].scale_fpi == pytest.approx(4.0)
    assert turned_fills[0].area_sf == pytest.approx(flat_fills[0].area_sf, rel=0.02)
    assert turned_fills[0].area_sf == pytest.approx(300.0, rel=0.06)
    assert not turned_drops and not flat_drops
    flat_doc.close()
    turned_doc.close()


def test_the_adjacency_tolerance_is_not_what_was_changed():
    """The defect was the coordinate space, not the guard's tolerance.

    Widening the tolerance would have "fixed" Moxy by letting a callout that
    sits ABOVE a title bind to it — which would move unrotated sheets and bind
    the wrong scale. Both constants are pinned.
    """
    from bobbytailor.pipeline import takeoff_pipeline as tp

    assert tp._TITLE_SCALE_ABOVE_TOL_PT == -6.0
    assert tp._TITLE_SCALE_SIDE_PT == 260.0
    assert tp.TakeoffPipeline._FILL_CLIP_UP_PT == 620.0


@pytest.mark.parametrize("rot", [0, 90])
def test_the_skip_veto_oracle_cannot_drift_from_the_engine_it_measures(rot):
    """`page_measurable_signal` binds a title to a callout by the SAME rule.

    Its own comment says so — *"one definition, so the oracle cannot drift
    from the thing it is the oracle for"* — and moving only the engine into
    page space would have broken exactly that: the ledger would report ZERO
    measurable drawings on a Moxy lobby sheet the engine now measures at 743
    SF, and the skip veto would let the classifier discard it. A silent zero
    wearing a coverage number.
    """
    from bobbytailor.pipeline.takeoff_pipeline import page_measurable_signal

    doc, page = _sheet_reading_upright(rot)
    assert page_measurable_signal(page)["plan_titles"] == len(_fills(page)[0]) == 1
    doc.close()


def test_the_region_bound_is_threaded_and_defaults_to_the_module_constant():
    """23-11 and 23-14 measure things that are not guest rooms.

    They must be able to pass their own bound instead of editing a constant
    every other caller shares — and the default must stay exactly today's, so
    this plan moves no measurement.
    """
    import inspect

    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    param = inspect.signature(
        TakeoffPipeline._measure_room_fills
    ).parameters["max_region_sf"]
    assert param.default == MAX_REGION_SF

    doc, page = _sheet_reading_upright(0)
    clean_fills, clean_drops = _fills(page)
    assert len(clean_fills) == 1
    assert not clean_drops
    # This fixture draws a room and a scale but NO dimension string, so since
    # 23-11 it is flagged for exactly one reason: the drawing does not say how
    # big it is, and a check that cannot run must say so rather than pass
    # silently. The oversize bound has not fired.
    assert "no overall dimension pair" in clean_fills[0].review_reason
    assert "KEPT AND FLAGGED" not in clean_fills[0].review_reason
    # A bound below the room's own area now FLAGS it rather than deleting it
    # (23-09) — proof the argument reaches measure_enclosed_area rather than
    # being decorative, without reintroducing the silent zero.
    tight_fills, tight_drops = TakeoffPipeline(
        analyzer=lambda *a, **k: {}
    )._measure_room_fills(page, [], {}, "SYNTH", max_region_sf=50.0)
    assert len(tight_fills) == 1, "a tighter bound flags, it does not delete"
    assert tight_fills[0].area_sf == clean_fills[0].area_sf
    assert tight_fills[0].needs_review is True
    assert "KEPT AND FLAGGED" in tight_fills[0].review_reason
    assert tight_drops and "larger than one unit" in tight_drops[0].reason
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


def test_the_measured_area_is_checked_against_the_drawings_own_printed_extent():
    """Moxy ID-412, with the story corrected (D-01; INV-02 §2, §3, §4).

    The superseded test here asserted that 458.3 SF was ~2x because the clip had
    reached the neighbouring opposite-hand plan, and pinned a fabricated 420 SF
    cap to "prove" it. Three probes falsified that:

      * INV-02 §3 — ID-412 is bit-identical across a 240 pt range of clip widths
        while ID-407 and ID-415 move +17% and +20%, so the two "defective"
        sheets are the LEAST clip-sensitive of all sixteen, not the most;
      * INV-02 §2 — every counted region sits inside 47% of the clip, so nothing
        from a neighbour is inside it;
      * INV-02 §4 — the drawing's OWN printed 17'-0 1/8" x 26'-9 1/8" = 455.2 SF
        matches the fill at a ratio of 1.007.

    The fill was right; the ~2x came from a room-mix `unit_count` of 2 one layer
    later, derived from a golden `Doors-WD 2 EA` that is really a suite's entry
    door plus its connecting door (INV-02 §4). The corresponding correction to
    `docs/PIPELINE-GROUND-TRUTH.md` §14.2 landed in plan 23-16.

    So the cross-check is against the drawing's own statement of its size, and
    BOTH directions are asserted here: 455.2 vs 458.3 must NOT be flagged, and a
    fill of roughly twice that bound MUST be.
    """
    r = RoomFillResult(area_sf=458.3, regions=[292.0, 64.0, 63.0],
                       candidate_id="ID-412-RCP")
    out = cross_check_extent(r, 455.2)
    assert out.needs_review is False
    assert out.review_reason == ""
    assert out.bound_sf == 455.2
    assert out.extent_ratio == pytest.approx(1.007, abs=0.001)

    # ...and the other direction, in the same test, because the check is only
    # meaningful if it discriminates: a genuine two-plan leak reads ~2.0.
    leak = cross_check_extent(
        RoomFillResult(area_sf=916.6, regions=[584.0, 128.0],
                       candidate_id="ID-412-RCP-LEAK"),
        455.2,
    )
    assert leak.needs_review is True
    assert leak.extent_ratio == pytest.approx(2.014, abs=0.001)


def test_a_fill_of_twice_its_printed_extent_is_flagged_never_halved():
    """The genuine two-plan leak this check exists for — ~2.0, not ~1.0.

    458.3 x 2 against the same 455.2 SF printed extent. Halving it would be a
    guess, so the row is FLAGGED with its measurement intact (INV-02 §4).
    """
    r = RoomFillResult(area_sf=916.6, regions=[584.0, 128.0], candidate_id="LEAK")
    out = cross_check_extent(r, 455.2)
    assert out.needs_review is True
    assert out.area_sf == 916.6, "the measurement is preserved, never rewritten"
    assert out.extent_ratio == pytest.approx(2.014, abs=0.001)
    assert "verify" in out.review_reason.lower()


def test_the_discrimination_holds_seven_percent_either_side():
    """The plan's own discrimination case: ~2x flags, within 7% does not."""
    for area in (455.2 * 0.93, 455.2, 455.2 * 1.07):
        assert cross_check_extent(
            RoomFillResult(area_sf=round(area, 1)), 455.2
        ).needs_review is False
    assert cross_check_extent(
        RoomFillResult(area_sf=round(455.2 * 2.0, 1)), 455.2
    ).needs_review is True


def test_no_printed_extent_flags_and_never_drops_the_measurement():
    """INV-02 risk 2: a bound-derived rejection would be worse than the bug.

    Two of the sixteen prototype sheets print no dimension pair at all, so
    "no bound" must mean NEEDS REVIEW carrying the measured area — never a
    dropped row and never a guessed bound.
    """
    for missing in (None, 0.0, -1.0):
        out = cross_check_extent(RoomFillResult(area_sf=451.1), missing)
        assert out.area_sf == 451.1, "the measurement survives"
        assert out.bound_sf is None and out.extent_ratio is None
        assert out.needs_review is True
        assert "no overall dimension pair" in out.review_reason


def test_the_plausibility_bound_is_a_ratio_and_not_a_size_in_square_feet():
    """V4-MEAS-02, stated as an assertion.

    A guest-room-sized threshold is right for a guest room and wrong for a
    lobby. The replacement is dimensionless, so the SAME number governs a
    250 SF guest room and a 12,000 SF ballroom — pinned here by checking that
    scaling BOTH sides by fifty changes no verdict.
    """
    assert EXTENT_TOLERANCE == 1.25
    assert 1.073 < EXTENT_TOLERANCE < 2.0, (
        "above every honest sheet INV-02 §4 measured, below a two-plan leak"
    )
    for factor in (1.0, 50.0):
        assert cross_check_extent(
            RoomFillResult(area_sf=round(455.2 * factor, 1)), 455.2 * factor
        ).needs_review is False
        assert cross_check_extent(
            RoomFillResult(area_sf=round(910.4 * factor, 1)), 455.2 * factor
        ).needs_review is True


def test_the_guest_room_sized_plausibility_constant_is_gone():
    """It was a size in SF, and it sat on the WRONG SIDE of the multiplication.

    `flag_implausible_unit` saw 458.3 and passed it; the 916.6 that was
    actually wrong was produced later, in fusion, and no guard ever saw it
    (INV-02 §5). Both the constant and the function it fed are deleted, and
    no module-level constant in room_fill may replace it with another size.
    """
    import re

    from bobbytailor.deterministic import room_fill as rf
    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    assert not hasattr(TakeoffPipeline, "_MAX_UNIT_SF")
    assert not hasattr(rf, "flag_implausible_unit")
    src = open(rf.__file__, encoding="utf-8").read()
    for line in src.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9_]*)\s*=\s*([0-9.]+)\s*$", line)
        if not m or m.group(1) in ("MIN_REGION_SF", "MAX_REGION_SF"):
            continue
        assert "_SF" not in m.group(1), (
            "%s is a new square-foot bound — V4-MEAS-02 forbids it" % m.group(1)
        )


# ── prototype-unit x count ───────────────────────────────────────────────────


def test_total_for_units_multiplies_measured_area_by_the_room_mix():
    """Moxy ID-413: one QQ A measured 272.6 SF x 90 units in the mix."""
    assert total_for_units(272.6, 90) == pytest.approx(24534.0, rel=1e-3)


def test_total_for_units_without_a_count_returns_the_single_unit():
    """No count supplied -> the measured area stands alone (never zeroed)."""
    assert total_for_units(272.6, None) == pytest.approx(272.6)
    assert total_for_units(272.6, 0) == pytest.approx(272.6)


def test_an_oversize_region_is_kept_and_flagged_never_dropped():
    """23-09: the hard drop is gone, and this is why (INV-02 §5).

    THE SUPERSEDED TEST, inverted rather than deleted. Its predecessor —
    `test_max_region_guard_rejects_sheet_scale_regions` — asserted that a room
    of this size is REJECTED, and the constant it was guarding
    (`MAX_REGION_SF`, and the `_MAX_UNIT_SF = 900.0` beside it) was a
    guest-room-shaped number: right for a Moxy guestroom, wrong for every lobby,
    ballroom and retail floor plate in the world. INV-02 §5 shows what the
    rejection actually cost — dropping the region left `enclosed` empty and the
    engine returned `None`, so such a drawing reported NOTHING, and a drawing
    that measured nothing is indistinguishable from an item that is genuinely
    zero. That is the silent zero this phase exists to abolish.

    So the contract is inverted: the measurement is RETURNED and FLAGGED, with
    the reason naming the bound it exceeded. The scale-free replacement for the
    plausibility judgement itself is `cross_check_extent` (INV-02 §4), a ratio
    against the drawing's own printed extent — see
    `test_the_plausibility_bound_is_a_ratio_and_not_a_size_in_square_feet`.

    Drawn at 1/8" = 1'-0" so the whole region fits on an 800 pt page and is
    genuinely ENCLOSED; a 60x40-at-quarter fixture overflows the page, so its
    region touches the clip edge and is discarded as the OUTSIDE before the
    size filter is ever reached.
    """
    fpp_eighth = 8.0 / 72.0
    doc, page, clip = _page_with_room(40.0, 30.0, fpp=fpp_eighth)
    r = measure_enclosed_area(
        page, clip, fpp_eighth, max_region_sf=MAX_REGION_SF,
    )
    assert r is not None, "the measurement must survive, flagged"
    assert r.area_sf == pytest.approx(1200.0, rel=0.08)
    assert r.needs_review is True
    assert "KEPT AND FLAGGED" in r.review_reason
    assert "900" in r.review_reason, "the reason names the bound it exceeded"
    doc.close()


# ── the oversize region leaves a trace (23-03 / INV-08 §4 step 7) ────────────


def test_the_oversize_register_still_records_the_area_for_the_ledger():
    """Kept and flagged, AND on the record (T-23-36).

    Flagging the row is what the client sees; the out-list is what the coverage
    ledger sees. Both, or an oversize region is visible in only one artifact.
    """
    fpp_eighth = 8.0 / 72.0
    doc, page, clip = _page_with_room(40.0, 30.0, fpp=fpp_eighth)
    dropped = []
    r = measure_enclosed_area(
        page, clip, fpp_eighth, max_region_sf=MAX_REGION_SF,
        dropped_regions=dropped,
    )
    assert r is not None and r.needs_review is True
    assert len(dropped) == 1
    assert dropped[0] > MAX_REGION_SF
    assert dropped[0] == pytest.approx(1200.0, rel=0.08)
    assert dropped[0] in r.regions, "the region is in the measurement too"
    doc.close()


def test_an_oversize_flag_is_not_erased_by_the_extent_cross_check():
    """Two flags, one reason string. Neither may delete the other."""
    r = RoomFillResult(area_sf=1200.0, regions=[1200.0], needs_review=True,
                       review_reason="1 region(s) of 1200 SF exceed the maximum")
    out = cross_check_extent(r, 455.2)
    assert "exceed the maximum" in out.review_reason
    assert "printed overall extent" in out.review_reason
    # and the same holds for the no-bound branch
    r2 = RoomFillResult(area_sf=1200.0, needs_review=True,
                        review_reason="1 region(s) of 1200 SF exceed the maximum")
    assert "exceed the maximum" in cross_check_extent(r2, None).review_reason


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


# ── SP-3: ONE shared mask labeller (23-09 Task 1) ────────────────────────────
#
# The previous implementation built a labelled bitmap and threw it away,
# returning only counts — which is why no perimeter primitive existed anywhere
# in the package (INV-01 §3). `label_mask` keeps the labels, so the contour
# consumer here, the enclosed-void consumer that already existed, and the
# silhouette consumer plan 23-14 adds all label a clip ONCE (D-03).


def _mask(rows):
    """A byte mask from an ASCII picture: '#' is set, anything else is clear."""
    width = len(rows[0])
    assert all(len(r) == width for r in rows), "the picture must be rectangular"
    flat = bytearray()
    for r in rows:
        flat.extend(1 if ch == "#" else 0 for ch in r)
    return flat, width, len(rows)


def test_label_mask_finds_every_component_with_its_pixel_count():
    """Three known components, hand-counted."""
    mask, w, h = _mask([
        ".....",
        ".##..",
        ".##..",
        "....#",
        "###..",
    ])
    out = label_mask(mask, w, h)
    assert out.count == 3
    assert sorted(out.counts) == [1, 3, 4]
    assert sum(out.counts) == sum(mask), "every set pixel belongs to exactly one component"


def test_label_mask_reports_which_components_touch_the_edge():
    """The edge flag is the whole basis of 'this region is the OUTSIDE'."""
    mask, w, h = _mask([
        ".....",
        ".##..",
        ".##..",
        "....#",
        "###..",
    ])
    out = label_mask(mask, w, h)
    by_start = dict(zip(out.starts, out.touches_edge))
    assert by_start[1 * 5 + 1] is False, "the interior 2x2 block touches no edge"
    assert by_start[3 * 5 + 4] is True, "the single pixel sits on the right edge"
    assert by_start[4 * 5 + 0] is True, "the bottom strip sits on the bottom edge"


def test_the_first_pixel_of_a_component_is_its_topmost_then_leftmost():
    """The Moore trace is seeded here, so the seed must be exactly this pixel.

    A raster-order scan visits a component's lowest linear index first, which
    is its smallest y and — within that row — its smallest x. The property is
    asserted rather than assumed because a wrong seed sends the trace around an
    interior hole instead of the outer ring.
    """
    mask, w, h = _mask([
        "..###",
        ".####",
        "####.",
        "..##.",
    ])
    out = label_mask(mask, w, h)
    assert out.count == 1
    start = out.starts[0]
    assert (start % w, start // w) == (2, 0)
    # independently recomputed from the mask itself
    members = [(i % w, i // w) for i in range(w * h) if mask[i]]
    assert min(members, key=lambda p: (p[1], p[0])) == (start % w, start // w)


def test_the_labels_array_is_the_thing_that_used_to_be_discarded():
    """Every set pixel carries its component id; every clear pixel carries 0."""
    mask, w, h = _mask([
        "##..",
        "##..",
        "..##",
    ])
    out = label_mask(mask, w, h)
    assert out.count == 2
    assert len(out.labels) == w * h
    for i in range(w * h):
        assert (out.labels[i] != 0) is bool(mask[i])
    assert out.labels[0] != out.labels[2 * w + 2], "the two blocks are distinct"


def test_label_mask_is_four_connected_so_a_diagonal_gap_is_not_a_leak():
    """8-way labelling of free space would merge a room with the outside
    through a single diagonal pixel gap and the room would be lost."""
    mask, w, h = _mask([
        "#..",
        ".#.",
        "..#",
    ])
    assert label_mask(mask, w, h).count == 3


def test_label_regions_is_a_projection_over_the_one_labeller():
    """D-03: the counting view must not be a second implementation."""
    import inspect

    from bobbytailor.deterministic import room_fill as r

    src = inspect.getsource(r._label_regions)
    assert "label_mask" in src
    assert "deque" not in src, "the breadth-first search lives in ONE place"


# ── the real-PDF measurement baseline (23-09, T-23-35) ───────────────────────


@pytest.fixture(scope="module")
def moxy_prototype_fills():
    """Every drawing on Moxy's 16 prototype-unit sheets, measured ONCE.

    ~70 s of pure-Python flood fill over ~1.2 M pixels per clip. Module-scoped
    deliberately: the area baseline, the perimeter assertions and the blind
    shape-ratio bands all read the SAME measurement, so the evidence is one run
    of the engine rather than three, and the suite pays for it once.
    """
    import os

    if not os.path.exists(MOXY_PDF):
        pytest.skip("the real Moxy plan set is not present")
    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    # The POISONED project answer is deliberately armed (23-13): Moxy's project
    # resolver returns 15 ft from a roof-plan "CLEAR REQ'D" callout at source
    # "plan". With it armed, the height assertions below prove the per-drawing
    # tag WINS over it — not merely that no project height was available.
    pipe._project_wall_height = 15.0
    pipe._project_wall_height_source = "plan"
    doc = fitz.open(MOXY_PDF)
    try:
        out = {
            pno: pipe._measure_room_fills(doc[pno], [], {}, "p%d" % pno)[0]
            for pno in range(23, 39)
        }
    finally:
        doc.close()
    return out


def _dominant(fills, page, kind):
    """The largest-area region of the *kind* drawing on *page*."""
    picks = [f for f in fills[page] if f.plan_kind == kind]
    assert len(picks) == 1, "expected exactly one %s drawing on page %d" % (kind, page)
    return picks[0]


# (page, plan name, area_sf) as measured BEFORE any of 23-09's changes, taken
# from a probe run of the shipped engine. These are the sixteen reflected-
# ceiling prototypes; §14 of PIPELINE-GROUND-TRUTH records four of them
# (229.4 / 341.7 / 272.6 / 274.6) and INV-01 §1 records ACC QQ RIS at 451.1.
#
# Their job is T-23-35: adding perimeter must not perturb a shipped area by a
# single decimal. If a refactor here moves one of these, the refactor is wrong
# — the number is NOT to be updated to match.
MOXY_RCP_AREA_BASELINE = [
    (23, "KING A", 229.4),
    (24, "KING B", 235.5),
    (25, "KING C", 217.6),
    (26, "KING SUITE A", 362.5),
    (27, "KING SUITE B", 341.7),
    (28, "KING SUITE C", 458.3),
    (29, "QQ A", 272.6),
    (30, "QQ B", 309.5),
    (31, "QQ C", 284.3),
    (32, "BUNK A", 454.7),
    (33, "BUNK B", 274.6),
    (34, "ADA KING RIS", 347.2),
    (35, "ACC KING TUB", 347.7),
    (36, "ACC QQ RIS", 451.1),
    (37, "ACC QQ TUB", 463.0),
    (38, "ACC BUNK", 458.5),
]


def test_the_sixteen_sheet_moxy_area_baseline_is_byte_identical(moxy_prototype_fills):
    """Not `approx` — EQUAL. Area is the shipped number and must not move."""
    measured = [
        (page, _dominant(moxy_prototype_fills, page, "RCP").plan_name,
         _dominant(moxy_prototype_fills, page, "RCP").area_sf)
        for page, _, _ in MOXY_RCP_AREA_BASELINE
    ]
    assert measured == MOXY_RCP_AREA_BASELINE


# ── SP-3: the outer-contour trace and the ring-safe simplifier (Task 2) ──────


def _traced(rows):
    """(contour, labelled) for the single component of an ASCII picture."""
    from bobbytailor.deterministic.room_fill import _trace_outer_contour

    mask, w, h = _mask(rows)
    labelled = label_mask(mask, w, h)
    assert labelled.count == 1, "the fixture must draw exactly one component"
    contour, truncated = _trace_outer_contour(
        labelled.labels, w, h, 1, labelled.starts[0],
        max_steps=4 * labelled.counts[0] + 16,
    )
    assert truncated is False
    return contour, labelled


def _solid(width, height):
    return ["#" * width for _ in range(height)]


def test_the_traced_ring_of_a_rectangle_has_its_exact_pixel_perimeter():
    """Exact ground truth by construction, in pixels — no scale involved yet.

    A trace through pixel CENTRES of a solid w x h block walks a rectangle of
    (w-1) x (h-1), so its ring length is exactly 2*((w-1) + (h-1)).
    """
    from bobbytailor.deterministic.room_fill import _ring_length

    for w, h in ((9, 5), (12, 12), (20, 3)):
        contour, _ = _traced(_solid(w, h))
        assert contour[0] == contour[-1], "the trace returns a CLOSED ring"
        assert _ring_length(contour) == pytest.approx(2.0 * ((w - 1) + (h - 1)))


def test_the_trace_walks_the_outer_ring_and_ignores_an_interior_hole():
    """A furniture outline or a room number inside a room is not a wall.

    The identical outer boundary with and without a hole is the whole reason
    the trace is a boundary FOLLOWER rather than a boundary-pixel COUNT: INV-05
    section 3 measured the counting method at roughly six times the truth
    precisely because it cannot tell an outer edge from an inner one.
    """
    from bobbytailor.deterministic.room_fill import _ring_length

    solid, _ = _traced(_solid(11, 9))
    holed, _ = _traced([
        "###########",
        "###########",
        "###########",
        "####...####",
        "####...####",
        "####...####",
        "###########",
        "###########",
        "###########",
    ])
    assert _ring_length(holed) == pytest.approx(_ring_length(solid))
    assert _ring_length(holed) == pytest.approx(2.0 * (10 + 8))


def test_a_diagonal_edge_is_traced_as_a_diagonal_not_as_a_staircase():
    """Each 8-connected step across a 45-degree face measures root two.

    A 4-connected trace would climb the staircase and over-read that face by
    41 percent, which is the error the simplifier's root-two comment names.
    """
    from bobbytailor.deterministic.room_fill import _ring_length

    contour, _ = _traced([
        "#....",
        "##...",
        "###..",
        "####.",
        "#####",
    ])
    # the hypotenuse is walked in 4 diagonal steps, the two legs in 4 each
    assert _ring_length(contour) == pytest.approx(4 * 2 ** 0.5 + 8.0)


def test_an_isolated_pixel_terminates_instead_of_spinning():
    """T-23-34: a degenerate component must flag, never loop."""
    from bobbytailor.deterministic.room_fill import _ring_length

    contour, _ = _traced([".....", "..#..", "....."])
    assert _ring_length(contour) == 0.0


def test_the_iteration_cap_flags_rather_than_looping(monkeypatch):
    """The cap is the safety net under Jacob's criterion, not a substitute.

    Forced here with an absurdly small cap, because no real region approaches
    it: the ring of an n-pixel component cannot exceed roughly 2n steps.
    """
    from bobbytailor.deterministic.room_fill import _trace_outer_contour

    mask, w, h = _mask(_solid(20, 20))
    labelled = label_mask(mask, w, h)
    contour, truncated = _trace_outer_contour(
        labelled.labels, w, h, 1, labelled.starts[0], max_steps=5,
    )
    assert truncated is True, "the walk must report that it was cut short"
    assert len(contour) <= 7


# ── the closed-ring collapse (INV-01 section 6 step 3) ───────────────────────


def test_plain_simplification_of_a_closed_ring_collapses_it():
    """The hazard, reproduced — this is what the split repair exists to avoid.

    A ring's first and last points are the SAME point, so its base chord runs
    from a point to itself. Under the ordinary reading — a degenerate chord
    means every deviation is zero — nothing survives the tolerance and the
    whole ring vanishes. INV-01's prototype hit exactly this and reported every
    perimeter as 0.0 while every area was correct, which reads as "this room
    has no walls" rather than as a bug.
    """
    from bobbytailor.deterministic.room_fill import _ring_length

    contour, _ = _traced(_solid(12, 12))

    def _naive(points, eps):
        """Textbook Douglas-Peucker with the usual degenerate-chord guard."""
        if len(points) < 3:
            return list(points)
        ax, ay = points[0]
        bx, by = points[-1]
        norm = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        if norm == 0.0:
            return [points[0], points[-1]]      # <- the collapse
        best, best_d = 0, 0.0
        for k in range(1, len(points) - 1):
            cx, cy = points[k]
            d = abs((bx - ax) * (ay - cy) - (ax - cx) * (by - ay)) / norm
            if d > best_d:
                best, best_d = k, d
        if best_d <= eps:
            return [points[0], points[-1]]
        return _naive(points[:best + 1], eps)[:-1] + _naive(points[best:], eps)

    assert _ring_length(_naive(contour, 2.0)) == 0.0, "the hazard is real"


def test_the_ring_safe_simplifier_does_not_collapse_a_traced_square():
    """The regression guard: at least four vertices and a non-zero length."""
    from bobbytailor.deterministic.room_fill import _ring_length, _simplify_ring

    contour, _ = _traced(_solid(12, 12))
    simple = _simplify_ring(contour, eps_px=2.0)
    assert len(simple) >= 4
    assert _ring_length(simple) > 0.0
    assert _ring_length(simple) == pytest.approx(_ring_length(contour))
    assert simple[0] == simple[-1], "the simplified ring is still closed"


def test_simplification_is_lossless_on_straight_faces_and_drops_the_vertices():
    """On rectilinear ink it removes vertices and NOTHING else.

    637 traced pixel corners become the 4 corners of the rectangle they
    describe, and the length does not move — which is why adding the
    simplifier cannot perturb a guest room's measured perimeter.
    """
    from bobbytailor.deterministic.room_fill import _ring_length, _simplify_ring

    contour, _ = _traced(_solid(200, 120))
    simple = _simplify_ring(contour, eps_px=2.0)
    assert len(contour) == 637
    assert len(simple) == 5, "four corners plus the closing point"
    assert _ring_length(simple) == pytest.approx(_ring_length(contour))


def test_simplification_recovers_the_true_length_of_a_shallow_diagonal():
    """THE reason the simplifier is kept — exact ground truth by construction.

    A face rising one pixel every four columns is traced as a staircase, and a
    staircase is longer than the line it approximates. The shape drawn here is
    a quadrilateral whose exact perimeter is 9 + 120 + 39 + hypot(120, 30);
    the raw trace over-reads it by three percent and the simplified ring lands
    on it to floating point. On a rectilinear guest room the correction is
    under one and a half percent (INV-01 section 4) — it is the diagonal wall
    that needs this.
    """
    import math

    from bobbytailor.deterministic.room_fill import _ring_length, _simplify_ring

    rows = [
        "".join("#" if y >= 30 - x // 4 else "." for x in range(121))
        for y in range(40)
    ]
    contour, _ = _traced(rows)
    exact = 9.0 + 120.0 + 39.0 + math.hypot(120.0, 30.0)
    raw = _ring_length(contour)
    simple = _ring_length(_simplify_ring(contour, eps_px=2.0))
    assert simple == pytest.approx(exact)
    assert raw > exact
    assert (raw - exact) / exact == pytest.approx(0.030, abs=0.005)


def test_a_ring_that_is_already_a_point_is_not_turned_into_garbage():
    from bobbytailor.deterministic.room_fill import _ring_length, _simplify_ring

    assert _ring_length(_simplify_ring([(3, 3), (3, 3)], 2.0)) == 0.0
    assert _simplify_ring([], 2.0) == []


# ── the same trace, on the real drawing (23-09 Task 2) ───────────────────────


def _moxy_viewport_mask(pno, kind):
    """Render the exact viewport the pipeline clips, and label it.

    The clip recipe is the pipeline's OWN — its two public inputs
    (`plan_titles` / `extract_printed_scales`) and its two clip constants — so
    this is not a parallel measurement path. It is anchored by asserting the
    resulting area against the pinned baseline: if the recipe ever drifts, this
    helper measures a different rectangle and says so loudly.
    """
    import os

    if not os.path.exists(MOXY_PDF):
        pytest.skip("the real Moxy plan set is not present")
    from bobbytailor.deterministic.printed_scale import extract_printed_scales
    from bobbytailor.deterministic.room_fill import (
        DEFAULT_DPI,
        free_mask,
        plan_titles,
    )
    from bobbytailor.pipeline.takeoff_pipeline import (
        TakeoffPipeline,
        _page_space_box,
        _page_space_point,
    )

    doc = fitz.open(MOXY_PDF)
    page = doc[pno]
    scales = extract_printed_scales(page)
    for name, plan_kind, tb in plan_titles(page):
        if plan_kind != kind:
            continue
        tx0, ty0, tx1, ty1 = _page_space_box(page, tb)
        mid = (tx0 + tx1) / 2.0
        ps, best = None, float("inf")
        for s in scales:
            cx, cy = _page_space_point(page, *s.center_pt)
            if abs(cx - mid) > TakeoffPipeline._FILL_CLIP_SIDE_PT:
                continue
            gap = cy - ty1
            if -6.0 <= gap < best:
                ps, best = s, gap
        assert ps is not None
        fpp = float(ps.feet_per_point)
        clip = fitz.Rect(
            tx0 - TakeoffPipeline._FILL_CLIP_SIDE_PT,
            max(0.0, ty0 - TakeoffPipeline._FILL_CLIP_UP_PT),
            tx1 + TakeoffPipeline._FILL_CLIP_SIDE_PT,
            max(0.0, ty0 - 8.0),
        )
        pix = page.get_pixmap(
            clip=to_page_space(page, from_page_space(page, clip)),
            dpi=DEFAULT_DPI, colorspace=fitz.csGRAY,
        )
        labelled = label_mask(
            free_mask(pix.samples, pix.width * pix.height), pix.width, pix.height
        )
        zoom = DEFAULT_DPI / 72.0
        doc.close()
        return labelled, (1.0 / (zoom * zoom)) * fpp * fpp, (1.0 / zoom) * fpp, name
    doc.close()
    raise AssertionError("no %s drawing on page %d" % (kind, pno))


def test_on_the_real_drawing_simplification_changes_the_perimeter_by_under_1_5_percent():
    """Moxy page 27, the KING SUITE B reflected-ceiling plan.

    The dominant region is identified by area alone, and the area is asserted
    against the pinned 216.8 SF baseline first — so this measures the same
    region the shipped engine measures, not a lookalike.
    """
    from bobbytailor.deterministic.room_fill import (
        _ring_length,
        _simplify_ring,
        _trace_outer_contour,
    )

    labelled, px_area_sf, px_len_ft, name = _moxy_viewport_mask(27, "RCP")
    assert name == "KING SUITE B"
    best = max(
        (k for k in range(labelled.count) if not labelled.touches_edge[k]),
        key=lambda k: labelled.counts[k],
    )
    assert round(labelled.counts[best] * px_area_sf, 1) == 216.8, (
        "the dominant enclosed region must be the one the engine publishes"
    )
    contour, truncated = _trace_outer_contour(
        labelled.labels, labelled.width, labelled.height, best + 1,
        labelled.starts[best], max_steps=4 * labelled.counts[best] + 16,
    )
    assert truncated is False
    raw = _ring_length(contour) * px_len_ft
    simple = _ring_length(_simplify_ring(contour)) * px_len_ft
    assert raw > 0.0 and simple > 0.0
    assert simple <= raw, "simplification can only ever shorten a polyline"
    assert (raw - simple) / raw < 0.015, (
        "raw %.2f LF vs simplified %.2f LF" % (raw, simple)
    )


# ── SP-3: perimeter and the blind shape ratio on the fill (23-09 Task 3) ─────


def _one_region(width_ft, height_ft, fpp=FPP_QUARTER, wall_pt=1.0, **kw):
    """Measure a single rectangular room and return its one region's numbers."""
    doc, page, clip = _page_with_room(width_ft, height_ft, fpp=fpp, wall_pt=wall_pt)
    r = measure_enclosed_area(page, clip, fpp, **kw)
    doc.close()
    assert r is not None and len(r.regions) == 1
    return r


# The ink is a stroke CENTRED on the room's nominal outline, so half of it
# eats into the room. The enclosed void a fill can see is therefore the
# nominal rectangle inset by half the stroke on each side — exact by
# construction, no plan and no golden number involved.
def _interior(width_ft, height_ft, wall_pt, fpp):
    inset = wall_pt * fpp
    return width_ft - inset, height_ft - inset


def test_perimeter_of_a_known_rectangle():
    """10' x 20' at 1/4"=1'-0": 60 LF and 200 SF, both within two percent."""
    r = _one_region(10.0, 20.0)
    w, h = _interior(10.0, 20.0, 1.0, FPP_QUARTER)
    assert r.perimeter_lf == pytest.approx(2.0 * (w + h), rel=0.02)
    assert r.area_sf == pytest.approx(w * h, rel=0.02)
    # and still within two percent of the NOMINAL room, since the linework is
    # thin relative to the room
    assert r.perimeter_lf == pytest.approx(60.0, rel=0.02)
    assert r.area_sf == pytest.approx(200.0, rel=0.02)
    assert r.region_perimeters == [r.perimeter_lf]
    assert r.needs_review is False


def test_perimeter_ignores_an_interior_hole():
    """A furniture block in the middle of a room is not part of its walls.

    The room is drawn twice — empty, and with a filled block at its centre.
    The perimeter must not move: the trace walks the OUTER ring only. A
    boundary-pixel count would rise by the block's whole circumference.
    """
    doc, page, clip = _page_with_room(10.0, 20.0, wall_pt=1.0)
    empty = measure_enclosed_area(page, clip, FPP_QUARTER)
    # a solid 2' x 2' block at the room's centre
    cx, cy = 100.0 + 10.0 / FPP_QUARTER / 2.0, 100.0 + 20.0 / FPP_QUARTER / 2.0
    half = 1.0 / FPP_QUARTER
    page.draw_rect(fitz.Rect(cx - half, cy - half, cx + half, cy + half),
                   fill=(0, 0, 0), color=(0, 0, 0))
    holed = measure_enclosed_area(page, clip, FPP_QUARTER)
    doc.close()
    assert empty is not None and holed is not None
    assert holed.perimeter_lf == pytest.approx(empty.perimeter_lf, rel=0.005)
    assert holed.area_sf < empty.area_sf, "the block does take away floor area"


def test_perimeter_scales_linearly_while_area_scales_quadratically():
    """The SAME ink read at half the scale: perimeter x2, area x4.

    One page, two scales — the drawing does not change, only the ratio it is
    read at. That is the measurement contract's rule-2 guard expressed for the
    new primitive: a perimeter accidentally derived from the AREA factor would
    come back x4 here and this test would say so.
    """
    doc, page, clip = _page_with_room(12.0, 10.0, wall_pt=1.0)
    quarter = measure_enclosed_area(page, clip, FPP_QUARTER)
    eighth = measure_enclosed_area(page, clip, 8.0 / 72.0)
    doc.close()
    assert quarter is not None and eighth is not None
    assert eighth.perimeter_lf == pytest.approx(2.0 * quarter.perimeter_lf, rel=0.02)
    assert eighth.area_sf == pytest.approx(4.0 * quarter.area_sf, rel=0.02)


def test_shape_ratio_of_a_square_is_four():
    """P/sqrt(A) = 4.00 for a square, by definition. Validated by construction."""
    r = _one_region(15.0, 15.0)
    assert r.region_shape_ratios[0] == pytest.approx(4.0, abs=0.05)


def test_the_shape_ratio_of_a_sliver_exceeds_eight():
    """The annotation-cell detector: a 1' x 40' cell is not a room.

    P/sqrt(A) = 82/6.32 = 12.97 — the 11.6-13.4 band INV-01 §4 measured on
    Moxy's real dimension cells, reproduced here from pure geometry with no
    plan and no golden number involved. Drawn at 1/8"=1'-0" so that 40 real
    feet fit on an 800 pt page and the cell is genuinely enclosed.
    """
    from bobbytailor.deterministic.room_fill import MAX_HONEST_SHAPE_RATIO

    r = _one_region(1.0, 40.0, fpp=8.0 / 72.0, wall_pt=0.5)
    assert r.region_shape_ratios[0] > MAX_HONEST_SHAPE_RATIO
    assert r.region_shape_ratios[0] == pytest.approx(13.0, rel=0.10)
    # and the room-shaped control, measured the same way, is nowhere near it
    assert _one_region(15.0, 15.0).region_shape_ratios[0] < MAX_HONEST_SHAPE_RATIO


def test_the_shape_ratio_threshold_is_read_off_geometry_not_off_a_total():
    """4.00 is a square; 5.08 was the worst honest room; 8.54 the best leak."""
    from bobbytailor.deterministic.room_fill import MAX_HONEST_SHAPE_RATIO

    assert MAX_HONEST_SHAPE_RATIO == 8.0
    assert MAX_HONEST_SHAPE_RATIO > 5.08, "above every honest room measured"
    assert MAX_HONEST_SHAPE_RATIO < 8.54, "below every leak measured"


def test_the_per_region_lists_are_parallel_to_the_region_list():
    """A perimeter that cannot say which region it belongs to is unusable."""
    doc, page, clip = _page_with_room(20.0, 15.0, inner=6.0, wall_pt=1.0)
    r = measure_enclosed_area(page, clip, FPP_QUARTER)
    doc.close()
    assert r is not None and len(r.regions) >= 2
    assert len(r.region_perimeters) == len(r.regions)
    assert len(r.region_shape_ratios) == len(r.regions)
    assert r.regions == sorted(r.regions, reverse=True)
    assert r.perimeter_lf == pytest.approx(sum(r.region_perimeters), abs=0.15)
    for area, perim, ratio in zip(r.regions, r.region_perimeters,
                                  r.region_shape_ratios):
        assert ratio == pytest.approx(perim / area ** 0.5, abs=0.01)


def test_the_serialised_form_carries_the_new_geometry():
    """The report and the learning store both read to_dict()."""
    r = _one_region(10.0, 20.0)
    d = r.to_dict()
    assert d["perimeter_lf"] == r.perimeter_lf
    assert d["region_perimeters"] == r.region_perimeters
    assert d["region_shape_ratios"] == r.region_shape_ratios
    assert d["bound_sf"] == r.bound_sf
    assert d["extent_ratio"] == r.extent_ratio
    # additive only — every pre-existing key is still there
    assert {"area_sf", "regions", "candidate_id", "scale_fpi", "needs_review",
            "review_reason", "sheet_name", "viewport_title", "plan_name",
            "plan_kind"} <= set(d)


def test_the_size_constant_is_still_untouched():
    """The behaviour changed; the threshold did not (D-07)."""
    assert MAX_REGION_SF == 900.0


# ── the blind bands, on the real drawings (23-09 Task 3) ─────────────────────


@pytest.mark.parametrize("page", [23, 27, 29, 33])
def test_the_dominant_ceiling_region_has_the_shape_of_a_room(moxy_prototype_fills, page):
    """Blind: geometry only, no golden quantity consulted anywhere.

    A rectilinear room has P/sqrt(A) between 4 (a square) and about 6 (an L
    with a bath alcove). INV-01 §4 measured 4.24 / 4.64 / 4.84 / 5.08 on these
    four sheets. A fill that has leaked out through a door swing breaks it.

    P/A is the SAME statement divided by a size — it equals the shape ratio
    over sqrt(A) — so its band of 0.20-0.45 per foot only holds over the
    150-400 SF room sizes it was quoted for, and it is asserted over exactly
    that premise. KING A's dominant reflected-ceiling region is 121.8 SF, so
    an honest ratio of 5.08 puts it at 0.46 by arithmetic alone; widening the
    band to swallow that would be fitting a threshold to an output. The
    identity is pinned below instead, so the relationship cannot drift.
    """
    fill = _dominant(moxy_prototype_fills, page, "RCP")
    area, ratio = fill.regions[0], fill.region_shape_ratios[0]
    perim = fill.region_perimeters[0]
    assert 4.0 <= ratio <= 6.0, "%s ratio %.2f" % (fill.plan_name, ratio)
    assert perim / area == pytest.approx(ratio / area ** 0.5, rel=0.01)
    if 150.0 <= area <= 400.0:
        assert 0.20 <= perim / area <= 0.45, (
            "%s P/A %.3f per ft" % (fill.plan_name, perim / area)
        )


@pytest.mark.parametrize("page", [23, 27, 29])
def test_the_architectural_fill_reproduces_its_leak_signature(moxy_prototype_fills, page):
    """The same blind ratio exposes the AR raster leak — INV-01 measured
    8.62 (KING A), 9.04 (KING SUITE B) and 8.54 (QQ A).

    Nothing here consults a golden value: the AR contour is simply wandering
    out through door swings and dimension strings, and a wandering contour is
    long for the area it encloses. This is the §14.2 clip defect surfacing in
    a second, independent way — and it is why 23-13 must not bill an AR
    perimeter without checking this number first.
    """
    from bobbytailor.deterministic.room_fill import MAX_HONEST_SHAPE_RATIO

    fill = _dominant(moxy_prototype_fills, page, "AR")
    ratio = fill.region_shape_ratios[0]
    assert ratio > MAX_HONEST_SHAPE_RATIO, "%s ratio %.2f" % (fill.plan_name, ratio)


# ── the extent cross-check on the real drawings (23-11 Task 3) ───────────────
#
# INV-02 §4 harvested the largest printed horizontal x the largest printed
# vertical dimension inside each sheet's ARCHITECTURAL viewport and scored the
# reflected-ceiling fill against it. Thirteen sheets landed in 0.98-1.07; two
# print no dimension pair at all; ID-410 paired only PARTIAL interior dimensions
# and produced a bound 2.5x too small. Every number below was measured from the
# PDF before any golden quantity was read, and none of them may be tuned.

MOXY_EXTENT_BOUND = {
    23: 223.7, 24: 219.7, 25: 214.5, 26: 146.2, 27: 350.1, 28: 455.2,
    29: 254.0, 30: 311.5, 31: None, 32: 455.2, 33: 275.4, 34: 350.3,
    35: 350.3, 36: None, 37: 455.2, 38: 455.2,
}
MOXY_NO_PRINTED_EXTENT = (31, 36)          # ID-415 QQ C, ID-420 ACC QQ RIS
MOXY_PARTIAL_EXTENT = (26,)                # ID-410, a BOUND failure not a fill one


def test_the_printed_extent_bound_is_the_drawings_own_statement_of_its_size(
    moxy_prototype_fills,
):
    """Reproduces INV-02 §4 sheet for sheet, from the PDF alone."""
    measured = {
        page: _dominant(moxy_prototype_fills, page, "RCP").bound_sf
        for page in MOXY_EXTENT_BOUND
    }
    assert measured == MOXY_EXTENT_BOUND


def test_thirteen_prototype_sheets_measure_their_own_printed_extent(
    moxy_prototype_fills,
):
    """The blind validator: fill / printed extent, with no golden consulted.

    Thirteen of the sixteen land inside 0.9-1.15 — including ID-412 and ID-416,
    the two sheets §14.2 accused the clip of doubling, which are among the
    TIGHTEST fits in the whole set at 1.007 and 0.999.
    """
    inside = []
    for page in MOXY_EXTENT_BOUND:
        fill = _dominant(moxy_prototype_fills, page, "RCP")
        if page in MOXY_NO_PRINTED_EXTENT or page in MOXY_PARTIAL_EXTENT:
            continue
        assert 0.9 <= fill.extent_ratio <= 1.15, (
            "%s ratio %.3f" % (fill.plan_name, fill.extent_ratio)
        )
        assert fill.needs_review is False, fill.review_reason
        inside.append(page)
    assert len(inside) == 13


@pytest.mark.parametrize("page", MOXY_NO_PRINTED_EXTENT)
def test_a_sheet_with_no_printed_extent_is_flagged_and_still_reports_its_area(
    moxy_prototype_fills, page,
):
    """FLAG, never FILTER. The measurement is the point; the bound is a check."""
    fill = _dominant(moxy_prototype_fills, page, "RCP")
    assert fill.bound_sf is None and fill.extent_ratio is None
    assert fill.area_sf > 0.0, "the measured area is still reported"
    assert fill.needs_review is True
    assert "no overall dimension pair" in fill.review_reason


@pytest.mark.parametrize("page", MOXY_PARTIAL_EXTENT)
def test_a_partial_printed_extent_flags_the_row_rather_than_the_measurement(
    moxy_prototype_fills, page,
):
    """ID-410: only partial interior dimensions paired, so the BOUND is wrong.

    The row is flagged and the area is untouched — which is the correct
    behaviour for a check that can be wrong about a fill that is right.
    """
    fill = _dominant(moxy_prototype_fills, page, "RCP")
    assert fill.extent_ratio > EXTENT_TOLERANCE
    assert fill.needs_review is True
    assert fill.area_sf == 362.5, "the measurement is never rewritten by a check"


def test_every_prototype_sheet_reports_a_perimeter_at_all(moxy_prototype_fills):
    """The primitive that did not exist now exists on every real measurement."""
    for page, name, _area in MOXY_RCP_AREA_BASELINE:
        fill = _dominant(moxy_prototype_fills, page, "RCP")
        assert fill.perimeter_lf > 0.0, name
        assert len(fill.region_perimeters) == len(fill.regions)
        assert all(p > 0.0 for p in fill.region_perimeters), name


# ── 23-13 Task 1: billable perimeter, wall area, and the drawing's own height ─
#
# The primitives the wall binder consumes. The threshold is geometric and
# published (MAX_HONEST_SHAPE_RATIO); nothing here consults a golden quantity.


def _fill_with_geometry(regions, perimeters, ratios, **kw):
    return RoomFillResult(
        area_sf=round(sum(regions), 1), regions=list(regions),
        region_perimeters=list(perimeters), region_shape_ratios=list(ratios),
        perimeter_lf=round(sum(perimeters), 1), **kw
    )


def test_wall_area_for_unit_multiplies_perimeter_by_height():
    assert wall_area_for_unit(60.0, 9.0) == 540.0
    assert wall_area_for_unit(56.1, 9.0) == pytest.approx(504.9)
    assert wall_area_for_unit(0.0, 9.0) == 0.0


def test_a_leaking_dominant_region_returns_zero_perimeter_with_the_ratio_named():
    """The INV-01 architectural-leak signature: dominant ratio 8.62 > 8.0.

    Zero plus a reason — the caller flags; a fabricated linear-foot figure is
    never emitted."""
    fill = _fill_with_geometry([173.5, 11.5], [113.6, 24.0], [8.62, 9.1])
    billable, reason = wall_perimeter_for_unit(fill)
    assert billable == 0.0
    assert "8.62" in reason and "8.0" in reason
    assert "UNMEASURED" in reason, "a zero here is 'not measured', never 'no walls'"


def test_billable_perimeter_sums_honest_regions_and_names_dropped_cells():
    """Dominant honest, one annotation cell: the cell's LF is dropped AND named."""
    fill = _fill_with_geometry(
        [121.8, 34.2, 13.4], [56.1, 30.4, 42.3], [5.08, 5.20, 11.56]
    )
    billable, reason = wall_perimeter_for_unit(fill)
    assert billable == pytest.approx(86.5)  # 56.1 + 30.4, never the 42.3
    assert "11.56" in reason and "13.4 SF" in reason, (
        "a dropped annotation cell is named, never silently discarded"
    )


def test_a_clean_fill_bills_every_region_with_no_reason():
    fill = _fill_with_geometry([121.8, 34.2], [56.1, 30.4], [5.08, 5.20])
    billable, reason = wall_perimeter_for_unit(fill)
    assert billable == pytest.approx(86.5)
    assert reason == ""


def test_an_unmeasured_dominant_perimeter_refuses_rather_than_bills_zero_length():
    fill = _fill_with_geometry([121.8, 34.2], [0.0, 30.4], [0.0, 5.20])
    billable, reason = wall_perimeter_for_unit(fill)
    assert billable == 0.0
    assert "UNMEASURED" in reason


def test_a_fill_with_no_region_perimeters_refuses():
    fill = RoomFillResult(area_sf=200.0, regions=[200.0])
    billable, reason = wall_perimeter_for_unit(fill)
    assert billable == 0.0
    assert "no per-region perimeters" in reason


def test_the_shape_threshold_is_the_published_constant():
    """wall_perimeter_for_unit consumes MAX_HONEST_SHAPE_RATIO — the one 23-09
    published — not a private copy that could drift."""
    import inspect

    from bobbytailor.deterministic import room_fill

    sig = inspect.signature(room_fill.wall_perimeter_for_unit)
    assert sig.parameters["max_shape_ratio"].default is MAX_HONEST_SHAPE_RATIO


def _page_with_text(lines):
    """A page carrying text lines at distinct positions, plus their clip."""
    doc = fitz.open()
    page = doc.new_page(width=800, height=800)
    y = 150.0
    for text in lines:
        page.insert_text(fitz.Point(120.0, y), text, fontsize=10)
        y += 40.0
    return doc, page, fitz.Rect(80, 80, 700, y + 40)


def test_the_taller_ceiling_tag_wins_and_the_source_is_the_drawing():
    """9'-0\" bedroom + 8'-0\" bath soffit -> 9.0, source 'drawing'.

    The wall boarded to full height is the tall one (INV-01 §5)."""
    doc, page, clip = _page_with_text(['9\'-0"', '8\'-0"'])
    heights = drawing_ceiling_heights(page, clip)
    assert heights == [8.0, 9.0]
    h, src = resolve_drawing_height(page, clip, 15.0, "plan")
    assert h == 9.0 and src == "drawing", (
        "the drawing's own tag must beat the poisoned 15 ft project answer"
    )
    doc.close()


def test_an_aff_mounting_height_is_excluded_and_never_becomes_the_height():
    """8'-1\"AFF is a towel-bar mounting height, not a ceiling. In-band, taller
    than the real 8'-0\" soffit — and it must still lose."""
    doc, page, clip = _page_with_text(['8\'-1"AFF', '8\'-0"'])
    assert drawing_ceiling_heights(page, clip) == [8.0]
    h, src = resolve_drawing_height(page, clip, None, "")
    assert h == 8.0 and src == "drawing"
    doc.close()


def test_tokens_outside_the_ceiling_band_are_ignored():
    doc, page, clip = _page_with_text(['2\'-2"', '15\'-0"', '30\'-0"'])
    assert drawing_ceiling_heights(page, clip) == []
    doc.close()


def test_no_tag_falls_back_to_the_project_height_with_its_source_carried():
    doc, page, clip = _page_with_text(["GENERAL NOTES"])
    h, src = resolve_drawing_height(page, clip, 15.0, "plan")
    assert h == 15.0 and src == "plan", (
        "the fallback is honest about WHERE the number came from — the binder "
        "flags any source that is not the drawing"
    )
    doc.close()


def test_no_tag_and_no_project_height_resolves_to_nothing_so_the_caller_flags():
    doc, page, clip = _page_with_text(["GENERAL NOTES"])
    assert resolve_drawing_height(page, clip, None, "") == (None, "")
    assert resolve_drawing_height(page, None, None, "") == (None, "")
    doc.close()


def test_a_line_outside_the_clip_is_not_a_tag_of_this_drawing():
    doc, page, clip = _page_with_text(['9\'-0"'])
    elsewhere = fitz.Rect(700, 700, 790, 790)  # excludes the text
    assert drawing_ceiling_heights(page, elsewhere) == []
    doc.close()


# ── 23-13 Task 1: the real-PDF height + billable-perimeter assertions ────────
#
# The fixture arms the POISONED project answer (15 ft, source "plan") before
# measuring, so every assertion below proves the drawing's own tag wins over
# an available authoritative-looking wrong number — the actual trap.

# (page, expected height) — every prototype RCP prints 9'-0" except BUNK A
# (p32), whose RCP prints 9'-8". The plan's acceptance says "nine feet"
# everywhere; the drawing on p32 says 9'-8", and the MEASUREMENT wins over the
# plan literal (the 23-09 rule). What matters is identical either way:
# the source is the DRAWING, and the value is never the roof-plan 15.
MOXY_PROTOTYPE_HEIGHTS = [
    (23, 9.0), (24, 9.0), (25, 9.0), (26, 9.0), (27, 9.0), (28, 9.0),
    (29, 9.0), (30, 9.0), (31, 9.0), (32, 9.667), (33, 9.0), (34, 9.0),
    (35, 9.0), (36, 9.0), (37, 9.0), (38, 9.0),
]


def test_every_prototype_reports_its_height_from_the_drawing_never_fifteen(
    moxy_prototype_fills,
):
    for page, expected in MOXY_PROTOTYPE_HEIGHTS:
        for fill in moxy_prototype_fills[page]:
            assert fill.wall_height_source == "drawing", (
                "p%d %s: source %r — the poisoned 15 ft 'plan' answer was "
                "armed and must lose to the drawing's own tag"
                % (page, fill.viewport_title, fill.wall_height_source)
            )
            assert fill.wall_height_ft == pytest.approx(expected, abs=0.01), (
                "p%d %s: height %r" % (page, fill.viewport_title,
                                       fill.wall_height_ft)
            )
            assert fill.wall_height_ft != 15.0


def test_the_aff_mounting_tags_on_the_real_em_clips_are_excluded():
    """p38 ACC BUNK EM clip prints 8'-1\"AFF and 7'-4\"AFF — both in band,
    both mounting heights. Neither may surface as a ceiling tag."""
    import os

    if not os.path.exists(MOXY_PDF):
        pytest.skip("the real Moxy plan set is not present")
    from bobbytailor.deterministic.printed_scale import extract_printed_scales
    from bobbytailor.deterministic.room_fill import plan_titles
    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    doc = fitz.open(MOXY_PDF)
    try:
        page = doc[38]
        scales = extract_printed_scales(page)
        em = [tb for name, kind, tb in plan_titles(page) if kind == "EM"]
        assert em, "ACC BUNK - EM PLAN must exist on page 38"
        _ps, clip = pipe._fill_clip_for_title(page, scales, em[0])
        assert clip is not None
        heights = drawing_ceiling_heights(page, clip)
        assert 8.083 not in [round(h, 3) for h in heights]
        assert 7.333 not in [round(h, 3) for h in heights]
    finally:
        doc.close()


# The INV-01 §4 prototypes: pages 23/27/29 leak on the architectural fill
# (8.62 / 9.04 / 8.54); page 33's architectural fill is HONEST (4.37) and the
# measurement wins over the plan's "four architectural zeros" literal, exactly
# as 23-09 pinned 451.1 over the plan's 451.0.
MOXY_AR_LEAK_PAGES = [23, 27, 29]


def test_the_reflected_ceiling_fill_bills_a_perimeter_on_the_inv01_prototypes(
    moxy_prototype_fills,
):
    for page in (23, 27, 29, 33):
        fill = _dominant(moxy_prototype_fills, page, "RCP")
        billable, _reason = wall_perimeter_for_unit(fill)
        assert billable > 0.0, "p%d RCP must bill a perimeter" % page


@pytest.mark.parametrize("page", MOXY_AR_LEAK_PAGES)
def test_the_leaking_architectural_fill_refuses_with_a_reason(
    moxy_prototype_fills, page,
):
    """The leak signature reproduced blind: zero + a reason, never a number."""
    fill = _dominant(moxy_prototype_fills, page, "AR")
    billable, reason = wall_perimeter_for_unit(fill)
    assert billable == 0.0
    assert "shape ratio" in reason and "UNMEASURED" in reason


def test_the_honest_architectural_fill_on_page_33_bills_its_perimeter(
    moxy_prototype_fills,
):
    """BUNK B AR measures 4.37 — inside the honest band. A detector that fired
    everywhere would be a gate, not a detector (23-09: 'it is not a detector
    that fires everywhere')."""
    fill = _dominant(moxy_prototype_fills, 33, "AR")
    billable, _reason = wall_perimeter_for_unit(fill)
    assert billable > 0.0


# ── elevation facades: complement labelling + callout titles (23-14) ─────────
#
# A facade is a FILLED SILHOUETTE subdivided by joint/reveal lines, not a void
# enclosed by walls: the room flood fill fragments Bob's front elevation into
# 63 pieces, while the complement of the border-connected background returns
# ONE blob per elevation on all three fixtures that draw them (INV-03 §3).

BOBS_PDF = "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
CROW_UPLOAD_PDF = "uploads/Crow - Cass White Road-Plans.pdf"
CHELSEA_PDF = "uploads/Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"

# 1/8" = 1'-0" — the elevation scale on Bob's and Chelsea.
FPP_EIGHTH = 8.0 / 72.0


def _facade_page(width_ft=40.0, height_ft=20.0, fpp=FPP_EIGHTH):
    """A page holding one filled rectangle of a KNOWN size — exact ground truth."""
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    x0, y0 = 100.0, 100.0
    rect = fitz.Rect(x0, y0, x0 + width_ft / fpp, y0 + height_ft / fpp)
    page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0), width=0.5)
    clip = fitz.Rect(rect.x0 - 40, rect.y0 - 40, rect.x1 + 40, rect.y1 + 40)
    return doc, page, rect, clip


def test_a_filled_rectangle_measures_its_known_area_and_bbox():
    """Exact ground truth: 40 x 20 ft at 1/8\" = 1'-0\" is 800 SF."""
    from bobbytailor.deterministic.room_fill import measure_facade_area

    doc, page, _rect_, clip = _facade_page(40.0, 20.0)
    try:
        result = measure_facade_area(page, clip, FPP_EIGHTH, candidate_id="F1")
        assert result is not None
        assert abs(result.area_sf - 800.0) / 800.0 < 0.02
        w_ft, h_ft = result.bbox_ft
        assert abs(w_ft - 40.0) / 40.0 < 0.02
        assert abs(h_ft - 20.0) / 20.0 < 0.02
        assert result.fill_ratio > 0.95, "a filled rectangle fills its own bbox"
        assert result.component_count == 1
        assert result.candidate_id == "F1"
    finally:
        doc.close()


def test_a_subdivided_rectangle_is_still_one_component_of_the_same_area():
    """THE property the void fill lacks: joint lines subdivide free space but
    never disconnect ink, so the silhouette stays whole. The same drawing
    measured as voids returns one fragment per cell."""
    from bobbytailor.deterministic.room_fill import measure_facade_area

    fpp = FPP_EIGHTH
    doc = fitz.open()
    page = doc.new_page(width=800, height=600)
    x0, y0 = 100.0, 100.0
    x1, y1 = x0 + 40.0 / fpp, y0 + 20.0 / fpp
    for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                 ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        page.draw_line(fitz.Point(*a), fitz.Point(*b), width=1.0)
    # thin interior "joint" lines cutting the facade into six cells
    for fx in (x0 + (x1 - x0) / 3, x0 + 2 * (x1 - x0) / 3):
        page.draw_line(fitz.Point(fx, y0), fitz.Point(fx, y1), width=1.0)
    page.draw_line(fitz.Point(x0, (y0 + y1) / 2), fitz.Point(x1, (y0 + y1) / 2),
                   width=1.0)
    clip = fitz.Rect(x0 - 40, y0 - 40, x1 + 40, y1 + 40)
    try:
        result = measure_facade_area(page, clip, fpp)
        assert result is not None
        assert result.component_count == 1, (
            "joint lines must not fragment the silhouette"
        )
        assert abs(result.area_sf - 800.0) / 800.0 < 0.02
        # contrast: the void fill sees the six cells, not one facade
        voids = measure_enclosed_area(page, clip, fpp)
        assert voids is not None and len(voids.regions) >= 6
    finally:
        doc.close()


def test_an_opening_stays_in_the_gross_and_appears_in_the_void_list():
    """Gross beside net: a window opening is INSIDE the silhouette. The gross
    keeps it; the void list names it so a net can be derived."""
    from bobbytailor.deterministic.room_fill import measure_facade_area

    fpp = FPP_EIGHTH
    doc, page, rect, clip = _facade_page(40.0, 20.0, fpp)
    opening = fitz.Rect(rect.x0 + 10.0 / fpp, rect.y0 + 5.0 / fpp,
                        rect.x0 + 20.0 / fpp, rect.y0 + 10.0 / fpp)
    page.draw_rect(opening, color=(1, 1, 1), fill=(1, 1, 1), width=0.5)
    try:
        result = measure_facade_area(page, clip, fpp)
        assert result is not None
        assert abs(result.area_sf - 800.0) / 800.0 < 0.02, (
            "the gross includes the opening"
        )
        assert any(abs(v - 50.0) / 50.0 < 0.1 for v in result.void_areas_sf), (
            "the 10 x 5 ft opening must appear in the void list, got %r"
            % (result.void_areas_sf,)
        )
    finally:
        doc.close()


def test_measure_facade_area_returns_none_and_never_raises_on_failure():
    from bobbytailor.deterministic.room_fill import measure_facade_area

    doc, page, _rect_, clip = _facade_page()
    try:
        assert measure_facade_area(page, clip, 0.0) is None
        assert measure_facade_area(page, clip, -1.0) is None
    finally:
        doc.close()

    class _Broken:
        def get_pixmap(self, **_kw):
            raise RuntimeError("defective page")

    assert measure_facade_area(_Broken(), (0, 0, 10, 10), FPP_EIGHTH) is None


def test_elevation_titles_returns_empty_on_a_page_with_nothing():
    from bobbytailor.deterministic.room_fill import elevation_titles

    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    try:
        assert elevation_titles(page) == []
    finally:
        doc.close()


def test_elevation_titles_on_bobs_page_4_flags_the_demolition(tmp_path):
    """Four elevations found by their OWN titles — including the demolition,
    whose callout block absorbed a keynote sentence and whose real title is a
    dedicated 25 pt line on the callout's baseline."""
    import os

    if not os.path.exists(BOBS_PDF):
        pytest.skip("the real Bob's plan set is not present")
    from bobbytailor.deterministic.room_fill import elevation_titles

    doc = fitz.open(BOBS_PDF)
    try:
        entries = elevation_titles(doc[4])
    finally:
        doc.close()
    assert len(entries) >= 4
    demo = [e for e in entries if e.is_demo]
    assert len(demo) == 1
    assert demo[0].title == "FRONT ELEVATION DEMOLITION"
    assert demo[0].orientation == "FRONT"
    by_title = {e.title: e for e in entries}
    assert by_title["FRONT ELEVATION NEW"].orientation == "FRONT"
    assert by_title["REAR ELEVATION NEW"].orientation == "REAR"
    assert by_title["TRUCK DOCK ELEVATION NEW"].orientation == "TRUCK DOCK"
    assert not by_title["FRONT ELEVATION NEW"].is_demo


def test_elevation_titles_on_crow_page_1_returns_the_four_orientations():
    import os

    if not os.path.exists(CROW_UPLOAD_PDF):
        pytest.skip("the real Crow plan set is not present")
    from bobbytailor.deterministic.room_fill import elevation_titles

    doc = fitz.open(CROW_UPLOAD_PDF)
    try:
        entries = elevation_titles(doc[1])
    finally:
        doc.close()
    assert len(entries) == 4
    assert {e.orientation for e in entries} == {"NORTH", "SOUTH", "EAST", "WEST"}
    assert not any(e.is_demo or e.is_interior for e in entries)


def test_elevation_titles_on_chelsea_page_9_returns_four_entries():
    import os

    if not os.path.exists(CHELSEA_PDF):
        pytest.skip("the real Chelsea plan set is not present")
    from bobbytailor.deterministic.room_fill import elevation_titles

    doc = fitz.open(CHELSEA_PDF)
    try:
        entries = elevation_titles(doc[9])
    finally:
        doc.close()
    assert len(entries) == 4
    orientations = sorted(e.orientation for e in entries)
    assert orientations == ["BACK", "FRONT", "SIDE", "SIDE"]


def _elev_band_clips(page, entries):
    """Minimal band clips for a TITLES-ONLY test: previous elevation callout
    (or page edge) up to this callout, split at x-midpoints between callouts
    sharing a band. The production clip — viewport-bounded — is
    ``TakeoffPipeline._measure_elevation_areas``'s (23-14 Task 3)."""
    clips = []
    for e in entries:
        x0c, y0c, x1c, y1c = e.callout_bbox_pt
        prev = 0.0
        for o in entries:
            if o.callout_bbox_pt[3] <= y0c and o.callout_bbox_pt[3] > prev:
                prev = o.callout_bbox_pt[3]
        x0, x1 = 0.0, page.rect.width
        cx = (x0c + x1c) / 2
        for o in entries:
            if o is e:
                continue
            ox0, oy0, ox1, oy1 = o.callout_bbox_pt
            if min(oy1, y1c) - max(oy0, y0c) <= 0:
                continue
            ocx = (ox0 + ox1) / 2
            if ocx < cx:
                x0 = max(x0, (ox1 + x0c) / 2)
            elif ocx > cx:
                x1 = min(x1, (x1c + ox0) / 2)
        clips.append(fitz.Rect(x0 + 2, prev + 2, x1 - 2, y0c - 2))
    return clips


def test_chelsea_facades_have_one_dominant_component_per_titled_elevation():
    """A different drafting office, same code, no tuning: every titled
    elevation on pages 9-12 yields ONE dominant silhouette (largest component
    at least twice the runner-up)."""
    import os

    if not os.path.exists(CHELSEA_PDF):
        pytest.skip("the real Chelsea plan set is not present")
    from bobbytailor.deterministic.room_fill import (
        elevation_titles,
        measure_facade_area,
    )

    doc = fitz.open(CHELSEA_PDF)
    measured = 0
    try:
        for pno in (9, 10, 11, 12):
            page = doc[pno]
            entries = elevation_titles(page)
            assert len(entries) == 4, "page %d must title four elevations" % pno
            for e, clip in zip(entries, _elev_band_clips(page, entries)):
                result = measure_facade_area(
                    page, from_page_space(page, clip),
                    e.scale.feet_per_point,
                )
                assert result is not None, "%s p%d measured nothing" % (e.title, pno)
                if result.sub_components:
                    ratio = result.area_sf / result.sub_components[0]["area_sf"]
                    assert ratio >= 2.0, (
                        "%s p%d: dominant %.0f SF vs runner-up %.0f SF"
                        % (e.title, pno, result.area_sf,
                           result.sub_components[0]["area_sf"])
                    )
                measured += 1
    finally:
        doc.close()
    assert measured == 16


def test_bobs_front_elevation_silhouette_and_its_detached_sign_band():
    """The INV-03 §3.2 numbers, reproduced by the shipped code: the front
    facade is ONE 6,245 SF blob 249 ft wide, and the EIFS sign band is a
    detached ~142 SF sub-component the material pass can later claim."""
    import os

    if not os.path.exists(BOBS_PDF):
        pytest.skip("the real Bob's plan set is not present")
    from bobbytailor.deterministic.room_fill import measure_facade_area

    doc = fitz.open(BOBS_PDF)
    try:
        page = doc[4]
        # The FRONT ELEVATION NEW band, in page space (probe-derived: from the
        # demolition callout's bottom to the front callout's top).
        clip = from_page_space(page, fitz.Rect(104, 516, 2351, 1029))
        result = measure_facade_area(page, clip, 8.0 / 72.0)
    finally:
        doc.close()
    assert result is not None
    assert abs(result.area_sf - 6245.0) < 65.0
    assert 245.0 <= result.bbox_ft[0] <= 255.0
    assert any(
        abs(sub["area_sf"] - 142.0) < 15.0 and abs(sub["bbox_ft"][0] - 32.0) < 4.0
        for sub in result.sub_components
    ), "the detached sign band must be reported as a sub-component"


# ── elevation datums: the drawing's own vertical ruler (23-14 Task 2) ────────


def test_elevation_datums_reads_the_crow_north_ladder():
    """The INV-03 §2.2 ladder, verbatim: T/ PANEL 45'-2\", T/ PANEL AT GUTTER
    37'-9\", FINISH FLOOR 0'-0\", TRUCK COURT -4'-0\" — including the sign."""
    import os

    if not os.path.exists(CROW_UPLOAD_PDF):
        pytest.skip("the real Crow plan set is not present")
    from bobbytailor.deterministic.room_fill import (
        datum_wall_band,
        elevation_datums,
    )

    doc = fitz.open(CROW_UPLOAD_PDF)
    try:
        # The OVERALL NORTH ELEVATION band (page space, probe-derived).
        clip = fitz.Rect(382, 1626, 2608, 1968)
        datums = elevation_datums(doc[1], clip)
    finally:
        doc.close()
    feet = sorted(round(f, 2) for _y, f, _l in datums)
    assert 45.17 in feet, "T/ PANEL 45'-2\" must parse (got %r)" % feet
    assert 37.75 in feet, "T/ PANEL AT GUTTER 37'-9\" must parse"
    assert 0.0 in feet, "FINISH FLOOR 0'-0\" must parse"
    assert -4.0 in feet, "TRUCK COURT -4'-0\" must parse WITH its sign"
    labels = " | ".join(l for _y, _f, l in datums)
    assert "FINISH FLOOR" in labels and "T/ PANEL" in labels
    band = datum_wall_band(datums)
    assert band is not None
    y_top, y_floor, span = band
    assert abs(span - 45.17) < 0.01
    assert y_top < y_floor, "the top datum sits above the floor as read"


def test_cropping_the_crow_facade_to_its_wall_band_lands_on_the_parapet():
    """Uncropped, the north blob bbox reads 56 ft against a 45'-2\" parapet
    (grid bubbles and dimension strings above the panel). Cropped to the
    datum band it must land within ten percent of the printed datum."""
    import os

    if not os.path.exists(CROW_UPLOAD_PDF):
        pytest.skip("the real Crow plan set is not present")
    from bobbytailor.deterministic.room_fill import (
        datum_wall_band,
        elevation_datums,
        measure_facade_area,
    )

    doc = fitz.open(CROW_UPLOAD_PDF)
    try:
        page = doc[1]
        clip = fitz.Rect(382, 1626, 2608, 1968)   # north band, page space
        fpp = 40.0 / 72.0
        raw = measure_facade_area(page, from_page_space(page, clip), fpp)
        assert raw is not None
        assert 50.0 <= raw.bbox_ft[1] <= 66.0, (
            "uncropped the blob runs over the parapet (measured 56 ft)"
        )
        band = datum_wall_band(elevation_datums(page, clip))
        assert band is not None
        cropped = measure_facade_area(
            page, from_page_space(page, clip), fpp,
            crop_band_pt=(band[0], band[1]),
        )
    finally:
        doc.close()
    assert cropped is not None and cropped.band_cropped
    parapet = band[2]
    assert abs(cropped.bbox_ft[1] - parapet) / parapet < 0.10, (
        "cropped height %.1f ft must be within 10%% of the %.2f ft datum span"
        % (cropped.bbox_ft[1], parapet)
    )
    assert cropped.area_uncropped_sf is not None
    assert cropped.area_sf < cropped.area_uncropped_sf


def test_the_datum_scale_band_accepts_crow_and_rejects_a_16x_misparse():
    """The derived scale is a ±30%% plausibility band ONLY — noisy (Crow
    measures 0.79-0.85x printed because label baselines are offset from
    their leaders) but still tight enough to reject the Bob's-class
    sixteen-times misparse."""
    import os

    if not os.path.exists(CROW_UPLOAD_PDF):
        pytest.skip("the real Crow plan set is not present")
    from bobbytailor.deterministic.room_fill import (
        datum_scale_check,
        elevation_datums,
    )

    doc = fitz.open(CROW_UPLOAD_PDF)
    try:
        datums = elevation_datums(doc[1], fitz.Rect(382, 1626, 2608, 1968))
    finally:
        doc.close()
    fpp = 40.0 / 72.0
    assert datum_scale_check(datums, fpp) is True
    # A sixteen-times misparse (0.5 ft/in instead of 8.0 — scaled here to the
    # 40 ft/in drawing) is far outside the band.
    assert datum_scale_check(datums, fpp / 16.0) is False
    assert datum_scale_check(datums, fpp * 16.0) is False
    assert datum_scale_check([], fpp) is None
    assert datum_scale_check(datums, 0.0) is None


def test_a_clip_with_no_datum_pair_yields_no_band():
    """Bob's page 4 prints NO datum ladder; Moxy's civic ladder is sea-level
    based (T/ ROOF 969'-2\") — neither yields a wall band, and the caller
    flags rather than crops by a guess."""
    import os

    from bobbytailor.deterministic.room_fill import (
        datum_wall_band,
        elevation_datums,
    )

    # Synthetic: a ladder with no zero-feet floor refuses.
    assert datum_wall_band([(100.0, 969.17, "T/ ROOF"), (300.0, 963.5, "LEVEL 1")]) is None
    assert datum_wall_band([]) is None
    assert datum_wall_band([(100.0, 45.17, "T/ PANEL")]) is None

    if not os.path.exists(BOBS_PDF):
        pytest.skip("the real Bob's plan set is not present")
    doc = fitz.open(BOBS_PDF)
    try:
        # The FRONT ELEVATION NEW band (page space).
        datums = elevation_datums(doc[4], fitz.Rect(104, 516, 2351, 1029))
    finally:
        doc.close()
    assert datum_wall_band(datums) is None


def test_aff_mounting_heights_never_become_datums():
    """+16'-0\" AFF on Bob's truck dock is an awning height, not a datum —
    excluded by MARKER, exactly as the ceiling harvest excludes it."""
    import os

    if not os.path.exists(BOBS_PDF):
        pytest.skip("the real Bob's plan set is not present")
    from bobbytailor.deterministic.room_fill import elevation_datums

    doc = fitz.open(BOBS_PDF)
    try:
        # The TRUCK DOCK band, which prints T/ AWNING +16'-0" AFF and
        # 35'-3" OPENING dimension strings.
        datums = elevation_datums(doc[4], fitz.Rect(584, 1541, 1376, 2093))
    finally:
        doc.close()
    feet = [round(f, 2) for _y, f, _l in datums]
    assert 16.0 not in feet, "an AFF mounting height is never a datum"
    assert 35.25 not in feet, "an OPENING dimension is never a datum"
