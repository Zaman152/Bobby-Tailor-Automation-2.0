"""Regression tests for robust printed-scale extraction.

Covers the class of bug where stacked architectural fractions collapse during
PDF text extraction (1/8" -> "18", 3/32" -> "32") and produce scales that are
~24-340x too small. These tests lock in exact recovery + ladder snapping.
"""
import os

import pytest

from scale_extraction import (
    snap_fpi,
    extract_scales_from_text,
    extract_scales_from_page,
    dominant_scale,
)

UPLOADS = os.path.join(os.path.dirname(__file__), os.pardir, "uploads")
BOBS = os.path.join(UPLOADS, "Bob's Discount Furniture - Kennesaw, GA-plans.pdf")
MOXY = os.path.join(UPLOADS, "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf")


# ── Ladder snapping: real scales snap, mangled values are rejected ────────────

@pytest.mark.parametrize("fpi,expected", [
    (8.0, 8.0),            # 1/8" = 1'-0"
    (4.0, 4.0),            # 1/4" = 1'-0"
    (2.0, 2.0),            # 1/2" = 1'-0"
    (5.333333, 5.333333),  # 3/16" = 1'-0"
    (10.666667, 10.666667),# 3/32" = 1'-0"
    (20.0, 20.0),          # 1" = 20'
    (10.5, 10.666667),     # close to 3/32 -> snaps
])
def test_snap_recovers_real_scales(fpi, expected):
    assert snap_fpi(fpi) == pytest.approx(expected, rel=1e-4)


@pytest.mark.parametrize("bad", [
    1 / 18,   # "18" read literally (1/8 mangled)
    1 / 12,   # "12" read literally (1/2 mangled)
    1 / 32,   # "32" read literally (3/32 mangled)
    1 / 316,  # "316" read literally (3/16 mangled)
    0.0,
    -5.0,
    7.0,      # not a standard scale, outside tolerance of 8.0
])
def test_snap_rejects_mangled_or_invalid(bad):
    assert snap_fpi(bad) is None


# ── Text fallback recovers collapsed fractions ───────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ('SCALE: 1/8" = 1\'-0"', 8.0),     # clean fraction
    ('SCALE: 18" = 1\'-0"', 8.0),      # collapsed 1/8
    ('SCALE: 14" = 1\'-0"', 4.0),      # collapsed 1/4
    ('SCALE: 12" = 1\'-0"', 2.0),      # collapsed 1/2
    ('SCALE: 316" = 1\'-0"', 5.333333),# collapsed 3/16
    ('SCALE: 32" = 1\'-0"', 10.666667),# collapsed 3/32 (numerator also dropped)
    ('1" = 20\'', 20.0),               # engineering
    ('1/4" = 1\'-0"', 4.0),
])
def test_text_extractor_recovers_scale(text, expected):
    scales = extract_scales_from_text(text)
    assert scales, f"no scale recovered from {text!r}"
    assert scales[0][0] == pytest.approx(expected, rel=1e-4)


def test_text_extractor_ignores_garbage():
    assert extract_scales_from_text("FLOOR PLAN — GENERAL NOTES") == []
    assert extract_scales_from_text("") == []


# ── PDF regression fixture: known per-sheet scales (skips if PDFs absent) ─────

# Recovered + ladder-snapped feet-per-inch we expect for specific sheets. Only
# stable, high-confidence sheets are asserted to avoid brittleness.
BOBS_EXPECTED = {
    4: 1.0,         # p4 enlarged plans 1" = 1'-0"
    5: 8.0,         # p5 1/8" = 1'-0"
    6: 2.666667,    # p6 3/8" = 1'-0"
}
MOXY_EXPECTED = {
    8: 10.666667,   # 3/32" = 1'-0"
    10: 5.333333,   # 3/16" = 1'-0"
    16: 4.0,        # 1/4" = 1'-0"
    17: 4.0,
    18: 4.0,
}


@pytest.mark.skipif(not os.path.exists(BOBS), reason="Bob's plans PDF not present")
def test_bobs_per_sheet_scales():
    import fitz
    doc = fitz.open(BOBS)
    try:
        for page_no, expected in BOBS_EXPECTED.items():
            fpi, conf, _ = dominant_scale(doc[page_no - 1])
            assert fpi == pytest.approx(expected, rel=1e-3), (
                f"Bob's p{page_no}: got {fpi}, expected {expected}"
            )
    finally:
        doc.close()


@pytest.mark.skipif(not os.path.exists(MOXY), reason="Moxy plans PDF not present")
def test_moxy_per_sheet_scales():
    import fitz
    doc = fitz.open(MOXY)
    try:
        for page_no, expected in MOXY_EXPECTED.items():
            fpi, conf, _ = dominant_scale(doc[page_no - 1])
            assert fpi == pytest.approx(expected, rel=1e-3), (
                f"Moxy p{page_no}: got {fpi}, expected {expected}"
            )
    finally:
        doc.close()


@pytest.mark.skipif(not os.path.exists(MOXY), reason="Moxy plans PDF not present")
def test_extracted_scales_are_all_on_ladder():
    """Every recovered page scale must be a valid ladder value (never mangled)."""
    import fitz
    from scale_extraction import feet_per_inch_ladder
    ladder = set(round(v, 4) for v in feet_per_inch_ladder())
    doc = fitz.open(MOXY)
    try:
        for i in range(doc.page_count):
            for fpi, _count in extract_scales_from_page(doc[i]):
                assert round(fpi, 4) in ladder, f"off-ladder scale {fpi} on p{i+1}"
    finally:
        doc.close()
