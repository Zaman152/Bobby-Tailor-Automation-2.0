"""Exactness tests for the real-world takeoff measurement engine."""
import math

import takeoff_measurements as tm


def test_polyline_length():
    # 3-4-5 right angle + back: 3 + 4 = 7
    pts = [(0, 0), (3, 0), (3, 4)]
    assert tm.polyline_length_pt(pts) == 7.0


def test_polygon_area_square():
    # 10×10 square = 100 pt²
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert tm.polygon_area_pt2(sq) == 100.0
    # winding direction shouldn't matter
    assert tm.polygon_area_pt2(list(reversed(sq))) == 100.0


def test_polygon_perimeter_autoclose():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert tm.polygon_perimeter_pt(sq) == 40.0


def test_area_scales_with_square_of_scale():
    # 100 pt² square. At 48 ft/in → fpp = 48/72 ft/pt.
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    m = tm.new_measurement("Slab", "SF", "area", "A1", sq, feet_per_inch=48)
    fpp = 48 / 72
    assert m["quantity"] == round(100 * fpp * fpp, 2)
    # doubling feet_per_inch quadruples area
    m2 = tm.recompute_measurement({**m, "feet_per_inch": 96})
    assert round(m2["quantity"] / m["quantity"], 2) == 4.0


def test_length_scales_linearly():
    line = [(0, 0), (100, 0)]
    m = tm.new_measurement("Gas Piping", "LF", "length", "P1", line, feet_per_inch=48)
    assert m["quantity"] == round(100 * 48 / 72, 2)


def test_wall_area_is_run_times_height():
    run = [(0, 0), (100, 0)]  # 100 pt run
    m = tm.new_measurement("CMU Wall", "SF", "wall_area", "A2", run,
                           feet_per_inch=48, height_ft=20)
    run_ft = 100 * 48 / 72
    assert m["quantity"] == round(run_ft * 20, 2)


def test_count_is_scale_independent():
    m = tm.new_measurement("Bollards", "EA", "count",
                           "A1", [(1, 1), (2, 2), (3, 3)])
    assert m["quantity"] == 3.0
    # explicit count wins over vertex count
    m2 = tm.new_measurement("Doors", "EA", "count", "A1", [], count=7)
    assert m2["quantity"] == 7.0


def test_two_point_calibration_roundtrip():
    # Two points 96 pt apart that should represent 64 real feet.
    # feet_per_point = 64/96 → feet_per_inch = (64/96)*72 = 48.
    fpi = tm.calibrate_two_point((0, 0), (96, 0), 64)
    assert fpi == 48.0
    # Using that scale, a 96pt line measures back to 64 ft.
    line = [(0, 0), (96, 0)]
    m = tm.new_measurement("X", "LF", "length", "S", line, feet_per_inch=fpi)
    assert m["quantity"] == 64.0


def test_calibration_rejects_degenerate():
    assert tm.calibrate_two_point((5, 5), (5, 5), 10) is None
    assert tm.calibrate_two_point((0, 0), (10, 0), 0) is None


def test_missing_scale_returns_none_for_measured():
    line = [(0, 0), (100, 0)]
    m = tm.new_measurement("Gas Piping", "LF", "length", "P1", line, feet_per_inch=None)
    assert m["quantity"] is None


def test_aggregate_sums_per_item_skips_unverified_and_none():
    measurements = [
        tm.new_measurement("CMU Wall", "SF", "wall_area", "A2", [(0, 0), (100, 0)],
                           feet_per_inch=48, height_ft=20),
        tm.new_measurement("CMU Wall", "SF", "wall_area", "A3", [(0, 0), (50, 0)],
                           feet_per_inch=48, height_ft=20),
        tm.new_measurement("Bollards", "EA", "count", "A1", [(1, 1), (2, 2)]),
        tm.new_measurement("Ignored", "LF", "length", "A1", [(0, 0), (10, 0)],
                           feet_per_inch=48, verified=False),
        tm.new_measurement("NoScale", "LF", "length", "A1", [(0, 0), (10, 0)],
                           feet_per_inch=None),
    ]
    agg = tm.aggregate_measurements(measurements)
    cmu = agg["cmu wall"]
    run_ft = (100 + 50) * 48 / 72
    assert cmu["quantity"] == round(run_ft * 20, 2)
    assert cmu["line_count"] == 2
    assert agg["bollards"]["quantity"] == 2.0
    assert "ignored" not in agg
    assert "noscale" not in agg


def test_bobs_cmu_wall_reaches_golden_with_right_geometry():
    # Demonstrate the engine is exact: choose a run length + height whose product
    # equals Bob's golden CMU wall paint area (16,218.94 SF) at a known scale.
    # At 96 ft/in, fpp = 96/72 = 4/3 ft/pt. Pick height 24 ft.
    # required run_ft = 16218.94 / 24 = 675.789...; run_pt = run_ft / fpp.
    fpi = 96
    fpp = fpi / 72
    height = 24
    run_ft = 16218.94 / height
    run_pt = run_ft / fpp
    m = tm.new_measurement("Exterior Painting - CMU Wall", "SF", "wall_area",
                           "A2", [(0, 0), (run_pt, 0)], feet_per_inch=fpi,
                           height_ft=height)
    assert abs(m["quantity"] - 16218.94) < 0.5
