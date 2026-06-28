"""Tests for the deterministic scale recompute engine."""
import scale_recalc as sr


def _raw():
    # 720pt × 360pt extent; 1000pt total linework; 600pt long runs.
    return {
        "footprint_pt2": 720 * 360,
        "total_linework_pt": 1000.0,
        "long_run_pt": 600.0,
        "width_pt": 720.0,
        "height_pt": 360.0,
    }


def test_recompute_at_quarter_inch_scale():
    # 1/4" = 1'-0"  ->  48 feet per inch  ->  48/72 ft/pt.
    fpp = 48 / 72
    out = sr.recompute(_raw(), 48)
    assert out["width_ft"] == round(720 * fpp, 1)
    assert out["height_ft"] == round(360 * fpp, 1)
    assert out["footprint_sf"] == round((720 * 360) * fpp * fpp, 1)
    assert out["total_linework_lf"] == round(1000 * fpp, 1)
    assert out["long_run_lf"] == round(600 * fpp, 1)


def test_doubling_scale_quadruples_area_doubles_length():
    a = sr.recompute(_raw(), 24)
    b = sr.recompute(_raw(), 48)
    assert round(b["footprint_sf"] / a["footprint_sf"], 2) == 4.0
    assert round(b["total_linework_lf"] / a["total_linework_lf"], 2) == 2.0


def test_invalid_scale_returns_none():
    for bad in (0, -5, None):
        out = sr.recompute(_raw(), bad)
        assert out["footprint_sf"] is None
        assert out["total_linework_lf"] is None


def test_apply_overrides_updates_only_matched_sheet():
    calib = {"sheets": [
        {"sheet": "A-101", "feet_per_inch": 48, "scale_source": "detected",
         "scale_confidence": "low", "raw": _raw(), "measured": sr.recompute(_raw(), 48)},
        {"sheet": "A-102", "feet_per_inch": 96, "scale_source": "detected",
         "scale_confidence": "low", "raw": _raw(), "measured": sr.recompute(_raw(), 96)},
    ]}
    out = sr.apply_overrides(calib, {"A-101": 24})
    s1 = next(s for s in out["sheets"] if s["sheet"] == "A-101")
    s2 = next(s for s in out["sheets"] if s["sheet"] == "A-102")
    assert s1["feet_per_inch"] == 24
    assert s1["scale_source"] == "user_verified"
    assert s1["scale_confidence"] == "high"
    assert s1["measured"]["footprint_sf"] == sr.recompute(_raw(), 24)["footprint_sf"]
    # untouched sheet stays as-is
    assert s2["feet_per_inch"] == 96
    assert s2["scale_source"] == "detected"


def test_apply_overrides_ignores_invalid_values():
    calib = {"sheets": [{"sheet": "A", "feet_per_inch": 48, "raw": _raw(),
                         "scale_source": "detected"}]}
    out = sr.apply_overrides(calib, {"A": -1})
    assert out["sheets"][0]["feet_per_inch"] == 48
    assert out["sheets"][0]["scale_source"] == "detected"
