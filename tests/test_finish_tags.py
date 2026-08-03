"""Layer-1 tests for the plan-body material / finish tag reader.

**Read this before changing a threshold.**  Every real-PDF assertion here is a
SET assertion — *which finish codes appear on which sheet* — checked against the
per-sheet Legend boxes the estimator drew on Moxy's own take-off PDF (INV-05 §2
Key A).  The per-code tag counts are deliberately NOT asserted and are never
compared to a square-foot figure: a tag is a callout instance, not a region, and
tuning a tag count toward an area is the documented coincidence trap (D-07).

The one number that would tempt a tuner — the 7,432.05 SF the five WC legends
sum to — appears nowhere in this file, and no code in ``finish_tags`` can
produce an area at all.
"""
from __future__ import annotations

import os

import fitz
import pytest

from bobbytailor.deterministic.finish_tags import (
    FINISH_PREFIXES,
    MaterialTag,
    code_set,
    extract_material_tags,
    is_finish_number,
    is_finish_prefix,
    normalise_code,
)
from bobbytailor.deterministic.tag_pairing import sheet_mask_rects

UPLOADS = os.path.join(os.path.dirname(__file__), os.pardir, "uploads")
MOXY = os.path.join(UPLOADS, "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf")

# INV-05 §2 Key A: the WC code set the estimator's per-sheet Legend records, per
# interior-elevation sheet (ID-200..ID-205).  Page index 17 is the TRUE NEGATIVE
# — the estimator measured guard rail and hand rail there and no wall covering.
MOXY_WC_SETS = {
    15: {"WC-1", "WC-2"},
    16: {"WC-1", "WC-2", "WC-4", "WC-7"},
    17: set(),
    18: {"WC-6", "WC-7"},
    19: {"WC-9", "WC-10"},
    20: {"WC-8"},
}

# The guestroom prototype sheets. INV-05 §1.3 checked these for material tags
# and got nothing: Guestroom-Wall Covering is an accent wall the drawing never
# designates, which is why it cannot be derived from a tag.
MOXY_GUESTROOM_PAGES = (23, 26, 31)

_needs_moxy = pytest.mark.skipif(not os.path.exists(MOXY), reason="Moxy plans PDF not present")


# ── Vocabulary ───────────────────────────────────────────────────────────────


def test_finish_prefix_registry_is_recognised_case_insensitively():
    for prefix in FINISH_PREFIXES:
        assert is_finish_prefix(prefix)
        assert is_finish_prefix(prefix.lower())
    assert not is_finish_prefix("WALLCOVERING")
    assert not is_finish_prefix("WCX")
    assert not is_finish_prefix("")
    assert not is_finish_prefix("07")


def test_finish_number_is_two_digits_with_an_optional_variant_letter():
    for good in ("01", "07", "10", "11A", "11B"):
        assert is_finish_number(good), good
    for bad in ("1", "007", "A1", "1A", "ABC", "", "7-"):
        assert not is_finish_number(bad), bad


def test_normalise_code_strips_leading_zeros_the_way_the_legend_writes_them():
    assert normalise_code("WC", "07") == "WC-7"
    assert normalise_code("WC", "10") == "WC-10"
    assert normalise_code("wc", "01") == "WC-1"
    assert normalise_code("T", "11A") == "T-11A"
    # An all-zero number keeps a digit rather than becoming an empty code.
    assert normalise_code("PT", "00") == "PT-0"


# ── The real sheets: the SET, on six of six ─────────────────────────────────


@_needs_moxy
@pytest.mark.parametrize("page_index", sorted(MOXY_WC_SETS))
def test_moxy_elevation_sheet_wall_covering_set_is_exact(page_index):
    """The estimator's own Legend box, reproduced from the drawing's text layer.

    Masks: the viewport (title-block / legend) masks are computed per page.  The
    schedule mask is empty on these sheets by construction — Moxy's only
    schedule table is the door schedule on page index 6 — so passing no schedule
    bbox here is the same input the production path builds, without the
    whole-document ``find_tables`` scan.
    """
    doc = fitz.open(MOXY)
    try:
        page = doc[page_index]
        tags = extract_material_tags(page, sheet_mask_rects(page), page_index)
    finally:
        doc.close()
    assert code_set(tags, "WC") == MOXY_WC_SETS[page_index]


@_needs_moxy
def test_the_true_negative_sheet_is_a_negative_and_not_a_failure():
    """Page 17 must yield NO wall covering AND still yield other finish codes.

    Without the second half this test would pass just as happily if the reader
    silently returned nothing at all on that sheet.
    """
    doc = fitz.open(MOXY)
    try:
        page = doc[17]
        tags = extract_material_tags(page, sheet_mask_rects(page), 17)
    finally:
        doc.close()
    assert code_set(tags, "WC") == set()
    assert code_set(tags) == {"PT-4", "PT-5", "ST-1", "WD-7"}


@_needs_moxy
def test_page_18_is_non_empty_the_rotation_regression():
    """The bug a naive implementation ships, pinned.

    Pages 15-17 draw their tags rotated (``dir=(0,-1)``); pages 18-20 draw them
    unrotated (``dir=(1,0)``).  A vertically-stacked-only reader finds page 15
    and returns NOTHING here — INV-05 §2 Key A recorded exactly that first pass.
    The assertion checks both the result and the rotation that makes it a
    regression test rather than a coincidence.
    """
    doc = fitz.open(MOXY)
    try:
        rotated = extract_material_tags(doc[15], sheet_mask_rects(doc[15]), 15)
        unrotated = extract_material_tags(doc[18], sheet_mask_rects(doc[18]), 18)
    finally:
        doc.close()
    assert code_set(unrotated, "WC"), "the unrotated layout was lost"
    assert {t.text_dir for t in rotated} == {(0, -1)}
    assert {t.text_dir for t in unrotated} == {(1, 0)}
    # Same reader, both orientations, in one test run.
    assert code_set(rotated, "WC") == {"WC-1", "WC-2"}
    assert code_set(unrotated, "WC") == {"WC-6", "WC-7"}


@_needs_moxy
@pytest.mark.parametrize("page_index", MOXY_GUESTROOM_PAGES)
def test_the_guestroom_prototype_sheets_carry_no_material_tags(page_index):
    doc = fitz.open(MOXY)
    try:
        page = doc[page_index]
        tags = extract_material_tags(page, sheet_mask_rects(page), page_index)
    finally:
        doc.close()
    assert tags == []


@_needs_moxy
def test_every_returned_tag_carries_its_page_and_position():
    """A tag's whole downstream value is that a human can be sent to it."""
    doc = fitz.open(MOXY)
    try:
        tags = extract_material_tags(doc[20], sheet_mask_rects(doc[20]), 20)
    finally:
        doc.close()
    assert tags
    for tag in tags:
        assert isinstance(tag, MaterialTag)
        assert tag.page_index == 20
        x0, y0, x1, y1 = tag.bbox_pt
        assert x1 > x0 and y1 > y0
        assert tag.code.startswith(tag.prefix + "-")
        assert tag.to_dict()["code"] == tag.code


# ── Masking: mandatory, not optional ────────────────────────────────────────


def _synthetic_tag_page(x: float = 200.0, y: float = 300.0) -> fitz.Document:
    """A page whose text layer holds one ``WC`` + ``07`` tag at (x, y).

    A synthetic page is built as a text DICT rather than by writing into a PDF,
    because ``insert_text`` puts two same-baseline tokens in one text line —
    ``'WC 07'`` — which is not the shape a CAD set produces.  A real drawing
    emits each token as its own line; that is the input this reader is written
    against and the input the real-PDF assertions above exercise.  The geometry
    below is the MEASURED Moxy page-18 tag from INV-05 §2 Key A, translated to
    (x, y), so the synthetic case is the real case with the position freed.
    """
    dx, dy = x - 908.4, y - 217.4
    return _StubPage(
        [
            ("WC", (908.4 + dx, 217.4 + dy, 923.7 + dx, 228.8 + dy), (1.0, 0.0)),
            ("07", (934.2 + dx, 217.4 + dy, 943.6 + dx, 228.8 + dy), (1.0, 0.0)),
        ]
    )


class _StubPage:
    """Minimal page exposing only the ``get_text('dict')`` the reader uses."""

    def __init__(self, records):
        self.number = 0
        self._records = list(records)

    def get_text(self, kind):  # noqa: D102 - mirrors the PyMuPDF signature
        assert kind == "dict"
        return {
            "blocks": [
                {
                    "lines": [
                        {"bbox": bbox, "dir": text_dir, "spans": [{"text": text}]}
                        for text, bbox, text_dir in self._records
                    ]
                }
            ]
        }


def test_a_tag_inside_a_mask_rectangle_is_not_a_plan_body_callout():
    page = _synthetic_tag_page(x=200.0, y=300.0)
    unmasked = extract_material_tags(page, (), 0)
    assert [t.code for t in unmasked] == ["WC-7"]
    assert unmasked[0].bbox_pt == pytest.approx((200.0, 300.0, 235.2, 311.4))
    # The mask the door-schedule / legend guard supplies on a real sheet.
    assert extract_material_tags(page, [(150.0, 250.0, 400.0, 350.0)], 0) == []
    # A mask elsewhere on the sheet leaves the tag alone.
    assert [t.code for t in extract_material_tags(page, [(0.0, 0.0, 50.0, 50.0)], 0)] == [
        "WC-7"
    ]


def test_a_mask_that_merely_clips_a_tag_does_not_delete_it():
    """Containment, not intersection — a mask edge must not eat a plan callout."""
    page = _synthetic_tag_page(x=200.0, y=300.0)
    clipping = (150.0, 250.0, 220.0, 350.0)  # covers the 'WC' token only
    assert [t.code for t in extract_material_tags(page, [clipping], 0)] == ["WC-7"]


def test_a_stray_number_beyond_the_gap_does_not_manufacture_a_code():
    """T-23-17: the adjacency window is the whole defence against invention."""
    page = _StubPage(
        [
            ("WC", (200.0, 300.0, 215.3, 311.4), (1.0, 0.0)),
            ("07", (275.0, 300.0, 284.4, 311.4), (1.0, 0.0)),  # ~60 pt away
        ]
    )
    assert extract_material_tags(page, (), 0) == []


def test_a_number_on_the_line_below_does_not_pair_with_the_prefix():
    page = _StubPage(
        [
            ("WC", (200.0, 300.0, 215.3, 311.4), (1.0, 0.0)),
            ("07", (225.8, 320.0, 235.2, 331.4), (1.0, 0.0)),
        ]
    )
    assert extract_material_tags(page, (), 0) == []


def test_extraction_survives_a_page_whose_text_layer_raises():
    class _Hostile:
        number = 0

        def get_text(self, _kind):
            raise RuntimeError("corrupt content stream")

    assert extract_material_tags(_Hostile(), (), 0) == []
