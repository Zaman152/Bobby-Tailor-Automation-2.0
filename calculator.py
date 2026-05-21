"""
Apply estimation tables to extracted drawing data to calculate quantities.
Estimation tables will be provided by the client — this module is structured
to accept them as config once received.
"""
import logging
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Estimation Tables ───────────────────────────────────────────────────────
# These will be populated once the client provides their tables.
# Format: {item_type: {unit_conversion, waste_factor, ...}}
ESTIMATION_TABLES = {
    # Example structure (to be replaced with client's actual tables):
    "flooring": {
        "unit": "sq_ft",
        "waste_factor": 1.10,   # 10% waste
        "description": "Floor area with 10% waste factor"
    },
    "wall_framing": {
        "unit": "lf",
        "stud_spacing": 16,     # inches on center
        "description": "Linear feet of wall framing"
    },
    "paint": {
        "unit": "sq_ft",
        "coverage_per_gallon": 350,
        "coats": 2,
        "description": "Wall/ceiling area for paint"
    },
    "concrete": {
        "unit": "cy",
        "description": "Cubic yards of concrete"
    },
    "drywall": {
        "unit": "sq_ft",
        "sheet_size": 32,       # sq ft per 4x8 sheet
        "waste_factor": 1.12,
        "description": "Drywall sheets needed"
    },
}


def apply_estimation_tables(extracted_data: dict) -> list[dict]:
    """
    Apply estimation tables to extracted drawing data.
    Returns list of calculated estimates with source tracing.
    """
    estimates = []
    sheet_name = extracted_data.get("_source_sheet", "unknown")
    sheet_type = extracted_data.get("sheet_type", "unknown")

    # Process measurements
    for m in extracted_data.get("measurements", []):
        estimate = _calculate_from_measurement(m, sheet_name, sheet_type)
        if estimate:
            estimates.append(estimate)

    # Process components
    for c in extracted_data.get("components", []):
        estimate = _calculate_from_component(c, sheet_name, sheet_type)
        if estimate:
            estimates.append(estimate)

    # Process rooms (area-based calculations)
    for room in extracted_data.get("rooms", []):
        room_estimates = _calculate_from_room(room, sheet_name)
        estimates.extend(room_estimates)

    logger.info(f"  Calculated {len(estimates)} estimates from {sheet_name}")
    return estimates


def _calculate_from_measurement(measurement: dict, sheet_name: str, sheet_type: str) -> Optional[dict]:
    try:
        raw_value = measurement.get("value", "")
        unit = measurement.get("unit", "").lower()
        description = measurement.get("description", "")
        location = measurement.get("location", "")

        # Parse numeric value
        numeric_value = _parse_numeric(raw_value)
        if numeric_value is None:
            return None

        # Convert units if needed
        converted_value, converted_unit = _convert_units(numeric_value, unit)

        # Determine item type and apply table
        item_type = _classify_item(description, unit, sheet_type)
        table = ESTIMATION_TABLES.get(item_type, {})
        waste_factor = table.get("waste_factor", 1.0)

        final_quantity = converted_value * waste_factor

        return {
            "item_type": item_type,
            "description": description,
            "raw_value": raw_value,
            "raw_unit": unit,
            "quantity": round(final_quantity, 2),
            "unit": converted_unit,
            "waste_factor_applied": waste_factor,
            "source_sheet": sheet_name,
            "source_location": location,
            "source_raw": measurement.get("raw_text", ""),
            "table_used": item_type if item_type in ESTIMATION_TABLES else "none",
        }
    except Exception as e:
        logger.warning(f"Could not calculate from measurement: {e}")
        return None


def _calculate_from_component(component: dict, sheet_name: str, sheet_type: str) -> Optional[dict]:
    try:
        name = component.get("name", "")
        qty_raw = component.get("quantity")
        unit = component.get("unit", "ea")
        spec = component.get("specification", "")
        location = component.get("location", "")

        if qty_raw is None:
            return None

        numeric_qty = _parse_numeric(str(qty_raw))
        if numeric_qty is None:
            return None

        return {
            "item_type": "component",
            "description": name,
            "specification": spec,
            "quantity": numeric_qty,
            "unit": unit,
            "waste_factor_applied": 1.0,
            "source_sheet": sheet_name,
            "source_location": location,
            "source_raw": name,
            "table_used": "none",
        }
    except Exception as e:
        logger.warning(f"Could not calculate from component: {e}")
        return None


def _calculate_from_room(room: dict, sheet_name: str) -> list[dict]:
    results = []
    room_name = room.get("name", "unknown")
    area_raw = room.get("area")

    if not area_raw:
        return results

    area = _parse_numeric(str(area_raw))
    if area is None:
        return results

    # Apply relevant area-based tables
    area_items = ["flooring", "paint", "drywall"]
    for item_type in area_items:
        table = ESTIMATION_TABLES.get(item_type, {})
        waste_factor = table.get("waste_factor", 1.0)
        final_qty = area * waste_factor

        results.append({
            "item_type": item_type,
            "description": f"{item_type.title()} - {room_name}",
            "quantity": round(final_qty, 2),
            "unit": "sq_ft",
            "waste_factor_applied": waste_factor,
            "source_sheet": sheet_name,
            "source_location": room_name,
            "source_raw": f"Room area: {area_raw}",
            "table_used": item_type,
        })

    return results


def _parse_numeric(value: str) -> Optional[float]:
    """Extract numeric value from strings like \"12'-6\"\", \"245 SF\", \"1,234\"."""
    import re
    if not value:
        return None

    # Handle feet-inches: 12'-6"
    feet_inches = re.match(r"(\d+)'[\s-]?(\d+)\"?", str(value))
    if feet_inches:
        feet = float(feet_inches.group(1))
        inches = float(feet_inches.group(2))
        return feet + inches / 12

    # Handle plain numbers with commas
    num = re.sub(r"[^\d.]", "", str(value).replace(",", ""))
    try:
        return float(num) if num else None
    except ValueError:
        return None


def _convert_units(value: float, unit: str) -> Tuple[float, str]:
    """Convert to standard units."""
    unit = unit.lower().strip()
    conversions = {
        "sf": (value, "sq_ft"),
        "square feet": (value, "sq_ft"),
        "sq ft": (value, "sq_ft"),
        "lf": (value, "lf"),
        "linear feet": (value, "lf"),
        "in": (value / 12, "ft"),
        "inches": (value / 12, "ft"),
        "cy": (value, "cy"),
        "cubic yards": (value, "cy"),
        "ea": (value, "ea"),
        "each": (value, "ea"),
    }
    return conversions.get(unit, (value, unit or "unit"))


def _classify_item(description: str, unit: str, sheet_type: str) -> str:
    """Map measurement description to an estimation table key."""
    desc_lower = description.lower()
    if any(w in desc_lower for w in ["floor", "tile", "carpet", "lvt", "vct"]):
        return "flooring"
    if any(w in desc_lower for w in ["wall", "partition", "stud", "framing"]):
        return "wall_framing"
    if any(w in desc_lower for w in ["paint", "primer", "finish"]):
        return "paint"
    if any(w in desc_lower for w in ["concrete", "slab", "footing"]):
        return "concrete"
    if any(w in desc_lower for w in ["drywall", "gypsum", "gwb"]):
        return "drywall"
    return "general"
