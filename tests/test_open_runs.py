"""Layer-1 tests for the SP-5 open-polyline run chainer core.

Every geometric assertion here has EXACT synthetic ground truth: the test draws
the lines, so it knows the answer before it asks. No assertion in this file is
made against a golden take-off quantity — the chainer is validated by position
and span, per the phase's never-tune-to-golden rule (D-07).
"""
from __future__ import annotations

import time
from pathlib import Path

import fitz
import pytest

from bobbytailor.deterministic.open_runs import (
    CONTINUITY_DEG,
    GAP_TOL_PT,
    MAX_PITCH_OVER_SPAN,
    MIN_INK_FRACTION,
    PAIR_OFFSET_MAX_FT,
    STUB_HOPS,
    STUB_MAX_PT,
    OpenRun,
    _linetype_gates_pass,
    clamp_run,
    extract_linetype_runs,
    extract_open_runs,
    run_lf,
)
from bobbytailor.deterministic.walls import MAX_SEGMENTS, MIN_THICKNESS_FT

# 1/4" = 1'-0" — Crow's enlarged ramp plan, INV-06 §1.3.
QUARTER_FPP = 1.0 / 18.0
HALF_FPP = 1.0 / 36.0  # 1/2" = 1'-0" — Crow's STAIR PLAN
PAGE = (0.0, 0.0, 600.0, 600.0)

FIXTURES = Path(__file__).parent / "fixtures"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"
BOBS_PDF = FIXTURES / "bobs_discount" / "bobs_discount_plans.pdf"
BOBS_TAKEOFF = FIXTURES / "bobs_discount" / "bobs_discount_takeoff.pdf"

# Chelsea and Moxy carry no committed fixture; the zero-false-positive sweep
# reads the real uploads and skips cleanly when they are absent (the same
# convention as tests/test_naming_conventions.py).
UPLOADS = Path(__file__).parent.parent / "uploads"
CHELSEA_UPLOAD = UPLOADS / "Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"
MOXY_UPLOAD = UPLOADS / "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"


def _page(draw):
    doc = fitz.open()
    page = doc.new_page(width=600, height=600)
    draw(page)
    return doc, page


def _runs(draw, fpp=QUARTER_FPP, clip=PAGE, **kw):
    doc, page = _page(draw)
    try:
        return extract_open_runs(page, doc, clip, fpp, **kw)
    finally:
        doc.close()


# ── Collinear merge across a bridged gap ─────────────────────────────────────


def test_three_collinear_pieces_under_the_gap_tolerance_are_one_run():
    """A linetype's breaks are pipe, not absence of pipe: length is the SPAN."""
    def draw(page):
        # Three 60 pt pieces with 20 pt gaps (< GAP_TOL_PT = 48).
        for x in (100.0, 180.0, 260.0):
            page.draw_line(fitz.Point(x, 300), fitz.Point(x + 60, 300), width=0.5)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 1
    assert runs[0].length_pt == pytest.approx(220.0, abs=0.01)
    assert runs[0].polyline_pt[0] == pytest.approx((100.0, 300.0))
    assert runs[0].polyline_pt[-1] == pytest.approx((320.0, 300.0))
    # Ink is the drawn 180 pt; the 40 pt of bridged gap is span, not ink.
    assert runs[0].ink_pt == pytest.approx(180.0, abs=0.01)


def test_the_same_three_pieces_beyond_the_gap_tolerance_are_three_runs():
    def draw(page):
        for x in (60.0, 60.0 + 60 + GAP_TOL_PT + 20, 60.0 + 2 * (60 + GAP_TOL_PT + 20)):
            page.draw_line(fitz.Point(x, 300), fitz.Point(x + 60, 300), width=0.5)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 3
    for run in runs:
        assert run.length_pt == pytest.approx(60.0, abs=0.01)


def test_a_bridged_gap_run_is_flagged_when_it_is_mostly_gap():
    """Kept and flagged — never deleted, never silently believed."""
    def draw(page):
        for x in (100.0, 100.0 + 4 + 40, 100.0 + 2 * (4 + 40)):
            page.draw_line(fitz.Point(x, 300), fitz.Point(x + 4, 300), width=0.5)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 1
    assert runs[0].ink_fraction < MIN_INK_FRACTION
    assert runs[0].needs_review is True
    assert "bridged gap" in runs[0].review_reason


# ── Parallel-pair collapse ───────────────────────────────────────────────────


def test_a_rail_offset_pair_collapses_to_one_run_of_the_mean_length():
    """A rail is drawn as two faces; without the collapse it reports at 2x."""
    # 1 1/2" O.D. pipe = 0.125 ft = 2.25 pt at 1/4" scale.
    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(400, 300), width=0.3)
        page.draw_line(fitz.Point(100, 302.25), fitz.Point(380, 302.25), width=0.3)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 1
    assert runs[0].paired is True
    assert runs[0].length_pt == pytest.approx((300.0 + 280.0) / 2.0, abs=0.05)


def test_a_pair_at_or_above_the_wall_minimum_thickness_does_not_collapse():
    """A rail and a wall can never claim the same segment pair (T-23-40)."""
    offset = MIN_THICKNESS_FT / QUARTER_FPP  # exactly 3" — a wall, not a rail
    assert PAIR_OFFSET_MAX_FT == MIN_THICKNESS_FT

    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(400, 300), width=0.3)
        page.draw_line(
            fitz.Point(100, 300 + offset), fitz.Point(400, 300 + offset),
            width=0.3,
        )

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 2
    assert all(r.paired is False for r in runs)
    for run in runs:
        assert run.length_pt == pytest.approx(300.0, abs=0.05)


def test_two_parallel_faces_that_barely_overlap_do_not_collapse():
    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(250, 300), width=0.3)
        page.draw_line(fitz.Point(400, 302.25), fitz.Point(550, 302.25), width=0.3)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 2
    assert all(r.paired is False for r in runs)


# ── Direction continuity ─────────────────────────────────────────────────────


def test_a_turn_beyond_the_continuity_window_terminates_the_chain():
    """The 20° window is what separates a rail from a hatch fan."""
    import math

    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(300, 300), width=0.3)
        # A 60° turn at the joint — far outside the window.
        end = (300 + 200 * math.cos(math.radians(60)),
               300 + 200 * math.sin(math.radians(60)))
        page.draw_line(fitz.Point(300, 300), fitz.Point(*end), width=0.3)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 2
    for run in runs:
        assert len(run.polyline_pt) == 2


def test_a_turn_inside_the_continuity_window_is_absorbed_into_one_polyline():
    import math

    assert CONTINUITY_DEG == 20.0
    turn = math.radians(10.0)

    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(300, 300), width=0.3)
        end = (300 + 200 * math.cos(turn), 300 + 200 * math.sin(turn))
        page.draw_line(fitz.Point(300, 300), fitz.Point(*end), width=0.3)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 1
    assert len(runs[0].polyline_pt) == 3
    assert runs[0].length_pt == pytest.approx(400.0, abs=0.1)


# ── Bounded single-hop stub closure ──────────────────────────────────────────


def test_a_short_free_ended_stub_is_absorbed_with_one_hop():
    assert STUB_HOPS == 1

    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(400, 300), width=0.3)
        # A 40 pt riser at a right angle — no continuity, so only the stub
        # pass can take it.
        page.draw_line(fitz.Point(400, 300), fitz.Point(400, 340), width=0.3)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 1
    assert runs[0].length_pt == pytest.approx(340.0, abs=0.1)


def test_the_second_hop_is_never_taken():
    """The +/-5% band is the contract; a second hop absorbs arrowheads."""
    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(400, 300), width=0.3)
        page.draw_line(fitz.Point(400, 300), fitz.Point(400, 340), width=0.3)
        page.draw_line(fitz.Point(400, 340), fitz.Point(440, 340), width=0.3)

    runs = _runs(draw, min_run_ft=1.0)
    total = sum(r.length_pt for r in runs)
    # 300 + 40 absorbed; the second 40 pt hop stays its own sub-minimum piece.
    main = max(runs, key=lambda r: r.length_pt)
    assert main.length_pt == pytest.approx(340.0, abs=0.1)
    assert total == pytest.approx(380.0, abs=0.1)


def test_a_stub_longer_than_the_cap_is_not_absorbed():
    def draw(page):
        page.draw_line(fitz.Point(60, 300), fitz.Point(400, 300), width=0.3)
        page.draw_line(
            fitz.Point(400, 300), fitz.Point(400, 300 + STUB_MAX_PT + 30),
            width=0.3,
        )

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 2


# ── Points-until-scale-bound ─────────────────────────────────────────────────


def test_length_is_stored_in_points_and_converted_late():
    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(400, 300), width=0.3)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 1
    run = runs[0]
    quarter = run.length_lf(QUARTER_FPP)
    half = run.length_lf(1.0 / 36.0)
    assert quarter == pytest.approx(300.0 / 18.0)
    assert quarter / half == pytest.approx(2.0)
    assert run_lf(runs, QUARTER_FPP) == pytest.approx(round(quarter, 2))
    assert run_lf(runs, 0) == 0.0
    assert run.length_lf(0) == 0.0


def test_the_run_reports_its_own_geometry():
    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(400, 300), width=0.3)

    runs = _runs(draw, min_run_ft=1.0)
    run = runs[0]
    assert run.points_pt == [(100.0, 300.0), (400.0, 300.0)]
    assert run.bbox_pt == (100.0, 300.0, 400.0, 300.0)
    assert run.candidate_id == "RUN-1"
    payload = run.to_dict()
    assert payload["length_pt"] == run.length_pt
    assert payload["polyline_pt"] == [[100.0, 300.0], [400.0, 300.0]]
    assert payload["mark_signature"] is None


def test_the_candidate_prefix_is_a_parameter_not_a_fork():
    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(400, 300), width=0.3)

    runs = _runs(draw, min_run_ft=1.0, candidate_prefix="LIN")
    assert runs[0].candidate_id == "LIN-1"


# ── Clamp ────────────────────────────────────────────────────────────────────


def test_clamp_trims_a_run_to_an_arc_length_window():
    run = OpenRun(
        polyline_pt=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0)),
        length_pt=200.0,
        ink_pt=200.0,
    )
    trimmed = clamp_run(run, 50.0, 150.0)
    assert trimmed.length_pt == pytest.approx(100.0)
    assert trimmed.polyline_pt[0] == pytest.approx((50.0, 0.0))
    assert trimmed.polyline_pt[-1] == pytest.approx((100.0, 50.0))
    assert trimmed.ink_pt == pytest.approx(100.0)


def test_clamp_outside_the_run_yields_a_zero_length_run_not_a_crash():
    run = OpenRun(polyline_pt=((0.0, 0.0), (100.0, 0.0)), length_pt=100.0)
    trimmed = clamp_run(run, 500.0, 600.0)
    assert trimmed.length_pt == 0.0


# ── Guards: clip, scale, cap ─────────────────────────────────────────────────


def test_only_ink_inside_the_clip_is_chained():
    def draw(page):
        page.draw_line(fitz.Point(20, 100), fitz.Point(280, 100), width=0.3)
        page.draw_line(fitz.Point(20, 500), fitz.Point(280, 500), width=0.3)

    runs = _runs(draw, clip=(0.0, 0.0, 600.0, 300.0), min_run_ft=1.0)
    assert len(runs) == 1
    assert runs[0].polyline_pt[0][1] == pytest.approx(100.0)


def test_an_unclipped_or_unscaled_call_returns_nothing():
    """T-23-38: there is deliberately no unclipped entry point."""
    doc = fitz.open()
    page = doc.new_page(width=600, height=600)
    page.draw_line(fitz.Point(100, 300), fitz.Point(400, 300), width=0.3)
    assert extract_open_runs(page, doc, None, QUARTER_FPP) == []
    assert extract_open_runs(page, doc, (1.0, 2.0), QUARTER_FPP) == []
    assert extract_open_runs(page, doc, PAGE, 0) == []
    assert extract_open_runs(page, doc, PAGE, None) == []
    doc.close()


def test_a_blank_clip_returns_nothing():
    doc = fitz.open()
    page = doc.new_page(width=600, height=600)
    assert extract_open_runs(page, doc, PAGE, QUARTER_FPP) == []
    doc.close()


class _FakePoint:
    __slots__ = ("x", "y")

    def __init__(self, x, y):
        self.x = x
        self.y = y


class _FakePage:
    def __init__(self, n):
        a, b = _FakePoint(10.0, 10.0), _FakePoint(60.0, 10.0)
        self._paths = [{
            "type": "s",
            "width": 0.5,
            "color": (0.0, 0.0, 0.0),
            "items": [("l", a, b)] * n,
        }]

    def get_drawings(self):
        return self._paths


class _FakeDoc:
    def get_ocgs(self):
        return {}

    def layer_ui_configs(self):
        return {}


def test_an_over_cap_page_returns_empty_without_raising_and_under_two_seconds():
    """T-23-37: the cap is carried into the chainer's own harvest."""
    t0 = time.monotonic()
    runs = extract_open_runs(
        _FakePage(MAX_SEGMENTS + 10), _FakeDoc(), PAGE, QUARTER_FPP
    )
    elapsed = time.monotonic() - t0
    assert runs == []
    assert elapsed < 2.0


def test_a_broken_page_object_returns_empty_rather_than_raising():
    class _Exploding:
        def get_drawings(self):
            raise RuntimeError("malformed content stream")

    assert extract_open_runs(_Exploding(), _FakeDoc(), PAGE, QUARTER_FPP) == []


def test_runs_shorter_than_the_minimum_are_not_reported():
    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(140, 300), width=0.3)

    assert _runs(draw, min_run_ft=4.0) == []
    assert len(_runs(draw, min_run_ft=1.0)) == 1


def test_a_wall_pair_is_still_a_wall_and_a_rail_pair_is_still_a_rail():
    """The two bands are disjoint by reference, not by a copied literal."""
    from bobbytailor.deterministic import open_runs

    assert open_runs.PAIR_OFFSET_MAX_FT is MIN_THICKNESS_FT
    assert open_runs.PAIR_OFFSET_MIN_FT < MIN_THICKNESS_FT


# ── Real-PDF position validation against the estimator's own marks ───────────
#
# The five bboxes below are the Crow estimator's OWN measurement polylines,
# read out of the take-off PDF's coloured markup paths by INV-06 §1.3 and
# pinned there as literals. They are an ANSWER KEY, never pipeline input, and
# they are the only legitimate acceptance test for detection: the stamped
# totals (Guard Rail 420.35 LF / Hand Rail 438.80 LF) are a per-instance length
# times a multiplier the drawings do not print, so asserting on them would be
# tuning to a coincidence (INV-06 §4 risk 1).


def _find_run(runs, x0, y0, x1, y1, tol=5.0):
    """The run whose bbox matches the answer-key bbox on every edge."""
    for run in runs:
        b = run.bbox_pt
        if (abs(b[0] - x0) <= tol and abs(b[1] - y0) <= tol
                and abs(b[2] - x1) <= tol and abs(b[3] - y1) <= tol):
            return run
    return None


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
@pytest.mark.parametrize(
    "key_bbox,expect_lf,fpp",
    [
        ((1607, 868, 1607, 1169), 8.31, HALF_FPP),   # STAIR PLAN guard rail
        ((1766, 869, 1767, 1168), 8.31, HALF_FPP),   # STAIR PLAN guard rail
        ((275, 167, 1229, 167), 53.10, QUARTER_FPP),  # ENLARGED RAMP PLAN
    ],
)
def test_crow_page2_reproduces_an_estimator_rail_mark_by_position(
    key_bbox, expect_lf, fpp
):
    x0, y0, x1, y1 = key_bbox
    doc = fitz.open(CROW_PDF)
    clip = (min(x0, x1) - 60, min(y0, y1) - 60,
            max(x0, x1) + 60, max(y0, y1) + 60)
    runs = extract_open_runs(doc[2], doc, clip, fpp, min_run_ft=4.0)
    doc.close()

    # The rail's own drawn face sits a few points off the estimator's stroke,
    # so the match is on the ALONG-RUN extent, which is what is measured.
    along = [
        r for r in runs
        if abs(min(r.bbox_pt[0], r.bbox_pt[2]) - min(x0, x1)) <= 6.0
        and abs(max(r.bbox_pt[1], r.bbox_pt[3]) - max(y0, y1)) <= 6.0
        and abs(min(r.bbox_pt[1], r.bbox_pt[3]) - min(y0, y1)) <= 14.0
    ]
    assert along, (
        "no run reproduces the estimator's mark at %r; got %r"
        % (key_bbox, [(round(r.length_lf(fpp), 2), r.bbox_pt) for r in runs])
    )
    best = min(along, key=lambda r: abs(r.length_lf(fpp) - expect_lf))
    assert best.length_lf(fpp) == pytest.approx(expect_lf, rel=0.05)


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_the_stair_rail_faces_collapse_to_one_run_not_two():
    """Without the pair collapse every rail reports at 2x (INV-06 §2 step 4)."""
    doc = fitz.open(CROW_PDF)
    runs = extract_open_runs(
        doc[2], doc, (1547, 808, 1667, 1229), HALF_FPP, min_run_ft=4.0
    )
    doc.close()
    rail = _find_run(runs, 1605, 870, 1605, 1169, tol=6.0)
    assert rail is not None
    assert rail.paired is True
    assert rail.length_lf(HALF_FPP) == pytest.approx(8.31, rel=0.05)


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_chaining_a_thirty_three_thousand_segment_page_stays_bounded():
    """T-23-37/T-23-38 on real ink: Crow page 0 is the dense worst case.

    The clip here is the WHOLE page, which is not how the module is used — it
    is the worst case the guards must survive. The 987 junk runs this produces
    are the documented reason chaining is only offered inside a clip.
    """
    doc = fitz.open(CROW_PDF)
    page = doc[0]
    rect = page.rect
    t0 = time.monotonic()
    runs = extract_open_runs(
        page, doc, (rect.x0, rect.y0, rect.x1, rect.y1), 40.0 / 72.0,
        min_run_ft=4.0,
    )
    elapsed = time.monotonic() - t0
    doc.close()
    assert runs, "the dense page must still produce runs, not an empty guard"
    assert elapsed < 10.0, "chaining must stay a bounded hash-grid pass"


def test_the_wall_length_floor_is_not_applied_to_open_runs():
    """A 3 pt exploded dash must survive; walls' 2 ft floor would delete it."""
    from bobbytailor.deterministic.open_runs import MIN_SEG_PT
    from bobbytailor.deterministic.walls import MIN_WALL_SEG_FT

    assert MIN_SEG_PT == 3.0
    assert MIN_SEG_PT < MIN_WALL_SEG_FT / QUARTER_FPP

    def draw(page):
        for i in range(12):
            x = 100.0 + i * 20.0
            page.draw_line(fitz.Point(x, 300), fitz.Point(x + 4, 300), width=0.3)

    runs = _runs(draw, min_run_ft=1.0)
    assert len(runs) == 1
    assert runs[0].length_pt == pytest.approx(224.0, abs=0.1)


# ═════════════════════════════════════════════════════════════════════════════
# SELECTOR 1 — annotated linetypes (INV-04)
#
# Detection is validated by POSITION against the estimator's own traced markup
# and by SET (zero false positives across every page of the other three plan
# sets). No assertion anywhere in this section is made against a golden
# linear-foot quantity — the LF band assertion lives with run_scale_fpp,
# because it depends on the scale being right.
# ═════════════════════════════════════════════════════════════════════════════


def _draw_glyph_mark(page, cx, cy, strokes=24, w=10.0, h=1.5):
    """A synthetic SHX-style glyph: *strokes* micro-strokes in a w x h box."""
    for i in range(strokes):
        x = cx - w / 2.0 + i * (w / (strokes - 1))
        page.draw_line(fitz.Point(x, cy), fitz.Point(x, cy + h), width=0.3)


def test_a_synthetic_annotated_linetype_is_detected():
    """Dashes broken at a regular pitch by identical glyph marks are ONE run."""
    mark_xs = [133.0, 166.0, 199.0, 232.0, 265.0]  # pitch 33, glyph span 10

    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(mark_xs[0] - 7, 300), width=0.5)
        for a, b in zip(mark_xs, mark_xs[1:]):
            page.draw_line(fitz.Point(a + 7, 300), fitz.Point(b - 7, 300), width=0.5)
        page.draw_line(fitz.Point(mark_xs[-1] + 7, 300), fitz.Point(298, 300), width=0.5)
        for x in mark_xs:
            _draw_glyph_mark(page, x, 299.0)

    doc, page = _page(draw)
    try:
        runs = extract_linetype_runs(page, doc, PAGE)
    finally:
        doc.close()
    assert len(runs) == 1
    run = runs[0]
    assert run.candidate_id == "RUN-1"
    assert run.mark_signature is not None
    assert run.mark_signature[0] == 24  # stroke count is the grouping key
    stats = run.mark_stats
    assert stats["mark_count"] == 5
    assert stats["pitch_pt"] == pytest.approx(33.0, abs=0.5)
    assert stats["break_frac"] == 1.0
    # Span, not ink: the run is the full merged line, breaks included.
    assert run.length_pt == pytest.approx(198.0, abs=1.0)


def test_a_row_of_tags_on_an_unbroken_line_is_rejected():
    """Same marks, but the line runs CONTINUOUSLY beneath them: not a linetype.

    The break-fraction gate (S6d) is what fails here — a glyph drawn ON TOP of
    a line is a label, not the line's own texture.
    """
    mark_xs = [133.0, 166.0, 199.0, 232.0, 265.0]

    def draw(page):
        page.draw_line(fitz.Point(100, 300), fitz.Point(298, 300), width=0.5)
        for x in mark_xs:
            _draw_glyph_mark(page, x, 299.0)

    doc, page = _page(draw)
    try:
        runs = extract_linetype_runs(page, doc, PAGE)
    finally:
        doc.close()
    assert runs == []


def test_evenly_spaced_tags_with_pitch_far_wider_than_the_glyph_are_rejected():
    """The coincidence trap, synthesised: the line genuinely breaks at every
    tag and the pitch is machine-regular — break_frac 1.0, cv 0.0 — and ONLY
    the pitch-over-glyph-span ratio gate rejects it. This is the Crow "K.O."
    dock-panel shape: a 2 pt tag every 53 pt is a row of tagged objects, not a
    linetype whose mark IS its texture."""
    pitch, half_gap = 53.0, 3.0
    mark_xs = [120.0 + i * pitch for i in range(6)]

    def draw(page):
        page.draw_line(
            fitz.Point(80, 300), fitz.Point(mark_xs[0] - half_gap, 300), width=0.5
        )
        for a, b in zip(mark_xs, mark_xs[1:]):
            page.draw_line(
                fitz.Point(a + half_gap, 300), fitz.Point(b - half_gap, 300),
                width=0.5,
            )
        page.draw_line(
            fitz.Point(mark_xs[-1] + half_gap, 300), fitz.Point(450, 300),
            width=0.5,
        )
        for x in mark_xs:
            # 20 strokes crammed into a 2 x 2 box — a tiny tick tag.
            for i in range(20):
                px = x - 1.0 + i * (2.0 / 19.0)
                page.draw_line(
                    fitz.Point(px, 299), fitz.Point(px, 301), width=0.3
                )

    doc, page = _page(draw)
    try:
        runs = extract_linetype_runs(page, doc, PAGE)
    finally:
        doc.close()
    assert runs == []


def test_the_linetype_selector_requires_a_clip():
    doc = fitz.open()
    page = doc.new_page(width=600, height=600)
    page.draw_line(fitz.Point(100, 300), fitz.Point(400, 300), width=0.5)
    assert extract_linetype_runs(page, doc, None) == []
    assert extract_linetype_runs(page, doc, (1.0, 2.0)) == []
    doc.close()


# ── The permanent rejection fixtures ─────────────────────────────────────────
#
# These literals are the development history's caught coincidences, pinned so
# no future edit can loosen a gate without failing them first.


def test_the_crow_dock_panel_tag_row_stays_rejected():
    """INV-04 §3, the trap caught in the act: 34 identical tags of signature
    (54, 2, 2) evenly spaced at 53 pt along Crow page 1's dock grade line —
    and the grade line really IS broken at every tag, so break_frac is 1.00
    and the pitch is regular. Rendering it shows a dock elevation, not piping.
    Only the pitch-over-glyph-span gate rejects it: 53 / 2 = 26.5 > 6."""
    signature = (54, 2, 2)
    mark_count = 34
    pitch_pt = 53.0
    break_frac = 1.00

    glyph_span = float(signature[1])
    assert pitch_pt / glyph_span == pytest.approx(26.5)
    assert pitch_pt / glyph_span > MAX_PITCH_OVER_SPAN
    assert not _linetype_gates_pass(
        mark_count, pitch_pt, 0.0, glyph_span, break_frac
    )


def test_the_real_gas_linetype_passes_the_same_gates():
    """The gate literals INV-04 §2 measured for the run that IS a linetype —
    the non-vacuity half of the rejection fixtures."""
    assert _linetype_gates_pass(160, 33.7, 0.02, 10.0, 1.00)


@pytest.mark.parametrize(
    "signature,mark_count,pitch_pt,pitch_cv,break_frac",
    [
        # Re-measured on the real Chelsea sheets (INV-04 §6 records the family
        # as five 3-mark candidates at pitches 108-237): page 14 and 13/16
        # text-block alignments that a naive pitch-only detector accepts.
        ((32, 13, 9), 3, 108.1, 0.00, 0.00),
        ((19, 11, 9), 3, 117.7, 0.27, 0.67),
        ((31, 13, 5), 3, 122.4, 0.77, 0.00),
        ((18, 9, 5), 3, 153.1, 0.41, 0.00),
        ((18, 9, 5), 3, 216.1, 0.00, 0.00),
    ],
)
def test_the_chelsea_three_mark_candidates_stay_rejected(
    signature, mark_count, pitch_pt, pitch_cv, break_frac
):
    glyph_span = float(signature[1])
    # Each one fails the ratio gate on its own, before cv or break are asked.
    assert pitch_pt > MAX_PITCH_OVER_SPAN * glyph_span
    assert not _linetype_gates_pass(
        mark_count, pitch_pt, pitch_cv, glyph_span, break_frac
    )


# ── Real-PDF position recall: the only honest detection test ─────────────────


def _estimator_gas_polyline():
    """The estimator's own Gas Piping trace, read from the take-off PDF.

    ANSWER KEY ONLY, never pipeline input: 34 line segments in the markup
    colour (0.47, 0.94, 0.03) at width 4.8 on take-off page 0 (A3.0). The
    4-segment legend swatch — a small closed box by the legend text — is
    excluded by its tiny bbox (INV-04 §1).
    """
    green = (0.47, 0.94, 0.03)
    doc = fitz.open(BOBS_TAKEOFF)
    page = doc[0]
    segs = []
    for path in page.get_drawings():
        col = path.get("color")
        if col is None or any(abs(a - b) > 0.02 for a, b in zip(col, green)):
            continue
        if abs((path.get("width") or 0.0) - 4.8) > 0.5:
            continue
        rect = path["rect"]
        if max(rect.x1 - rect.x0, rect.y1 - rect.y0) < 60.0:
            continue  # the legend swatch
        for item in path["items"]:
            if item[0] == "l":
                segs.append(
                    ((item[1].x, item[1].y), (item[2].x, item[2].y))
                )
    doc.close()
    return segs


def _dist_to_segment(p, a, b):
    import math

    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    h2 = dx * dx + dy * dy
    if h2 == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / h2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


@pytest.mark.skipif(
    not (BOBS_PDF.is_file() and BOBS_TAKEOFF.is_file()),
    reason="Bob's fixtures missing",
)
def test_bobs_gas_marks_land_on_the_estimators_own_polyline():
    """POSITION RECALL: >= 95% of detected mark blobs within 12 pt of the
    polyline the human estimator actually traced (INV-04 observed 162/164 on
    raw candidate blobs; run-attached marks measure 160/160)."""
    key = _estimator_gas_polyline()
    assert len(key) == 34, "the answer key changed shape"

    doc = fitz.open(BOBS_PDF)
    page = doc[3]  # A3.0 ROOF PLAN
    rect = page.rect
    clip = (0.0, 0.0, max(rect.x1, rect.y1), max(rect.x1, rect.y1))
    runs = extract_linetype_runs(page, doc, clip)
    doc.close()

    assert runs, "the gas linetype was not detected at all"
    # One family, INV-04's measured signature.
    assert {r.mark_signature for r in runs} == {(39, 10, 4)}

    centers = [c for r in runs for c in r.mark_stats["mark_centers"]]
    assert len(centers) >= 100, "far fewer marks than the ~160 observed"
    on_key = sum(
        1
        for c in centers
        if min(_dist_to_segment(c, a, b) for a, b in key) <= 12.0
    )
    assert on_key / float(len(centers)) >= 0.95


@pytest.mark.skipif(not BOBS_PDF.is_file(), reason="Bob's PDF fixture missing")
def test_the_detector_is_silent_on_every_other_bobs_page():
    doc = fitz.open(BOBS_PDF)
    fired = {}
    for pno in range(len(doc)):
        if pno == 3:
            continue
        page = doc[pno]
        rect = page.rect
        clip = (0.0, 0.0, max(rect.x1, rect.y1), max(rect.x1, rect.y1))
        runs = extract_linetype_runs(page, doc, clip)
        if runs:
            fired[pno] = len(runs)
    doc.close()
    assert fired == {}


@pytest.mark.skipif(
    not (
        CROW_PDF.is_file()
        and CHELSEA_UPLOAD.is_file()
        and MOXY_UPLOAD.is_file()
    ),
    reason="the three-set sweep needs Crow + the Chelsea/Moxy uploads",
)
def test_zero_false_positives_across_all_76_pages_of_the_other_three_sets():
    """THE honesty test: the detector fires on nothing in Crow (4 pages),
    Chelsea (32) and Moxy (40) — 76 pages of three other drafting offices.
    A detector that finds annotated linetypes where none exist would be
    manufacturing quantities (T-23-45)."""
    fired = {}
    page_total = 0
    for path in (CROW_PDF, CHELSEA_UPLOAD, MOXY_UPLOAD):
        doc = fitz.open(path)
        for pno in range(len(doc)):
            page = doc[pno]
            rect = page.rect
            clip = (0.0, 0.0, max(rect.x1, rect.y1), max(rect.x1, rect.y1))
            runs = extract_linetype_runs(page, doc, clip)
            page_total += 1
            if runs:
                fired["%s p%d" % (path.name, pno)] = len(runs)
        doc.close()
    assert page_total == 76, "the sweep no longer covers the 76 pages"
    assert fired == {}
