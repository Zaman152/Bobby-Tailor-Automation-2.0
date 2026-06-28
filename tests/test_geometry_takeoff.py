"""Tests for the vector-geometry measurement engine (scale + length/area math)."""
import types

from geometry_takeoff import resolve_scale, measure_geometry, POINTS_PER_INCH


class _P:
    def __init__(self, x, y):
        self.x, self.y = x, y


class _R:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.width, self.height = x1 - x0, y1 - y0


class FakePage:
    """Minimal stand-in for a fitz Page for deterministic geometry tests."""
    def __init__(self, items, text="", words=None):
        self._items = items
        self._text = text
        self._words = words or []

    def get_drawings(self):
        return [{"items": self._items}]

    def get_text(self, kind="text"):
        return self._words if kind == "words" else self._text


def _line(x0, y0, x1, y1):
    return ("l", _P(x0, y0), _P(x1, y1))


def test_override_scale_is_high_confidence():
    pg = FakePage([_line(0, 0, 72, 0)])
    sc = resolve_scale(pg, override_feet_per_inch=20)
    assert sc.confidence == "high"
    assert sc.method == "override"
    # 20 ft per inch -> 20/72 ft per point
    assert sc.feet_per_point == 20 / POINTS_PER_INCH


def test_printed_scale_detection():
    pg = FakePage([_line(0, 0, 10, 0)], text='SCALE: 1" = 20\'-0"')
    sc = resolve_scale(pg)
    assert sc.method == "printed_scale"
    assert round(sc.feet_per_point * POINTS_PER_INCH) == 20


def test_length_measurement_is_exact_given_scale():
    # One 72pt horizontal line = 1 inch = 20 ft at 1"=20'.
    pg = FakePage([_line(0, 0, 72, 0)])
    m = measure_geometry(pg, override_feet_per_inch=20)
    assert m.total_linework_lf == 20.0
    # Auto-accept: an explicit (high-confidence) scale needs no manual review.
    assert m.confidence == "high"
    assert m.needs_review is False


def test_area_measurement_rectangle():
    # A 72pt x 72pt square = 1in x 1in = 20ft x 20ft = 400 SF at 1"=20'.
    items = [
        _line(0, 0, 72, 0), _line(72, 0, 72, 72),
        _line(72, 72, 0, 72), _line(0, 72, 0, 0),
    ]
    pg = FakePage(items)
    m = measure_geometry(pg, override_feet_per_inch=20, trim_pct=0)
    assert m.footprint_sf == 400.0


def test_no_scale_returns_none_measurement():
    pg = FakePage([_line(0, 0, 10, 0)], text="FLOOR PLAN")
    m = measure_geometry(pg)
    assert m.footprint_sf is None
    assert m.confidence == "none"


def test_dimension_calibration_fallback():
    # Two dimension words "20'" centered over two 72pt lines -> 20/72 ft/pt.
    items = [_line(0, 0, 72, 0), _line(0, 100, 72, 100), _line(0, 200, 72, 200)]
    words = [
        (0, -10, 72, -5, "20'"), (0, 90, 72, 95, "20'"), (0, 190, 72, 195, "20'"),
    ]
    pg = FakePage(items, text="no scale here", words=words)
    sc = resolve_scale(pg)
    assert sc.method == "dimension_calibration"
    assert round(sc.feet_per_point * POINTS_PER_INCH) == 20
    assert sc.confidence == "low"
