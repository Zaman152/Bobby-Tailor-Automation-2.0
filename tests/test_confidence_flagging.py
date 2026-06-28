"""Phase 3: per-item confidence / needs_review propagation end-to-end."""
import csv
from pathlib import Path

from calculator import _calculate_from_component, _calculate_from_measurement, _calculate_from_room
from reporter import _normalize_calculated, _write_takeoff_summary_csv, _write_calculated_csv
from aggregator import aggregate_takeoff


def _summary_from(estimates):
    return aggregate_takeoff(_normalize_calculated(estimates))


def test_low_confidence_count_flags_needs_review():
    e = _calculate_from_component(
        {"name": "Bollard", "quantity": 3, "unit": "ea", "confidence": "low"},
        "A1", "floor_plan",
    )
    assert e["needs_review"] is True
    assert e["confidence"] == "low"
    summary = _summary_from([e])
    row = next(r for r in summary if r["item"] == "Bollards")
    assert row["needs_review"] is True


def test_unclassified_component_flags_needs_review():
    e = _calculate_from_component(
        {"name": "Mysterious Widget XJ", "quantity": 2, "unit": "ea"},
        "A1", "floor_plan",
    )
    assert e["needs_review"] is True
    assert "unclassified" in e["review_reason"]


def test_high_confidence_count_not_flagged():
    e = _calculate_from_component(
        {"name": "Bollard", "quantity": 3, "unit": "ea", "confidence": "high"},
        "A1", "floor_plan",
    )
    assert e["needs_review"] is False
    assert e["confidence"] == "high"


def test_approximate_measurement_flags_needs_review():
    e = _calculate_from_measurement(
        {"value": "120", "unit": "lf", "description": "guard rail", "approximate": True},
        "C1", "civil_site",
    )
    assert e is not None
    assert e["needs_review"] is True
    assert "approximate" in e["review_reason"].lower()


def test_estimated_wall_area_flags_needs_review():
    rows = _calculate_from_room(
        {"name": "Office 101", "area": "400", "notes": "paint walls"},
        "A2", "office",
    )
    wall_rows = [r for r in rows if "wall" in (r.get("source_raw") or "").lower() or "≈" in (r.get("source_raw") or "")]
    assert wall_rows, rows
    assert all(r["needs_review"] for r in wall_rows)


def test_summary_csv_includes_confidence_columns(tmp_path):
    summary = _summary_from([
        _calculate_from_component(
            {"name": "Bollard", "quantity": 3, "unit": "ea", "confidence": "low"},
            "A1", "floor_plan"),
    ])
    out = tmp_path / "takeoff_summary.csv"
    _write_takeoff_summary_csv(summary, out)
    with open(out, newline="") as f:
        reader = csv.DictReader(f)
        assert "confidence" in reader.fieldnames
        assert "needs_review" in reader.fieldnames
        assert "review_notes" in reader.fieldnames
        rows = list(reader)
    bollard = next(r for r in rows if r["item"] == "Bollards")
    assert bollard["needs_review"] == "yes"


def test_calculations_csv_includes_confidence_columns(tmp_path):
    items = _normalize_calculated([
        _calculate_from_component(
            {"name": "Bollard", "quantity": 3, "unit": "ea", "confidence": "low"},
            "A1", "floor_plan"),
    ])
    out = tmp_path / "calculations.csv"
    _write_calculated_csv(items, out)
    with open(out, newline="") as f:
        reader = csv.DictReader(f)
        assert "confidence" in reader.fieldnames
        assert "needs_review" in reader.fieldnames
        assert "review_reason" in reader.fieldnames
