"""29-05 — a drawing that MEASURED leaves a ledger row saying so. ZERO API.

This module was opened to prove a different claim: that Crow A-101's two
same-named ``OVERALL - AR PLAN`` titles collided, and that the one WITHOUT a
printed scale displaced the one with it, so the sheet's main drawing was never
measured. **The drawings say otherwise, and the drawings win.** Measured on
``tests/fixtures/crow_cass/crow_cass_plans.pdf`` page 0:

* ``plan_titles`` returns two boxes. #1 at x=2731..2955, y=1923..1945 is the
  TITLE BLOCK's own "OVERALL FLOOR PLAN" string — the sheet's name, printed in
  the stamp. The nearest scale callout is 573 pt away across the sheet, so it
  correctly pairs with nothing. #2 at x=2163..2443, y=1998..2023 is the real
  drawing title, and the 1" = 40'-0" callout centred at (2284.0, 2019.6) is
  -3.4 pt above its baseline and 33 pt off its midpoint — inside both
  ``_TITLE_SCALE_ABOVE_TOL_PT`` and ``_TITLE_SCALE_SIDE_PT``.
* So ``_fill_clip_for_title`` pairs #2, and ``_measure_room_fills`` measures it:
  FILL-2, 1716.7 SF at 40.00 ft/in. Nothing is lost, and no tolerance needs
  widening.

What was actually wrong is one line lower down. ``_measure_room_fills`` and
``_measure_elevation_areas`` returned a :class:`DrawingCoverage` row for every
drawing they REFUSED and none for any drawing they MEASURED, and
``_record_sheet_coverage`` copies exactly those rows onto the ledger. So
``summary()["drawings_measured"]`` — which counts MEASURED and MEASURED_PARTIAL
rows — was structurally 0, and it reads 0 in every saved run in ``output/``:
Crow, Bob's, Moxy and Chelsea alike. The 2026-08-16 paid Crow run is the proof
that the number is wrong rather than merely small: its ledger reports
``drawings_measured: 0`` for A-101 while its own ``fusion_rejected`` records
carry ``fill:FILL-2`` at 1716.7 SF, measured off that very sheet. A counter
that cannot be anything but zero is not a low reading; it is a false one, and
beside A-101's single legitimate skip row it reads as "this sheet measured
nothing".

Nothing here asserts a quantity that reaches a bill. The three SF rows Crow
publishes best — Exposed Structure and Sealed Concrete at 397,600 SF from the
printed schedule, Tilt Up Wall at 106,992 SF from WALL-TC1 — are produced by
paths this module does not touch, and FILL-2's own numbers are arbitrated away
upstream of any total.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import fitz  # noqa: E402

from bobbytailor.pipeline.coverage import (  # noqa: E402
    MEASURED,
    MEASURED_PARTIAL,
    SKIPPED_NO_SCALE,
    CoverageLedger,
)
from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline  # noqa: E402

CROW_FIXTURE = ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"
UPLOADS = ROOT / "uploads"
FOUR_SETS = {
    "crow": UPLOADS / "Crow - Cass White Road-Plans.pdf",
    "bobs": UPLOADS / "Bob's Discount Furniture - Kennesaw, GA-plans.pdf",
    "moxy": UPLOADS / "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
    "chelsea": (
        UPLOADS / "Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf"
    ),
}


def _need(path: Path) -> Path:
    """Skip by name rather than pass on an absent fixture (T-23-67)."""
    if not path.is_file():
        pytest.skip("fixture not present: %s" % path.name)
    return path


def _pipeline():
    return TakeoffPipeline(analyzer=lambda *a, **k: {})  # analyzer never called


@pytest.fixture(scope="module")
def crow_page0():
    _need(CROW_FIXTURE)
    doc = fitz.open(str(CROW_FIXTURE))
    try:
        yield doc[0]
    finally:
        doc.close()


@pytest.fixture(scope="module")
def crow_a101_coverage():
    """A-101's fills and their coverage rows, measured once for this module."""
    _need(CROW_FIXTURE)
    pipe = _pipeline()
    doc = fitz.open(str(CROW_FIXTURE))
    try:
        return pipe._measure_room_fills(doc[0], [], {}, "A-101")
    finally:
        doc.close()


# ═════════════════════════════════════════════════════════════════════════════
# (a) The real Crow page 0 case — the scale-bearing title is the one that
#     measures, and it is now on the record as having done so.
# ═════════════════════════════════════════════════════════════════════════════


def test_a101_prints_two_same_named_titles_and_exactly_one_pairs_to_a_scale(
    crow_page0,
):
    """The diagnosis, pinned: neither title is lost and neither is guessed at.

    Asserts the SPLIT, not the tolerances. If a future change lets the title
    block's own string pair to the drawing's callout, `paired` becomes 2 here
    and the sheet starts measuring the stamp.
    """
    from bobbytailor.deterministic.printed_scale import extract_printed_scales
    from bobbytailor.deterministic.room_fill import plan_titles

    pipe = _pipeline()
    scales = extract_printed_scales(crow_page0)
    titles = plan_titles(crow_page0)
    assert [(t[0], t[1]) for t in titles] == [("OVERALL", "AR"), ("OVERALL", "AR")]

    paired = [
        pipe._fill_clip_for_title(crow_page0, scales, tb)[0] is not None
        for _n, _k, tb in titles
    ]
    # The title-block string is first in reading order and pairs with nothing;
    # the drawing title is second and owns the 1" = 40'-0" callout.
    assert paired == [False, True]


def test_the_scale_bearing_title_is_the_one_that_measures(crow_a101_coverage):
    fills, _coverage = crow_a101_coverage
    assert [f.candidate_id for f in fills] == ["FILL-2"]
    assert fills[0].viewport_title == "OVERALL - AR PLAN"
    assert round(fills[0].area_sf, 1) == 1716.7
    assert round(fills[0].scale_fpi, 2) == 40.00


def test_the_measured_drawing_leaves_a_row_saying_it_was_measured(
    crow_a101_coverage,
):
    """The row the ledger was missing. Before 29-05 this list held FILL-1 only.

    A sheet is entitled to say what it measured, not only what it refused.
    """
    _fills, coverage = crow_a101_coverage
    measured = [c for c in coverage if c.disposition == MEASURED]
    assert [c.region_id for c in measured] == ["FILL-2"]
    assert measured[0].title == "OVERALL - AR PLAN"
    assert round(measured[0].area_sf, 1) == 1716.7
    assert measured[0].printed_scale_fpi == 40.0
    # The 1716.7 SF region flags against the drawing's own printed extent; the
    # row carries that flag rather than quietly presenting a clean measurement.
    assert measured[0].needs_review is True


# ═════════════════════════════════════════════════════════════════════════════
# (b) A title with no printed scale still refuses — it never borrows one, and
#     it never inherits the measured row of its same-named sibling.
# ═════════════════════════════════════════════════════════════════════════════


def test_a_title_with_no_scale_refuses_rather_than_borrowing_one(
    crow_a101_coverage,
):
    _fills, coverage = crow_a101_coverage
    refused = [c for c in coverage if c.disposition == SKIPPED_NO_SCALE]
    assert [c.region_id for c in refused] == ["FILL-1"]
    # None, never 0.0: a drawing that produced no number and a drawing that
    # measured zero square feet are different facts.
    assert refused[0].area_sf is None
    assert refused[0].printed_scale_fpi is None
    assert "borrowed scale" in refused[0].reason
    # Same name, same kind, one measured row — the refusal did not acquire the
    # sibling's 1716.7 SF and the sibling did not lose its row to the refusal.
    assert refused[0].title == "OVERALL - AR PLAN"
    assert len({c.region_id for c in coverage}) == 2


def test_the_ledger_counts_the_drawing_the_engine_measured(crow_a101_coverage):
    """End to end through the real ledger writer: 0 -> 1 on this sheet.

    Also pins what must NOT move: the sheet is still MEASURED_PARTIAL, because
    FILL-1 is still an unmeasured drawing on it. A MEASURED drawing row is
    invisible to `_record_sheet_coverage`'s `dropped` filter by construction.
    """
    _fills, coverage = crow_a101_coverage
    ledger = CoverageLedger()
    row = ledger.register_page(0, sheet_name="A-101", disposition=MEASURED)
    TakeoffPipeline._record_sheet_coverage(row, {"_coverage_drops": list(coverage)})

    assert ledger.summary()["drawings_measured"] == 1
    assert ledger.summary()["drawings_dropped_no_scale"] == 1
    assert row.disposition == MEASURED_PARTIAL


def test_the_elevation_sheet_records_the_facades_it_measured():
    """The same asymmetry, closed on the other producer.

    Crow A-201 (page 1) measures four facade silhouettes and refuses none, so
    before 29-05 it contributed NO drawing row at all — a sheet that measured
    four drawings and reported none.
    """
    _need(CROW_FIXTURE)
    pipe = _pipeline()
    doc = fitz.open(str(CROW_FIXTURE))
    try:
        facades, coverage = pipe._measure_elevation_areas(doc[1], [], "A-201")
    finally:
        doc.close()
    assert len(facades) == 4
    assert [c.region_id for c in coverage] == [
        "ELEV-1", "ELEV-2", "ELEV-3", "ELEV-4",
    ]
    assert {c.disposition for c in coverage} == {MEASURED}
    # Every row carries the number that was measured, so the ledger row is
    # auditable against the facade it stands for.
    assert [round(c.area_sf, 1) for c in coverage] == [
        round(f.area_sf, 1) for f in facades
    ]


# ═════════════════════════════════════════════════════════════════════════════
# (c) The four-set regression pins.
#
# Counted by walking every page of the four real plan sets with `plan_titles`
# and `_fill_clip_for_title` — the exact pair of calls the measurement gates
# on. These are read off the drawings; not one of them is fitted to a quantity,
# a golden take-off or an accuracy score. `paired` is the number that a change
# to either tolerance would move, and 29-05 moved neither: every literal below
# is IDENTICAL before and after the change.
# ═════════════════════════════════════════════════════════════════════════════

FOUR_SET_TITLE_CENSUS = {
    # set: (pages, plan titles, titles pairing to a printed scale)
    "crow": (4, 2, 1),
    # Bob's titles ten drawings and pairs NONE of them: its callouts sit beside
    # the title, not beneath it. That zero is the reason the tolerances may not
    # be loosened to "fix" a set — widening them until Bob's pairs is exactly
    # the coincidence trap, and Bob's measures its quantities by other routes.
    "bobs": (7, 10, 0),
    # Moxy is where the pairing does its work: 104 of 124 titles own a callout,
    # mostly the sixteen guestroom prototype sheets at 5-6 drawings each.
    "moxy": (40, 124, 104),
    "chelsea": (32, 15, 9),
}


@pytest.mark.parametrize("name", sorted(FOUR_SET_TITLE_CENSUS))
def test_the_four_set_title_and_scale_census_is_unchanged(name):
    from bobbytailor.deterministic.printed_scale import extract_printed_scales
    from bobbytailor.deterministic.room_fill import plan_titles

    path = _need(FOUR_SETS[name])
    pipe = _pipeline()
    doc = fitz.open(str(path))
    try:
        pages = doc.page_count
        titles = paired = 0
        for index in range(pages):
            page = doc[index]
            scales = extract_printed_scales(page)
            boxes = plan_titles(page) or []
            titles += len(boxes)
            for _n, _k, tb in boxes:
                if pipe._fill_clip_for_title(page, scales, tb)[0] is not None:
                    paired += 1
    finally:
        doc.close()
    assert (pages, titles, paired) == FOUR_SET_TITLE_CENSUS[name]
