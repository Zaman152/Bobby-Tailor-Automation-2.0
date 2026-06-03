"""
Generalization test suite — synthetic extraction JSON per sheet_type.

Tests calculator + aggregator for all plan categories WITHOUT PDFs or API keys.
Each fixture is a synthetic Claude extraction output that the production code
consumes via apply_estimation_tables() + aggregate_takeoff().

Run in CI: pytest tests/test_takeoff_generalization.py -q
Run with verbose: pytest tests/test_takeoff_generalization.py -v -m generalization

xfail notes:
  - Industrial room NOT producing Flooring requires 20-03 content-first mapping.
  - Gas pipe producing "Gas Piping" item requires RC-4 fix (MEASURE_ADDENDUM).
  - Door HM/WD separation requires ITEM_NAME_MAP expansion in 20-03.
"""
import json
import pytest
from pathlib import Path
from typing import List, Dict

from calculator import apply_estimation_tables
from aggregator import aggregate_takeoff

FIXTURES = Path(__file__).parent / "fixtures" / "generalization"
EXPECTED = FIXTURES / "expected"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _load_expected(name: str) -> dict:
    path = EXPECTED / name
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _item_types(items: List[Dict]) -> set:
    """Return the set of item_type values from apply_estimation_tables output."""
    return {it.get("item_type") for it in items if it.get("item_type")}


def _aggregated_item_names(items: List[Dict]) -> set:
    """Return canonical item names from aggregate_takeoff output."""
    return {row["item"] for row in aggregate_takeoff(items)}


def _aggregated_qty(items: List[Dict], item_name: str) -> float:
    """Return quantity for a named item in the aggregated summary (0 if absent)."""
    for row in aggregate_takeoff(items):
        if row["item"].lower() == item_name.lower():
            return float(row["quantity"])
    return 0.0


# ─── 1. Floor plan — retail ───────────────────────────────────────────────────

@pytest.mark.generalization
def test_floor_plan_retail_produces_flooring():
    """Retail floor with VCT rooms → Flooring is in the takeoff output."""
    raw = apply_estimation_tables(_load_fixture("floor_plan_retail.json"))
    assert any(it.get("item_type") == "flooring" for it in raw), (
        "Expected flooring item from retail VCT room"
    )


@pytest.mark.generalization
def test_floor_plan_retail_produces_bollard():
    """Retail floor bollard component (qty=6) → bollard item with quantity=6."""
    raw = apply_estimation_tables(_load_fixture("floor_plan_retail.json"))
    bollards = [it for it in raw if it.get("item_type") == "bollard"]
    assert bollards, "Expected bollard item from retail fixture"
    total = sum(b["quantity"] for b in bollards)
    assert total == 6.0, f"Expected 6 bollards, got {total}"


@pytest.mark.generalization
def test_floor_plan_retail_expected_constraints():
    """Validate retail fixture against expected/ constraints file."""
    exp = _load_expected("floor_plan_retail.json")
    if not exp:
        pytest.skip("No expected file for floor_plan_retail")
    raw = apply_estimation_tables(_load_fixture("floor_plan_retail.json"))
    types = _item_types(raw)
    for required in exp.get("required_item_types", []):
        assert required in types, f"Expected item_type '{required}' not found in {types}"
    for qty_type, min_q in exp.get("min_quantities", {}).items():
        total = sum(it["quantity"] for it in raw if it.get("item_type") == qty_type)
        assert total >= min_q, f"{qty_type} qty {total} < expected min {min_q}"


# ─── 2. Floor plan — industrial (sealed concrete) ────────────────────────────

@pytest.mark.generalization
def test_floor_plan_industrial_produces_items():
    """Industrial floor with large area → calculator produces at least some items."""
    raw = apply_estimation_tables(_load_fixture("floor_plan_industrial.json"))
    # Calculator processes the room (flooring/ceiling/etc.) even if wrong item type — non-empty
    assert len(raw) > 0, "Industrial floor fixture should produce at least some items"


@pytest.mark.generalization
def test_floor_plan_industrial_bollard_count():
    """Industrial fixture has 28 bollards with qty — should produce 28 bollard items."""
    raw = apply_estimation_tables(_load_fixture("floor_plan_industrial.json"))
    bollards = [it for it in raw if it.get("item_type") == "bollard"]
    assert bollards, "Expected bollard items from industrial fixture"
    total = sum(b["quantity"] for b in bollards)
    assert total == 28.0, f"Expected 28 bollards (industrial perimeter), got {total}"


@pytest.mark.generalization
def test_floor_plan_industrial_null_qty_ladder_dropped():
    """Ladder component with quantity=null must be silently dropped (no item produced)."""
    raw = apply_estimation_tables(_load_fixture("floor_plan_industrial.json"))
    ladder_items = [it for it in raw if "ladder" in it.get("description", "").lower()]
    assert ladder_items == [], (
        f"Null-qty ladder should produce no items, got: {ladder_items}"
    )


@pytest.mark.generalization
def test_floor_plan_industrial_no_flooring():
    """Industrial sealed-concrete room should NOT produce Flooring items.

    Fixed by 20-04: content-first room mapping reads material_notes and maps
    'sealed concrete' → sealed_concrete, skipping the flooring default.
    """
    raw = apply_estimation_tables(_load_fixture("floor_plan_industrial.json"))
    flooring = [it for it in raw if it.get("item_type") == "flooring"]
    assert flooring == [], (
        "Sealed concrete industrial floor must not produce Flooring"
    )


# ─── 3. Civil site — storm pipe + structures ─────────────────────────────────

@pytest.mark.generalization
def test_civil_site_produces_storm_pipe():
    """Civil pipe_runs → storm_pipe items with non-zero LF quantity."""
    raw = apply_estimation_tables(_load_fixture("civil_site.json"))
    storm_pipes = [it for it in raw if it.get("item_type") == "storm_pipe"]
    assert storm_pipes, "Expected storm_pipe items from civil fixture"
    total_lf = sum(p["quantity"] for p in storm_pipes)
    # 342.5 × 1.05 + 156.0 × 1.05 = 523.4 LF total (waste applied)
    assert total_lf > 400, f"Expected > 400 LF storm pipe, got {total_lf}"


@pytest.mark.generalization
def test_civil_site_produces_catch_basins():
    """Civil structures with type=catch_basin → catch_basin EA items."""
    raw = apply_estimation_tables(_load_fixture("civil_site.json"))
    cb = [it for it in raw if it.get("item_type") == "catch_basin"]
    assert cb, "Expected catch_basin items from civil fixture"
    total = sum(c["quantity"] for c in cb)
    assert total == 12.0, f"Expected 12 catch basins, got {total}"


@pytest.mark.generalization
def test_civil_site_produces_manholes():
    """Civil structures with type=manhole → manhole EA items."""
    raw = apply_estimation_tables(_load_fixture("civil_site.json"))
    mh = [it for it in raw if it.get("item_type") == "manhole"]
    total = sum(m["quantity"] for m in mh)
    assert total == 8.0, f"Expected 8 manholes, got {total}"


@pytest.mark.generalization
def test_civil_site_no_flooring():
    """Civil site fixture must NOT produce flooring items (no rooms in this fixture)."""
    raw = apply_estimation_tables(_load_fixture("civil_site.json"))
    assert not any(it.get("item_type") == "flooring" for it in raw), (
        "Civil site fixture has no rooms — must not produce Flooring"
    )


@pytest.mark.generalization
def test_civil_site_expected_constraints():
    """Validate civil_site against expected/ constraints file."""
    exp = _load_expected("civil_site.json")
    if not exp:
        pytest.skip("No expected file for civil_site")
    raw = apply_estimation_tables(_load_fixture("civil_site.json"))
    types = _item_types(raw)
    for excl in exp.get("excluded_item_types", []):
        assert excl not in types, f"Item type '{excl}' should NOT appear in civil_site output"


# ─── 4. Door schedule — HM + WD rows ─────────────────────────────────────────

@pytest.mark.generalization
def test_schedule_doors_produces_door_items():
    """Door schedule rows with QUANTITY → door items produced."""
    raw = apply_estimation_tables(_load_fixture("schedule_doors.json"))
    door_items = [it for it in raw if "door" in (it.get("item_type") or "")]
    assert door_items, f"Expected door items from door schedule, got: {[it['item_type'] for it in raw]}"
    total = sum(d["quantity"] for d in door_items)
    # 5 HM + 7 WD = 12 doors (frame rows use 'frame' item type, may be general)
    assert total >= 12, f"Expected at least 12 door items (HM+WD), got {total}"


@pytest.mark.generalization
def test_schedule_doors_hm_wd_separate():
    """Door schedule should produce Doors-HM / Doors-WD as separate line items.

    Fixed by 20-05: ITEM_NAME_MAP now has specific HM/WD patterns before the
    generic door catch-all. Schedule rows with TYPE=HM / TYPE=WD aggregate
    to separate canonical names.
    """
    raw = apply_estimation_tables(_load_fixture("schedule_doors.json"))
    aggregated = aggregate_takeoff(raw)
    names = {row["item"] for row in aggregated}
    assert "Doors-HM" in names, f"Expected 'Doors-HM' item, got: {names}"
    assert "Doors-WD" in names, f"Expected 'Doors-WD' item, got: {names}"


# ─── 5. Detail sheet — component null qty vs explicit qty ────────────────────

@pytest.mark.generalization
def test_detail_null_qty_component_dropped():
    """Component with quantity=null must produce no item (calculator gate)."""
    raw = apply_estimation_tables(_load_fixture("detail_ladder.json"))
    # Ladder-H-24' has qty=null → must not appear
    null_ladders = [
        it for it in raw
        if "24" in (it.get("description") or "")
    ]
    assert null_ladders == [], (
        f"null-qty ladder component must be silently dropped, got: {null_ladders}"
    )


@pytest.mark.generalization
def test_detail_qty1_component_kept():
    """Component with quantity=1 (Ladder-H-20') must produce exactly 1 item."""
    raw = apply_estimation_tables(_load_fixture("detail_ladder.json"))
    items_20 = [
        it for it in raw
        if "ladder" in (it.get("description") or "").lower()
        and "20" in (it.get("description") or "")
    ]
    assert items_20, "Expected item for Ladder-H-20' (qty=1)"
    total = sum(it["quantity"] for it in items_20)
    assert total == 1.0, f"Expected quantity=1 for Ladder-H-20', got {total}"


# ─── 6. MEP roof plan — gas piping ───────────────────────────────────────────

@pytest.mark.generalization
def test_mep_roof_gas_produces_pipe_item():
    """Gas pipe_run produces at least one pipe-related item (non-zero quantity)."""
    raw = apply_estimation_tables(_load_fixture("mep_roof_gas.json"))
    pipe_items = [it for it in raw if "pipe" in (it.get("item_type") or "")]
    assert pipe_items, "Expected at least one pipe item from gas roof fixture"
    total = sum(p["quantity"] for p in pipe_items)
    assert total > 800, f"Expected > 800 LF pipe quantity, got {total}"


@pytest.mark.generalization
def test_mep_roof_gas_produces_gas_piping():
    """Gas pipe_run should produce 'Gas Piping' (not 'Storm Pipe') in the takeoff.

    Fixed by 20-04: _detect_pipe_item_type reads material/raw_text and maps
    'black steel' / 'gas' keyword to gas_pipe; aggregator maps to 'Gas Piping'.
    """
    raw = apply_estimation_tables(_load_fixture("mep_roof_gas.json"))
    aggregated = aggregate_takeoff(raw)
    names = {row["item"] for row in aggregated}
    assert "Gas Piping" in names, f"Expected 'Gas Piping' item, got: {names}"
    assert "Storm Pipe" not in names, f"'Storm Pipe' should not appear for gas pipe, got: {names}"


# ─── 7. Specification-reference schedule — zero rows ─────────────────────────

@pytest.mark.generalization
def test_spec_reference_schedule_produces_nothing():
    """Schedule with table_purpose='specification_reference' must produce zero calc rows."""
    raw = apply_estimation_tables(_load_fixture("schedule_spec_reference.json"))
    assert raw == [], (
        f"Spec-reference schedule must produce no takeoff items, got: {raw}"
    )


@pytest.mark.generalization
def test_spec_reference_expected_constraints():
    """Validate spec_reference fixture against expected/ zero-output constraint."""
    exp = _load_expected("schedule_spec_reference.json")
    if not exp:
        pytest.skip("No expected file for schedule_spec_reference")
    raw = apply_estimation_tables(_load_fixture("schedule_spec_reference.json"))
    if "expected_item_count" in exp:
        assert len(raw) == exp["expected_item_count"], (
            f"Expected {exp['expected_item_count']} items, got {len(raw)}"
        )


# ─── 8. Content-first overrides — added by 20-04 ────────────────────────────

_INLINE_SEALED_CONCRETE = {
    "_source_sheet": "T-01",
    "sheet_type": "floor_plan",
    "rooms": [
        {"name": "Slab Area", "area": 10000, "material_notes": "sealed concrete floor per spec"},
    ],
    "components": [], "measurements": [], "schedules": [], "pipe_runs": [], "civil_structures": [],
}

_INLINE_VCT_ON_INDUSTRIAL = {
    "_source_sheet": "T-02",
    "sheet_type": "floor_plan",
    "rooms": [
        {"name": "Office Corner", "area": 5000, "material_notes": "VCT tile per spec 09 65 00"},
    ],
    "components": [], "measurements": [], "schedules": [], "pipe_runs": [], "civil_structures": [],
}


@pytest.mark.generalization
def test_content_first_sealed_concrete_overrides_default():
    """Room with 'sealed concrete' note → sealed_concrete, NOT flooring.

    Verifies content-first logic: note parsing through MATERIAL_NOTE_MAP takes
    priority over the auto-profile universal fallback.
    """
    raw = apply_estimation_tables(_INLINE_SEALED_CONCRETE)
    types = _item_types(raw)
    assert "sealed_concrete" in types, (
        f"'sealed concrete' note must produce sealed_concrete item, got: {types}"
    )
    assert "flooring" not in types, (
        f"'sealed concrete' note must not produce flooring item, got: {types}"
    )


@pytest.mark.generalization
def test_content_first_vct_on_industrial_profile():
    """Room with VCT note → flooring even when project_type='industrial'.

    Verifies content-first priority: explicit note override beats profile skip_items.
    """
    raw = apply_estimation_tables(_INLINE_VCT_ON_INDUSTRIAL, project_type="industrial")
    types = _item_types(raw)
    assert "flooring" in types, (
        f"VCT note must produce flooring even on industrial profile, got: {types}"
    )
    assert "sealed_concrete" not in types, (
        f"VCT note must not produce sealed_concrete on industrial profile, got: {types}"
    )


# ─── 9. Aggregator ITEM_NAME_MAP — Civil / Site labels ───────────────────────

def _agg(description: str, item_type: str = "general", unit: str = "ea") -> str:
    """Helper: run normalize_item_name and return canonical name."""
    from aggregator import normalize_item_name
    name, _ = normalize_item_name(description, item_type, unit)
    return name


@pytest.mark.generalization
def test_aggregator_bollard_canonical():
    assert _agg("Steel pipe bollard at parking entry") == "Bollards"


@pytest.mark.generalization
def test_aggregator_catch_basin_canonical():
    assert _agg("BB CI#4 catch basin 24\" diameter") == "Catch Basins"
    assert _agg("Drop inlet DI-3") == "Catch Basins"


@pytest.mark.generalization
def test_aggregator_manhole_canonical():
    assert _agg("Sanitary manhole MH-7") == "Manholes"
    assert _agg("Access structure MH") == "Manholes"


@pytest.mark.generalization
def test_aggregator_headwall_canonical():
    assert _agg("24\" flared end section FES-1") == "Headwall"


@pytest.mark.generalization
def test_aggregator_trench_drain_canonical():
    assert _agg("120 LF trench drain at loading dock") == "Trench Drain"
    assert _agg("Channel drain along drive aisle") == "Trench Drain"


@pytest.mark.generalization
def test_aggregator_gas_piping_canonical():
    assert _agg("Black steel pipe gas main") == "Gas Piping"
    assert _agg("CSST gas line to rooftop units") == "Gas Piping"
    assert _agg("Gas pipe 2\" black steel") == "Gas Piping"


@pytest.mark.generalization
def test_aggregator_storm_pipe_canonical():
    # normalize_item_name appends pipe size via _extract_spec_for_name when diameter is present
    name_12 = _agg("342.5 LF 12\" PVC storm sewer pipe")
    assert name_12.startswith("Storm Pipe"), f"Expected 'Storm Pipe*', got {name_12!r}"
    name_hdpe = _agg("HDPE pipe run 8 in")
    assert name_hdpe.startswith("Storm Pipe"), f"Expected 'Storm Pipe*', got {name_hdpe!r}"
    assert _agg("RCP storm pipe") == "Storm Pipe"


@pytest.mark.generalization
def test_aggregator_guard_rail_canonical():
    assert _agg("W-beam guardrail along property line") == "Guard Rail"
    assert _agg("Guard rail at truck dock") == "Guard Rail"


@pytest.mark.generalization
def test_aggregator_striping_canonical():
    assert _agg("Pavement marking - double yellow stripe") == "Striping"
    assert _agg("Lane marking 4\" white stripe") == "Striping"


@pytest.mark.generalization
def test_aggregator_asphalt_canonical():
    assert _agg("Asphalt pavement HMA 4\" base") == "Asphalt"


@pytest.mark.generalization
def test_aggregator_concrete_pavement_canonical():
    assert _agg("Concrete sidewalk flatwork 4\" thick") == "Concrete Pavement"
    assert _agg("PCC concrete pavement approach") == "Concrete Pavement"
    assert _agg("Concrete drive approach PCC") == "Concrete Pavement"


# ─── 10. Aggregator ITEM_NAME_MAP — Structural labels ────────────────────────

@pytest.mark.generalization
def test_aggregator_sealed_concrete_canonical():
    assert _agg("Sealed concrete floor 395,000 SF") == "Sealed Concrete"
    assert _agg("Polished concrete slab-on-grade") == "Sealed Concrete"


@pytest.mark.generalization
def test_aggregator_exposed_structure_canonical():
    assert _agg("Exposed structure open web joist") == "Exposed Structure"
    assert _agg("Exposed deck above") == "Exposed Structure"


@pytest.mark.generalization
def test_aggregator_tilt_up_walls_canonical():
    assert _agg("Exterior Tilt up wall panel") == "Exterior Tilt Up Wall"
    assert _agg("Interior tilt up wall") == "Interior Tilt Up Walls"
    assert _agg("Internal tilt-up panel") == "Interior Tilt Up Walls"


@pytest.mark.generalization
def test_aggregator_cmu_wall_canonical():
    assert _agg("CMU block wall 8\" masonry") == "CMU Wall"
    assert _agg("Masonry wall 12\" CMU") == "CMU Wall"


@pytest.mark.generalization
def test_aggregator_lintel_canonical():
    assert _agg("Lintel L-4 6x4x5/16 A36") == "Lintels"
    assert _agg("Steel lintel above storefront") == "Lintels"


# ─── 11. Aggregator ITEM_NAME_MAP — Architectural labels ─────────────────────

@pytest.mark.generalization
def test_aggregator_canopy_canonical():
    assert _agg("Metal entrance canopy 24x12 SF") == "Canopy"


@pytest.mark.generalization
def test_aggregator_eifs_canonical():
    assert _agg("EIFS exterior finish system") == "EIFS"
    assert _agg("Dryvit exterior insulation finish") == "EIFS"


@pytest.mark.generalization
def test_aggregator_cmu_paint_canonical():
    assert _agg("CMU paint epoxy block coat") == "CMU Paint"
    assert _agg("Masonry paint exterior CMU") == "CMU Paint"


@pytest.mark.generalization
def test_aggregator_door_hm_canonical():
    """Hollow metal door description resolves to Doors-HM, not generic Doors."""
    assert _agg("Hollow Metal Door 3x7 at entry") == "Doors-HM"
    assert _agg("HM door D-101") == "Doors-HM"


@pytest.mark.generalization
def test_aggregator_door_wd_canonical():
    """Wood door description resolves to Doors-WD, not generic Doors."""
    assert _agg("Wood door solid core 3x7") == "Doors-WD"


@pytest.mark.generalization
def test_aggregator_door_al_canonical():
    """Aluminum door resolves to Doors-AL."""
    assert _agg("Aluminum storefront door") == "Doors-AL"


@pytest.mark.generalization
def test_aggregator_frame_hm_canonical():
    """Hollow metal frame row resolves to Frame-HM."""
    assert _agg("HM Door Frame 3x7") == "Frame-HM"
    assert _agg("Hollow metal frame F-101") == "Frame-HM"


@pytest.mark.generalization
def test_aggregator_ladder_canonical():
    assert _agg("Ladder H-20 to roof hatch") == "Ladder"


@pytest.mark.generalization
def test_aggregator_lift_canonical():
    assert _agg("Personnel lift at mezzanine") == "Lift"
    assert _agg("Elevator in core") == "Lift"


# ─── 12. Aggregator ITEM_NAME_MAP — MEP labels ───────────────────────────────

@pytest.mark.generalization
def test_aggregator_fan_coil_canonical():
    assert _agg("Fan coil unit FCU-3 at offices") == "Fan Coil Units"


@pytest.mark.generalization
def test_aggregator_ahu_canonical():
    assert _agg("Air handling unit AHU-1 rooftop") == "Air Handling Units"


@pytest.mark.generalization
def test_aggregator_exhaust_fan_canonical():
    assert _agg("Exhaust fan EF-2 toilet rooms") == "Exhaust Fans"


@pytest.mark.generalization
def test_aggregator_duct_lf_canonical():
    assert _agg("Ductwork rectangular duct main trunk") == "Duct LF"
    assert _agg("Spiral duct 10\" diameter run") == "Duct LF"


@pytest.mark.generalization
def test_aggregator_conduit_lf_canonical():
    assert _agg("EMT conduit 1\" home runs") == "Conduit LF"
    assert _agg("Conduit underground 2\" PVC") == "Conduit LF"
    assert _agg("Cable tray 24\" wide") == "Conduit LF"


# ─── 13. Aggregator — schedule to canonical name integration ─────────────────

@pytest.mark.generalization
def test_aggregator_door_schedule_hm_wd_via_full_pipeline():
    """Full pipeline: schedule_doors fixture → aggregate → HM and WD separate items.

    This test replaces the xfail from 20-02 now that ITEM_NAME_MAP has HM/WD
    separation patterns (Phase 20-05).
    """
    raw = apply_estimation_tables(_load_fixture("schedule_doors.json"))
    aggregated = aggregate_takeoff(raw)
    names = {row["item"] for row in aggregated}
    assert "Doors-HM" in names, f"Expected 'Doors-HM' in {names}"
    assert "Doors-WD" in names, f"Expected 'Doors-WD' in {names}"


@pytest.mark.generalization
def test_aggregator_lintel_run_canonical():
    """lintel_runs fixture produces 'Lintels' canonical name."""
    data = {
        "_source_sheet": "A4.0",
        "sheet_type": "elevation",
        "measurements": [], "components": [], "rooms": [],
        "schedules": [], "pipe_runs": [], "civil_structures": [],
        "lintel_runs": [
            {"mark": "L-4", "size": "6×4×5/16 A36",
             "individual_length_ft": 6.0, "count": 12,
             "total_lf": 72.0, "raw_text": "L-4 @ 6'-0\" ea"},
        ],
    }
    raw = apply_estimation_tables(data)
    assert any(it.get("item_type") == "lintel" for it in raw), (
        "lintel_runs must produce lintel item_type"
    )
    aggregated = aggregate_takeoff(raw)
    names = {row["item"] for row in aggregated}
    assert "Lintels" in names, f"Expected 'Lintels' canonical name, got: {names}"
    qty = next(r["quantity"] for r in aggregated if r["item"] == "Lintels")
    assert abs(qty - 72.0 * 1.05) < 0.1, f"Expected 75.6 LF (72 × 1.05 waste), got {qty}"


@pytest.mark.generalization
def test_aggregator_duct_lf_pipe_run_canonical():
    """pipe_run with duct material → 'Duct LF' canonical name."""
    data = {
        "_source_sheet": "M2.0",
        "sheet_type": "mep_plan",
        "measurements": [], "components": [], "rooms": [],
        "schedules": [], "civil_structures": [], "lintel_runs": [],
        "pipe_runs": [
            {"length_lf": 200.0, "diameter_in": 12, "material": "rectangular duct",
             "raw_text": "200 LF 24x12 rect duct main trunk"},
        ],
    }
    raw = apply_estimation_tables(data)
    assert any(it.get("item_type") == "duct_lf" for it in raw), (
        "Duct pipe_run must produce duct_lf item_type"
    )
    aggregated = aggregate_takeoff(raw)
    names = {row["item"] for row in aggregated}
    # The description will be '12" rectangular duct duct'; normalize_item_name
    # matches \bduct\b and returns "Duct LF"
    assert "Duct LF" in names, f"Expected 'Duct LF' canonical name, got: {names}"
