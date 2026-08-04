"""tests/test_units.py — what a unit MEASURES (C3b).

Pure data tests: no PDF, no fitz, no API key.

The rule this module encodes is a negative one and the tests are shaped to
match it: a class mismatch withholds a published number, so the module must
fire where the contradiction is CERTAIN and stay silent everywhere else. A
false positive here blanks a good quantity, which is worse than the defect it
prevents.
"""

import pytest

from bobbytailor.pipeline.units import (
    AREA,
    COUNT,
    LINEAR,
    VOLUME,
    basis_class,
    classes_conflict,
    unit_class,
    unit_conflict,
)

pytestmark = pytest.mark.generalization


@pytest.mark.parametrize("unit,expected", [
    ("EA", COUNT), ("ea", COUNT), ("Each", COUNT), ("PR", COUNT),
    ("SET", COUNT), ("openings", COUNT),
    ("SF", AREA), ("sf", AREA), ("sq_ft", AREA), ("SQ. FT.", AREA),
    ("square feet", AREA), ("SY", AREA),
    ("LF", LINEAR), ("lin ft", LINEAR), ("FT", LINEAR), ("feet", LINEAR),
    ("CY", VOLUME), ("cu. yd.", VOLUME), ("CF", VOLUME),
])
def test_unit_class_reads_the_common_spellings(unit, expected):
    assert unit_class(unit) == expected


@pytest.mark.parametrize("unit", ["", None, "ROLLS", "widgets", "???", "  "])
def test_an_unrecognised_unit_has_no_class(unit):
    """None is a first-class answer, never a guess — see the module docstring."""
    assert unit_class(unit) is None


@pytest.mark.parametrize("basis,expected", [
    ("count", COUNT),
    ("linear", LINEAR), ("perimeter", LINEAR),
    ("wall_area", AREA), ("floor_area", AREA), ("roof_area", AREA),
    ("ceiling_area", AREA), ("footprint_area", AREA), ("facade_area", AREA),
])
def test_basis_class_covers_every_basis_a_binder_registers(basis, expected):
    assert basis_class(basis) == expected


@pytest.mark.parametrize("basis", ["", None, "some_new_basis"])
def test_an_unmapped_basis_has_no_class(basis):
    assert basis_class(basis) is None


def test_a_conflict_needs_both_classes_known_and_different():
    assert classes_conflict(COUNT, AREA) is True
    assert classes_conflict(AREA, COUNT) is True
    assert classes_conflict(AREA, AREA) is False
    assert classes_conflict(None, AREA) is False
    assert classes_conflict(AREA, None) is False
    assert classes_conflict(None, None) is False


def test_the_two_crow_violations_are_both_conflicts():
    """The defect in both directions, from the saved paid run.

    `Tilt Up Wall 5.0 SF` — a COUNT of five panels published as an AREA.
    `LED Wall Pack 34,214 EA` — a wall AREA published as a COUNT.
    """
    assert unit_conflict("count", "SF") is True
    assert unit_conflict("wall_area", "EA") is True


def test_the_ordinary_cases_are_not_conflicts():
    assert unit_conflict("wall_area", "SF") is False
    assert unit_conflict("linear", "LF") is False
    assert unit_conflict("count", "EA") is False
    # ...and anything unknown on either side stays silent.
    assert unit_conflict("wall_area", "ROLLS") is False
    assert unit_conflict("some_new_basis", "EA") is False
    assert unit_conflict(None, None) is False
