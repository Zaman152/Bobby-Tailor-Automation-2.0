"""Phase 16 calculator accuracy guards + 23-15 unit-aware formula guards.

23-15 / INV-06: the LF branch of _apply_formula used to IGNORE its unit
argument, so a rail's pipe diameter printed in inches on a detail sheet
became "1.54 lf" — seven such phantom rows in the saved Crow run, reported
as Guardrail 5.8 LF / Handrail 4.7 LF with needs_review=False. The tests
below pin the kill: an inch is never silently reported as a linear foot,
and a detail-sheet spec is never a quantity.
"""
import csv

from bobbytailor.pipeline.calculator import (
    ESTIMATION_TABLES,
    _apply_formula,
    _calculate_from_lintel_runs,
    _calculate_from_measurement,
    _calculate_from_pipe_runs,
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
    assert all(e.get("qty_source") == "plan_schedule_legend" for e in est)


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


# ─── 23-15: unit-aware formula branches + widened detail-sheet guard ─────────

# The seven phantom rows of INV-06 §1.1 — every one a pipe O.D. in inches,
# every one from the A-401 details sheet, reproduced verbatim as fixtures.
_INV06_PHANTOM_MEASUREMENTS = [
    {"value": "1.5", "unit": "in", "description": "Steel pipe guardrail outer diameter",
     "raw_text": '1 1/2" O.D. STEEL PIPE GUARDRAIL'},
    {"value": "1.125", "unit": "in", "description": "Steel pipe guardrail outer diameter",
     "raw_text": '1 1/8" O.D. STEEL PIPE GUARDRAIL'},
    {"value": "1.5", "unit": "in", "description": "Handrail O.D. pipe diameter",
     "raw_text": '1 1/2" O.D. HANDRAIL'},
    {"value": "1.5", "unit": "in", "description": "Guardrail O.D. pipe diameter",
     "raw_text": '1 1/2" O.D. GUARDRAIL'},
    {"value": "1.5", "unit": "in", "description": "Guardrail O.D. pipe diameter",
     "raw_text": '1-1/2" O.D. GUARDRAIL'},
    {"value": "1.5", "unit": "in", "description": "Handrail pipe diameter",
     "raw_text": '1 1/2" O.D. PIPE GUARDRAIL'},
    {"value": "1.5", "unit": "in", "description": "Handrail pipe diameter",
     "raw_text": '1 1/2" O.D. HANDRAIL @ CONC. SLAB'},
]


def test_a_pipe_diameter_in_inches_never_becomes_linear_feet():
    """INV-06 §3 item 1: today _apply_formula('guard_rail', 1.5, 'in', ...)
    returns (1.545, 'lf', '2 lf × 1.03 = 2 lf') — the value with the inch
    unit and the no-formula sentinel is the fix."""
    qty, unit, formula = _apply_formula("guard_rail", 1.5, "in", "1.5")
    assert (qty, unit, formula) == (1.5, "in", "no formula")
    qty, unit, formula = _apply_formula("hand_rail", 1.5, "in", "1.5")
    assert (qty, unit, formula) == (1.5, "in", "no formula")
    # The area branch has the same shape: a linear dimension is not an area.
    qty, unit, formula = _apply_formula("cmu_wall", 8.0, "lf", "8")
    assert (qty, unit, formula) == (8.0, "lf", "no formula")


def test_a_rail_diameter_measurement_produces_no_row():
    """INV-06 §3 item 1 (second half): the same measurement dict through the
    measurement calculator returns nothing — on the detail sheet via the
    widened guard, and on a plan sheet via the unit guard."""
    m = {"value": "1.5", "unit": "in",
         "description": "Steel pipe guardrail outer diameter",
         "raw_text": '1 1/2" O.D. STEEL PIPE GUARDRAIL'}
    assert _calculate_from_measurement(m, "A-401", "detail") is None
    assert _calculate_from_measurement(m, "A-101", "floor_plan") is None


def test_a_detail_sheet_dimension_is_a_spec_not_a_run():
    """The widened detail guard covers rails, striping and trench drains —
    even a length-unit callout on a DETAIL sheet is a specification."""
    for desc, raw in (
        ("Guardrail run", "42 LF GUARDRAIL"),
        ("Handrail run", "42 LF HANDRAIL"),
        ("Parking striping", "42 LF STRIPING"),
        ("Trench drain", "42 LF TRENCH DRAIN"),
    ):
        m = {"value": "42", "unit": "lf", "description": desc, "raw_text": raw}
        assert _calculate_from_measurement(m, "A-401", "detail") is None, desc


def test_a_rail_length_in_linear_feet_still_gets_its_formula():
    """Regression: a guard-rail item with a value in LF keeps its normal
    formula and quantity — the guard is on the unit, not the item type."""
    wf = ESTIMATION_TABLES["guard_rail"]["waste_factor"]
    qty, unit, formula = _apply_formula("guard_rail", 50.0, "lf", "50")
    assert unit == "lf"
    assert formula != "no formula"
    # 31-01: the QUANTITY is the measurement. The waste factor is an ORDER
    # factor and is named in the formula rather than multiplied in — a take-off
    # states what is on the drawing, not what to buy.
    assert abs(qty - 50.0) < 0.01
    assert str(wf) in formula and "not applied" in formula


def test_pipe_run_and_lintel_run_calculators_are_unaffected():
    """Regression: both calculators pass an explicit 'lf' unit, so the new
    guard never fires on their outputs."""
    pipe = _calculate_from_pipe_runs(
        [{"length_lf": 25, "diameter_in": 12, "material": "PVC",
          "raw_text": "25 LF PVC"}], "C-1")
    assert len(pipe) == 1
    wf = ESTIMATION_TABLES["storm_pipe"]["waste_factor"]
    assert pipe[0]["unit"] == "lf"
    assert pipe[0]["formula"] != "no formula"
    # 31-01: measured length published; order factor recorded, not applied.
    assert abs(pipe[0]["quantity"] - 25.0) < 0.01
    assert str(wf) in pipe[0]["formula"]

    lintel = _calculate_from_lintel_runs([{"total_lf": 179.24}], "S-1")
    assert len(lintel) == 1
    wf = ESTIMATION_TABLES["lintel"]["waste_factor"]
    assert lintel[0]["unit"] == "lf"
    assert lintel[0]["formula"] != "no formula"
    # 31-01: 179.24 is what the drawing carries, and it is what Bob's golden
    # asks for. Publishing 188.20 could never have matched it.
    assert abs(lintel[0]["quantity"] - 179.24) < 0.01
    assert str(wf) in lintel[0]["formula"]


def test_no_rail_row_with_an_inch_raw_unit_survives_to_calculations_csv(tmp_path):
    """INV-06 §3 item 2, asserted over the run directory this offline test
    produces: after a re-run of the seven saved phantom measurements through
    the calculator and the reporter's own CSV writer, filtering the
    calculations output for rail rows whose raw unit is inches yields
    NOTHING — on the detail sheet AND on a plan sheet."""
    from bobbytailor.pipeline.reporter import (
        _normalize_calculated, _write_calculated_csv,
    )
    run_dir = tmp_path / "offline_run"
    run_dir.mkdir()
    estimates = []
    for sheet_type in ("detail", "floor_plan"):
        extracted = {
            "_source_sheet": "A-401",
            "sheet_type": sheet_type,
            "measurements": list(_INV06_PHANTOM_MEASUREMENTS),
            "components": [], "rooms": [], "schedules": [], "pipe_runs": [],
        }
        estimates.extend(apply_estimation_tables(extracted))
    out = run_dir / "calculations.csv"
    _write_calculated_csv(_normalize_calculated(estimates), out)
    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    rail_inch_rows = [
        r for r in rows
        if "rail" in (r.get("item_type") or "").lower()
        and (r.get("raw_unit") or "").strip().lower() in ("in", "inches", '"')
    ]
    assert rail_inch_rows == []


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
