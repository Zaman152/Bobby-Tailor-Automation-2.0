"""Aggregator consolidation tests."""
from aggregator import aggregate_takeoff, normalize_item_name


def test_aggregate_flooring_two_sheets():
    items = [
        {"description": "flooring conf 106", "item_type": "flooring", "calculated_quantity": 100,
         "calculated_unit": "sq_ft", "source_sheet": "A1"},
        {"description": "floor tile open office", "item_type": "flooring", "calculated_quantity": 200,
         "calculated_unit": "sq_ft", "source_sheet": "A2"},
    ]
    out = aggregate_takeoff(items)
    flooring = [r for r in out if "Flooring" in r["item"]]
    assert len(flooring) == 1
    assert flooring[0]["quantity"] == 300


def test_companion_legend_suppresses_vision_duplicate():
    """An authoritative legend item is the sole source; vision dup is dropped."""
    items = [
        {"description": "Sealed Concrete", "item_type": "sealed_concrete",
         "calculated_quantity": 395673.42, "calculated_unit": "sq_ft",
         "qty_source": "companion_takeoff_legend", "source_sheet": "A-101"},
        {"description": "Sealed Concrete for Warehouse", "item_type": "sealed_concrete",
         "calculated_quantity": 397556.0, "calculated_unit": "sq_ft",
         "qty_source": "room_profile", "source_sheet": "A-101"},
    ]
    out = aggregate_takeoff(items)
    sealed = [r for r in out if r["item"] == "Sealed Concrete"]
    assert len(sealed) == 1
    assert sealed[0]["quantity"] == 395673.42


def test_companion_legend_suppresses_base_name_variant():
    """Vision 'Columns' is dropped when legend reports 'Columns-H-35''."""
    items = [
        {"description": "Columns-H-35'", "item_type": "columns",
         "calculated_quantity": 132, "calculated_unit": "ea",
         "qty_source": "companion_takeoff_legend", "source_sheet": "S-101"},
        {"description": "Columns", "item_type": "columns",
         "calculated_quantity": 140, "calculated_unit": "ea",
         "qty_source": "count", "source_sheet": "S-101"},
    ]
    out = aggregate_takeoff(items)
    cols = [r for r in out if r["item"].startswith("Columns")]
    assert len(cols) == 1
    assert cols[0]["item"] == "Columns-H-35'"
    assert cols[0]["quantity"] == 132


def test_companion_legend_keeps_unrelated_vision_items():
    """Suppression must not touch items the legend doesn't cover."""
    items = [
        {"description": "Bollards", "item_type": "bollard", "calculated_quantity": 28,
         "calculated_unit": "ea", "qty_source": "companion_takeoff_legend",
         "source_sheet": "A-101"},
        {"description": "windows", "item_type": "general",
         "calculated_quantity": 7, "calculated_unit": "ea", "qty_source": "count",
         "source_sheet": "A-201"},
    ]
    out = aggregate_takeoff(items)
    names = {r["item"] for r in out}
    assert "Bollards" in names
    assert "Windows" in names


def test_normalize_guard_rail():
    name, unit = normalize_item_name("guard rail along parking", "general", "lf")
    assert name == "Guard Rail"
    assert unit == "LF"


def test_aggregate_empty():
    assert aggregate_takeoff([]) == []


def test_mobilization_injected_for_real_takeoff():
    """Mobilization is a universal estimating line item, added once."""
    items = [
        {"description": "sealed concrete", "item_type": "slab", "calculated_quantity": 1000,
         "calculated_unit": "SF", "source_sheet": "A-101"},
    ]
    out = aggregate_takeoff(items)
    mob = [r for r in out if r["item"] == "Mobilization"]
    assert len(mob) == 1
    assert mob[0]["quantity"] == 1
    assert mob[0]["unit"] == "EA"


def test_mobilization_not_injected_for_empty():
    assert all(r["item"] != "Mobilization" for r in aggregate_takeoff([]))


def test_mobilization_not_double_counted():
    """An explicit Mobilization note from the drawings must not be doubled."""
    items = [
        {"description": "sealed concrete", "item_type": "slab", "calculated_quantity": 1000,
         "calculated_unit": "SF", "source_sheet": "A-101"},
        {"description": "mobilization", "item_type": "", "calculated_quantity": 1,
         "calculated_unit": "EA", "source_sheet": "G-001"},
    ]
    out = aggregate_takeoff(items)
    mob = [r for r in out if r["item"] == "Mobilization"]
    assert len(mob) == 1
    assert mob[0]["quantity"] == 1
