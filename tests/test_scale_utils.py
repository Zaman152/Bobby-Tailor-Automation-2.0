"""Tests for drawing scale extraction (Phase 4a)."""
import pytest

from scale_utils import parse_scale, ScaleInfo


def test_architectural_quarter_inch():
    s = parse_scale('SCALE: 1/4" = 1\'-0"')
    assert s is not None
    assert s.system == "architectural"
    # 1/4" paper = 1 ft real -> 4 ft per inch
    assert s.feet_per_inch == pytest.approx(4.0)


def test_architectural_three_sixteenths():
    s = parse_scale('3/16" = 1\'-0"')
    assert s.feet_per_inch == pytest.approx(1 / (3 / 16))  # 5.333..


def test_architectural_mixed_number():
    s = parse_scale('1 1/2" = 1\'-0"')
    assert s.feet_per_inch == pytest.approx(1 / 1.5)


def test_engineering_scale():
    s = parse_scale('1" = 20\'')
    assert s is not None
    assert s.system == "engineering"
    assert s.feet_per_inch == pytest.approx(20.0)


def test_ratio_scale():
    s = parse_scale("SCALE 1:100")
    assert s is not None
    assert s.system == "ratio"
    assert s.ratio == 100.0


def test_nts():
    s = parse_scale("Details — NTS")
    assert s is not None
    assert s.system == "unknown"
    assert s.feet_per_inch is None


def test_no_scale_returns_none():
    assert parse_scale("FLOOR PLAN LEVEL 1") is None
    assert parse_scale("") is None
    assert parse_scale(None) is None


def test_feet_per_pixel():
    s = parse_scale('1" = 20\'')
    # at 200 px/inch render, one pixel = 20/200 = 0.1 ft
    assert s.feet_per_pixel(200) == pytest.approx(0.1)
    assert ScaleInfo("x", None, None, "unknown").feet_per_pixel(200) is None


def test_to_dict():
    s = parse_scale('1/8" = 1\'-0"')
    d = s.to_dict()
    assert set(d) == {"raw", "feet_per_inch", "ratio", "system"}
