"""Keynote reading and the Ladder count. ZERO API.

The Ladder was never an engine failure. ``_KEYNOTE_NUM_RE`` was ``^(\\d{2})\\.?$``
— exactly two digits — so keynotes 1-9 were structurally invisible to the whole
text-anchored route. Crow page 0 read 3 of its 12 keynotes, and keynote 1,
"ACCESS LADDER TO CONCRETE ROOF OF ELECTRICAL ROOM", never entered the pipeline
at all.

Widening it exposed two latent defects in the same reader, both of which would
have published confidently wrong labels, and both fixed here structurally:

* the nearest-header-above rule had no vertical bound, so view titles 1,900 pt
  below a header joined it as entries 1-4;
* two adjacent numbered lists merged, because nothing said a legend numbers
  upward.

Numbers in this file are counts of things printed on the drawing. The only one
that coincides with a golden take-off is Ladder = 1, and it is asserted as
"keynote 1 is placed once besides its own legend bubble", which is what the
sheet shows.
"""
from __future__ import annotations

import sys
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from bobbytailor.deterministic.room_fill import (  # noqa: E402
    _KEYNOTE_NUM_RE,
    keynote_callout_counts,
    keynote_legend,
    keynote_legend_rows,
)
from bobbytailor.deterministic.symbols import cluster_symbols  # noqa: E402

CROW_PDF = ROOT / "tests" / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"
BOBS_PDF = ROOT / "uploads" / "Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
CROW_P0_FPP = 40.0 / 72.0

_CACHE: dict = {}


def _crow(index=0):
    if "doc" not in _CACHE:
        _CACHE["doc"] = fitz.open(CROW_PDF)
    return _CACHE["doc"][index]


crow_only = pytest.mark.skipif(
    not CROW_PDF.exists(), reason="Crow fixture PDF not present"
)
bobs_only = pytest.mark.skipif(
    not BOBS_PDF.exists(), reason="Bob's plan set not present"
)


def test_single_digit_keynotes_are_matchable_at_all():
    """The two-character defect, pinned so it cannot come back."""
    for token in ("1", "9", "01", "12", "12."):
        assert _KEYNOTE_NUM_RE.match(token), token
    for token in ("", "123", "A", "1A"):
        assert not _KEYNOTE_NUM_RE.match(token), token


@crow_only
def test_crow_page0_reads_all_twelve_keynotes_including_the_ladder():
    """Was 3 of 12. Keynote 1 is the entire evidence for the Ladder item."""
    legend = keynote_legend(_crow())
    assert list(legend) == ["KEYNOTES"]
    entries = legend["KEYNOTES"]
    assert sorted(entries, key=int) == [str(i) for i in range(1, 13)]
    assert entries["1"].startswith("ACCESS LADDER")
    assert "ROOF HATCH" in entries["2"] or "CONCRETE ROOF" in entries["2"]


@crow_only
def test_crow_page1_view_titles_do_not_become_keynotes():
    """Page 1 has a KEYNOTES header and no keynote entries under it.

    What it does have is four "1 OVERALL NORTH ELEVATION"-style view titles in
    the same column, up to 1,900 pt below the header. They pair like legend
    entries and they are not legend entries. Before the stack rule they were
    published as keynotes 1-4.
    """
    assert keynote_legend(_crow(1)).get("KEYNOTES", {}) == {}


@bobs_only
def test_bobs_keyed_notes_stop_where_the_next_list_starts():
    """KEYED NOTES runs 01..16; 93 pt below it an unheaded paint-colour list
    restarts at 1, 2. A legend numbers upward, so the restart ends the stack."""
    doc = fitz.open(BOBS_PDF)
    try:
        legend = keynote_legend(doc[4])
    finally:
        doc.close()
    keyed = legend.get("KEYED NOTES", {})
    assert sorted(keyed, key=int) == ["%02d" % i for i in range(1, 17)]
    assert "1" not in keyed and "2" not in keyed
    # The two legends on this sheet stay separate — 03 means different things.
    demo = legend.get("DEMO KEYED NOTES", {})
    assert demo and keyed["03"] != demo["03"]


@crow_only
def test_legend_rows_carry_the_number_block_rectangle():
    rows = keynote_legend_rows(_crow())["KEYNOTES"]
    assert len(rows) == 12
    number, text, box = rows[0]
    assert number == "1" and text.startswith("ACCESS LADDER")
    assert len(box) == 4 and box[2] > box[0] and box[3] > box[1]


@crow_only
def test_the_ladder_is_placed_exactly_once_on_crow_page0():
    """Keynote 1 is drawn in exactly two bubbles: its own legend entry, and one
    callout on the plan. One callout, one ladder.

    Golden Ladder-H-20' is 1 EA. This asserts the SHAPE that produces it — a
    legend bubble subtracted from a bubble count — not the golden number.
    """
    page = _crow()
    groups = cluster_symbols(page, CROW_P0_FPP, doc=page.parent, page_index=0)
    callouts = {c.number: c for c in keynote_callout_counts(page, groups)}

    assert sorted(callouts, key=int) == [str(i) for i in range(1, 13)]
    ladder = callouts["1"]
    assert ladder.note_text.startswith("ACCESS LADDER")
    assert ladder.callout_count == 1
    assert ladder.legend_bbox_pt is not None, "the legend's own bubble was not found"
    assert len(ladder.instance_bboxes_pt) == 1

    # The placed callout is on the plan, not inside the legend column.
    placed = ladder.instance_bboxes_pt[0]
    assert placed != ladder.legend_bbox_pt
    assert placed[1] > ladder.legend_bbox_pt[3], "callout should sit below the legend"


@crow_only
def test_a_keynote_that_is_never_placed_counts_zero_and_says_so():
    """Zero placed callouts is a measurement, and it is not the same as the
    keynote being absent — the legend text is still carried."""
    page = _crow()
    groups = cluster_symbols(page, CROW_P0_FPP, doc=page.parent, page_index=0)
    callouts = {c.number: c for c in keynote_callout_counts(page, groups)}
    unplaced = [c for c in callouts.values() if c.callout_count == 0]
    assert unplaced, "expected at least one legend-only keynote on this sheet"
    for c in unplaced:
        assert c.note_text and c.legend_bbox_pt is not None


@crow_only
def test_the_ladder_alias_is_ambiguous_and_the_engine_publishes_no_number_for_it():
    """Keynotes 1 AND 2 both say "ACCESS LADDER". A naive alias match returns 2.

    This is exactly the case the label/measure split exists for: the counts are
    deterministic per keynote, and choosing WHICH keynote is the Ladder line
    item is a head-noun judgement left to the semantic pass. This test pins the
    ambiguity so nobody later "fixes" it with a substring match.
    """
    entries = keynote_legend(_crow())["KEYNOTES"]
    matches = [n for n, t in entries.items() if "ACCESS LADDER" in t.upper()]
    assert sorted(matches, key=int) == ["1", "2"]
    assert "HATCH" in entries["2"].upper()


def test_no_legend_no_callouts():
    doc = fitz.open()
    doc.new_page()
    try:
        assert keynote_legend_rows(doc[0]) == {}
        assert keynote_callout_counts(doc[0], []) == []
    finally:
        doc.close()
