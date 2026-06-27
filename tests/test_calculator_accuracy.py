"""Phase 16 calculator accuracy guards."""
from calculator import (
    _calculate_from_schedule,
    _parse_numeric,
    _schedule_is_takeoff,
    resolve_spec_lookups,
    apply_estimation_tables,
)


def test_schedule_guard_spec_reference():
    sched = {
        "name": "Plastic Flared End Section",
        "table_purpose": "specification_reference",
        "rows": [{"PIPE SIZE": "12 in", "PART#": "1210NP"}],
    }
    assert _calculate_from_schedule(sched, "C-1") == []


def test_schedule_guard_use_for_takeoff_false():
    sched = {"name": "Notes", "table_purpose": "takeoff_schedule", "use_for_takeoff": False, "rows": []}
    assert not _schedule_is_takeoff(sched)


def test_takeoff_legend_sf_and_ea_rows():
    """Quantity takeoff legend rows with UNIT column map to correct item types and units."""
    sched = {
        "name": "Quantity Takeoff Legend",
        "table_purpose": "takeoff_legend",
        "use_for_takeoff": True,
        "rows": [
            {"ITEM": "Bollards", "QTY": "28", "UNIT": "EA"},
            {"ITEM": "Sealed Concrete", "QTY": "395673.42", "UNIT": "SF"},
            {"ITEM": "CMU Wall", "QTY": "2204.33", "UNIT": "SF"},
            {"ITEM": "Columns-H-35'", "QTY": "132", "UNIT": "EA"},
            {"ITEM": "Mobilization", "QTY": "1", "UNIT": "EA"},
        ],
    }
    est = _calculate_from_schedule(sched, "A-101")
    by_type = {e["item_type"]: e for e in est}
    assert by_type["bollard"]["quantity"] == 28
    # Authoritative legend preserves the printed unit token verbatim (EA, SF...).
    assert by_type["bollard"]["unit"] == "EA"
    assert abs(by_type["sealed_concrete"]["quantity"] - 395673.42) < 1
    assert by_type["sealed_concrete"]["unit"] == "SF"
    assert abs(by_type["cmu_wall"]["quantity"] - 2204.33) < 1
    assert by_type["columns"]["quantity"] == 132
    # Authoritative legend rows are tagged so aggregation can dedupe vision items.
    assert all(e.get("qty_source") == "companion_takeoff_legend" for e in est)


def test_takeoff_legend_does_not_apply_waste():
    """A companion legend is final — waste factors must NOT inflate its values."""
    sched = {
        "name": "Quantity Takeoff (companion document)",
        "table_purpose": "takeoff_legend",
        "use_for_takeoff": True,
        "rows": [
            {"ITEM": "Exterior Painting-EIFS", "QTY": "3053.04", "UNIT": "SF"},
            {"ITEM": "Gas Piping", "QTY": "886.77", "UNIT": "LF"},
            {"ITEM": "Lintels", "QTY": "179.24", "UNIT": "LF"},
        ],
    }
    est = _calculate_from_schedule(sched, "A-101")
    by_desc = {e["description"]: e for e in est}
    # eifs/gas_pipe/lintel all carry a 1.05 waste factor in ESTIMATION_TABLES;
    # the legend value must pass through verbatim (no ×1.05).
    assert abs(by_desc["Exterior Painting-EIFS"]["quantity"] - 3053.04) < 0.01
    assert abs(by_desc["Gas Piping"]["quantity"] - 886.77) < 0.01
    assert abs(by_desc["Lintels"]["quantity"] - 179.24) < 0.01
    assert all(e["waste_factor_applied"] == 1.0 for e in est)


def test_schedule_suppresses_flooring_when_legend_present():
    extracted = {
        "_source_sheet": "A-101",
        "sheet_type": "floor_plan",
        "rooms": [{"name": "Warehouse", "area": "400000", "notes": ""}],
        "schedules": [{
            "name": "Takeoff Legend",
            "table_purpose": "takeoff_legend",
            "use_for_takeoff": True,
            "rows": [{"ITEM": "Sealed Concrete", "QTY": "395673", "UNIT": "SF"}],
        }],
        "measurements": [],
        "components": [],
        "pipe_runs": [],
    }
    est = apply_estimation_tables(extracted, project_type="industrial")
    types = [e["item_type"] for e in est]
    assert "flooring" not in types
    assert "sealed_concrete" in types


def test_parse_numeric_rejects_gl():
    assert _parse_numeric("GL=845.0") is None
    assert _parse_numeric("INV. IN=843.3") is None


def test_parse_numeric_rejects_slope_percent():
    assert _parse_numeric("4.81%") is None


def test_storm_pipe_from_pipe_runs():
    extracted = {
        "_source_sheet": "C-1",
        "pipe_runs": [{"length_lf": 25, "diameter_in": 12, "material": "PVC", "raw_text": "25 LF PVC"}],
        "measurements": [],
        "components": [],
        "rooms": [],
        "schedules": [],
    }
    est = apply_estimation_tables(extracted)
    assert any(e.get("item_type") == "storm_pipe" for e in est)


def test_resolve_spec_lookups_enriches():
    all_ext = [{
        "_source_sheet": "S1",
        "schedules": [{
            "name": "Pipe Catalog",
            "table_purpose": "specification_reference",
            "lookup_key": "PIPE SIZE",
            "rows": [{"PIPE SIZE": "12 in", "PART#": "1210NP"}],
        }],
    }]
    estimates = [{"description": '12" storm pipe run', "item_type": "storm_pipe"}]
    out = resolve_spec_lookups(all_ext, estimates)
    assert out[0].get("spec_reference", {}).get("matched_size") == "12 in"
