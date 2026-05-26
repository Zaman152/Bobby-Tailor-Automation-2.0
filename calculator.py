"""
Apply estimation tables to extracted drawing data to calculate quantities.

Each measurement Claude extracts from a drawing gets matched to an estimation
table and the table's formula is applied to produce a final takeoff quantity.

The tables here are standard construction defaults — replace any value with
the client's actual numbers when provided (just edit the dict below).
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Estimation Tables ───────────────────────────────────────────────────────
# Each entry is keyed by item type. The "formula" field is just documentation
# — the actual math runs in the _calc_* functions below.
ESTIMATION_TABLES = {
    "flooring": {
        "unit_out": "sq_ft",
        "waste_factor": 1.10,          # 10% waste / cuts
        "formula": "area × waste_factor",
        "description": "Floor area to order, with 10% waste",
        "keywords": ["floor", "tile", "carpet", "lvt", "vct", "vinyl", "hardwood", "laminate"],
    },
    "drywall": {
        "unit_out": "sheets",
        "sheet_size_sf": 32,           # 4'×8' sheet = 32 sq ft
        "waste_factor": 1.12,          # 12% waste
        "formula": "ceil(area × 1.12 / 32)",
        "description": "4×8 drywall sheets needed (5/8\" type X assumed)",
        "keywords": ["drywall", "gypsum", "gwb", "gypboard", "sheetrock", "wallboard"],
    },
    "paint": {
        "unit_out": "gallons",
        "coverage_per_gallon": 350,    # sf per gallon (standard latex)
        "coats": 2,                     # primer + finish or 2 finish coats
        "formula": "ceil(area × coats / 350)",
        "description": "Paint gallons (2 coats, 350 sf coverage)",
        "keywords": ["paint", "primer", "finish coat", "epoxy"],
    },
    "wall_framing": {
        "unit_out": "studs",
        "stud_spacing_in": 16,         # 16" OC
        "stud_height_ft": 9,           # default ceiling height assumption
        "waste_factor": 1.10,
        "formula": "studs = ceil(wall_length_ft × 12 / 16) + 1 (corners +1)",
        "description": "Wall studs at 16\" OC (add top/bottom plates separately)",
        "keywords": ["wall", "partition", "stud", "framing", "metal stud", "wood stud"],
    },
    "concrete_slab": {
        "unit_out": "cy",
        "default_thickness_in": 4,
        "formula": "cy = area_sf × thickness_in / (12 × 27)",
        "description": "Concrete cubic yards (4\" slab default)",
        "keywords": ["concrete", "slab", "footing", "foundation", "slab-on-grade"],
    },
    "ceiling_grid": {
        "unit_out": "sq_ft",
        "waste_factor": 1.08,
        "formula": "area × 1.08",
        "description": "Acoustic ceiling tile area (8% waste)",
        "keywords": ["ceiling", "acoustic", "act", "lay-in", "ceiling tile", "t-bar"],
    },
    "doors": {
        "unit_out": "ea",
        "formula": "count (from schedule)",
        "description": "Door count (verify hardware spec separately)",
        "keywords": ["door", "swinging door", "double door"],
    },
    "windows": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Window count",
        "keywords": ["window", "glazing"],
    },
    "insulation": {
        "unit_out": "sq_ft",
        "waste_factor": 1.05,
        "formula": "area × 1.05",
        "description": "Insulation area (5% waste)",
        "keywords": ["insulation", "batt", "rigid", "spray foam", "r-value"],
    },
    "fire_extinguisher": {
        "unit_out": "ea",
        "formula": "count from plan",
        "description": "Fire extinguisher count",
        "keywords": ["fire extinguisher", "extinguisher"],
    },
    "electrical_fixture": {
        "unit_out": "ea",
        "formula": "count from schedule",
        "description": "Light fixture / device count",
        "keywords": ["light fixture", "led", "exit sign", "receptacle", "switch", "panel"],
    },
}


# ─── Public entry point ──────────────────────────────────────────────────────

def apply_estimation_tables(extracted_data: dict) -> List[dict]:
    """
    Apply estimation tables to extracted drawing data.
    Returns list of calculated takeoff items with source traceability.
    """
    estimates = []
    sheet_name = extracted_data.get("_source_sheet", "unknown")
    sheet_type = extracted_data.get("sheet_type", "unknown")

    # 1) Process individual measurements (dimension annotations)
    for m in extracted_data.get("measurements", []):
        e = _calculate_from_measurement(m, sheet_name, sheet_type)
        if e:
            estimates.append(e)

    # 2) Process counted components (doors, fixtures, equipment, etc.)
    for c in extracted_data.get("components", []):
        e = _calculate_from_component(c, sheet_name, sheet_type)
        if e:
            estimates.append(e)

    # 3) Process rooms — area-based calculations across multiple item types
    for room in extracted_data.get("rooms", []):
        estimates.extend(_calculate_from_room(room, sheet_name))

    # 4) Process schedules — every row becomes counted takeoff items
    for sched in extracted_data.get("schedules", []):
        estimates.extend(_calculate_from_schedule(sched, sheet_name))

    logger.info(f"  Calculated {len(estimates)} estimates from {sheet_name}")
    return estimates


# ─── Per-source-type calculators ─────────────────────────────────────────────

def _calculate_from_measurement(m: dict, sheet_name: str, sheet_type: str) -> Optional[dict]:
    """A single dimension annotation. Find what it measures, apply the table.
    REJECTS noise: scale references, catalog numbers, temperatures, design conditions,
    and anything that doesn't map to a real estimation table."""
    try:
        raw_value = m.get("value", "")
        raw_unit = (m.get("unit") or "").lower().strip()
        description = m.get("description", "") or ""
        location = m.get("location", "") or ""
        raw_text = m.get("raw_text", "") or ""

        # Reject scale references in description (e.g. "Door and Frame Elevations reference")
        desc_lower = description.lower()
        text_lower = raw_text.lower()
        for noise in ("scale", "= 1'", "= 1 '", "= 1ft", "reference", "n.t.s.", "nts",
                      "not to scale", "design conditions", "temperature", "dry bulb",
                      "wet bulb", "design dry", "design wet"):
            if noise in desc_lower or noise in text_lower:
                return None

        # Reject temperature units
        if raw_unit in ("f", "°f", "c", "°c", "degree", "deg"):
            return None

        # Parse numeric (handles feet-inches → inches, rejects catalog numbers)
        numeric = _parse_numeric(raw_value)
        if numeric is None or numeric == 0:
            return None

        # Convert to estimation units
        std_value, std_unit = _convert_units(numeric, raw_unit)

        # Classify by description
        item_type = _classify_item(description, std_unit, sheet_type)

        # Apply formula
        calc_qty, calc_unit, formula_used = _apply_formula(
            item_type, std_value, std_unit, raw_value
        )

        # GATE: don't put rows in calculations.csv that have no formula applied.
        # Single dimension annotations (mounting heights, clearances, etc.) belong in
        # raw_items.csv, not calculations.csv — they're references, not order quantities.
        if formula_used in ("no formula", "", None):
            return None

        table = ESTIMATION_TABLES.get(item_type, {})
        return {
            "item_type": item_type,
            "description": description,
            "raw_value": raw_value,
            "raw_unit": raw_unit,
            "quantity": round(calc_qty, 2) if isinstance(calc_qty, (int, float)) else calc_qty,
            "unit": calc_unit,
            "waste_factor_applied": table.get("waste_factor", 1.0),
            "formula": formula_used,
            "source_sheet": sheet_name,
            "source_location": location,
            "source_raw": raw_text or description,
            "table_used": item_type if item_type in ESTIMATION_TABLES else "none",
            "specification": "",
        }
    except Exception as e:
        logger.warning(f"Calc from measurement failed: {e}")
        return None


def _calculate_from_component(c: dict, sheet_name: str, sheet_type: str) -> Optional[dict]:
    """A counted item (e.g. door type A, fan coil unit FCU-1)."""
    try:
        name = c.get("name", "")
        qty_raw = c.get("quantity")
        unit = c.get("unit", "ea")
        spec = c.get("specification", "")
        location = c.get("location", "")

        if qty_raw is None or str(qty_raw).strip() in ("", "null", "None"):
            return None

        numeric = _parse_numeric(str(qty_raw))
        if numeric is None or numeric == 0:
            return None

        item_type = _classify_item(name, unit, sheet_type)
        table = ESTIMATION_TABLES.get(item_type, {})
        wf = table.get("waste_factor", 1.0)
        final = numeric * wf

        return {
            "item_type": item_type if item_type != "general" else "component",
            "description": name,
            "specification": spec,
            "raw_value": qty_raw,
            "raw_unit": unit,
            "quantity": round(final, 2),
            "unit": unit,
            "waste_factor_applied": wf,
            "formula": f"count × {wf}" if wf != 1.0 else "count",
            "source_sheet": sheet_name,
            "source_location": location,
            "source_raw": f"{name} — {spec}" if spec else name,
            "table_used": item_type if item_type in ESTIMATION_TABLES else "none",
        }
    except Exception as e:
        logger.warning(f"Calc from component failed: {e}")
        return None


def _calculate_from_room(room: dict, sheet_name: str) -> List[dict]:
    """A room can produce multiple takeoff items: flooring, paint, drywall, ceiling."""
    results = []
    room_name = room.get("name", "unknown")
    area_raw = room.get("area")
    dimensions = room.get("dimensions", "")

    # If area not given but L x W is, compute it
    area = _parse_numeric(str(area_raw)) if area_raw else None
    if not area and dimensions:
        area = _area_from_dimensions(dimensions)

    if not area or area == 0:
        return results

    # Default ceiling height for wall area
    ceiling_ht = 9  # ft

    # Flooring
    results.append(_room_calc(room_name, "flooring", area, "sq_ft", sheet_name, dimensions or f"area={area_raw}"))
    # Ceiling
    results.append(_room_calc(room_name, "ceiling_grid", area, "sq_ft", sheet_name, dimensions or f"area={area_raw}"))

    # For paint and drywall, estimate wall area: assume room is square: perimeter × height
    perimeter = 4 * (area ** 0.5)
    wall_area = perimeter * ceiling_ht
    results.append(_room_calc(room_name, "paint", wall_area, "sq_ft", sheet_name,
                              f"wall area ≈ perimeter ({perimeter:.0f}lf) × {ceiling_ht}ft ceiling"))
    results.append(_room_calc(room_name, "drywall", wall_area, "sq_ft", sheet_name,
                              f"wall area ≈ perimeter ({perimeter:.0f}lf) × {ceiling_ht}ft ceiling"))

    return [r for r in results if r]


def _calculate_from_schedule(sched: dict, sheet_name: str) -> List[dict]:
    """Each row of a schedule becomes a counted item ONLY when there's a real quantity.
    Skip rows that just define a type/spec without a count — those belong in raw_items.csv,
    not calculations.csv (no math to do)."""
    results = []
    sched_name = sched.get("name", "Schedule")
    rows = sched.get("rows", [])

    if not isinstance(rows, list):
        return results

    for row in rows:
        if not isinstance(row, dict):
            continue

        # Description
        desc = ""
        for k in ("DESCRIPTION", "Description", "description", "NAME", "TYPE", "ITEM"):
            if row.get(k):
                desc = str(row[k])
                break

        # Find a REAL quantity. Reject "Multiple", "Varies", "TBD", etc.
        qty = None
        qty_source = ""
        for k in ("QUANTITY", "QTY", "Qty", "COUNT", "Count"):
            if row.get(k):
                raw = str(row[k]).strip()
                if raw.lower() in ("multiple", "varies", "tbd", "n/a", "na", "-", "--", ""):
                    continue
                q = _parse_numeric(raw)
                if q and q > 0:
                    qty = q
                    qty_source = raw
                    break

        # No real quantity → skip. This row IS in raw_items.csv as a schedule_row,
        # but it has no math to put in calculations.csv. Don't fabricate "1 ea".
        if qty is None:
            continue

        # Mark/identifier
        mark = ""
        for k in ("MARK", "TYPE", "FIXTURE TYPE", "CKT", "NO", "ID"):
            if row.get(k):
                mark = str(row[k])
                break

        item_type = _classify_item(desc or sched_name, "ea", "schedule")
        full_desc = f"{sched_name} - {mark} - {desc}".strip(" -") if mark else f"{sched_name} - {desc}".strip(" -")
        row_text = " | ".join(f"{k}={v}" for k, v in row.items() if v)

        results.append({
            "item_type": item_type if item_type != "general" else "schedule_item",
            "description": full_desc,
            "raw_value": qty_source,
            "raw_unit": "ea",
            "quantity": qty,
            "unit": "ea",
            "waste_factor_applied": 1.0,
            "formula": f"count from schedule (qty column = {qty_source})",
            "source_sheet": sheet_name,
            "source_location": f"{sched_name}{' row ' + mark if mark else ''}",
            "source_raw": row_text,
            "table_used": item_type if item_type in ESTIMATION_TABLES else "none",
            "specification": row.get("SPECIFICATION") or row.get("SPEC") or "",
        })

    return results


def _room_calc(room_name: str, item_type: str, area: float, unit_in: str,
               sheet_name: str, source_note: str) -> Optional[dict]:
    """Apply a single estimation table to a room's area."""
    try:
        calc_qty, calc_unit, formula = _apply_formula(item_type, area, unit_in, str(area))
        table = ESTIMATION_TABLES.get(item_type, {})
        return {
            "item_type": item_type,
            "description": f"{item_type.replace('_', ' ').title()} for {room_name}",
            "raw_value": round(area, 1),
            "raw_unit": unit_in,
            "quantity": round(calc_qty, 2) if isinstance(calc_qty, (int, float)) else calc_qty,
            "unit": calc_unit,
            "waste_factor_applied": table.get("waste_factor", 1.0),
            "formula": formula,
            "source_sheet": sheet_name,
            "source_location": room_name,
            "source_raw": source_note,
            "table_used": item_type,
            "specification": "",
        }
    except Exception as e:
        logger.warning(f"Room calc failed for {room_name}/{item_type}: {e}")
        return None


# ─── Formula engine ──────────────────────────────────────────────────────────

def _apply_formula(item_type: str, value: float, unit: str, raw: str) -> Tuple[float, str, str]:
    """
    Given an item type + a numeric value, apply the estimation formula.
    Returns (calculated_qty, output_unit, formula_description).
    """
    import math
    table = ESTIMATION_TABLES.get(item_type, {})

    if item_type == "flooring":
        wf = table["waste_factor"]
        return value * wf, "sq_ft", f"{value:.0f} sf × {wf} waste = {value * wf:.0f} sf"

    if item_type == "drywall":
        wf = table["waste_factor"]
        sheet = table["sheet_size_sf"]
        sheets = math.ceil(value * wf / sheet)
        return sheets, "sheets", f"ceil({value:.0f} × {wf} / {sheet}sf/sheet) = {sheets} sheets"

    if item_type == "paint":
        cov = table["coverage_per_gallon"]
        coats = table["coats"]
        gallons = math.ceil(value * coats / cov)
        return gallons, "gallons", f"ceil({value:.0f} sf × {coats} coats / {cov} sf/gal) = {gallons} gal"

    if item_type == "wall_framing":
        # If value is in inches, this is OC spacing — note it; doesn't directly give stud count
        # If value is in feet, treat as wall length
        if unit == "in":
            return value, "in OC spacing", f"stud spacing reference: {value}\" OC"
        spacing_in = table["stud_spacing_in"]
        wf = table["waste_factor"]
        # Length in ft → stud count: studs = (length_ft × 12 / spacing) + 1 corner stud
        studs = math.ceil(value * 12 / spacing_in) + 1
        # Apply waste
        total = math.ceil(studs * wf)
        return total, "studs", f"ceil({value:.0f}lf × 12 / {spacing_in}\" OC) + 1 = {studs}; × {wf} waste = {total}"

    if item_type == "concrete_slab":
        # value is area in sq ft, thickness default 4"
        t = table["default_thickness_in"]
        cy = value * t / (12 * 27)
        return round(cy, 2), "cy", f"{value:.0f} sf × {t}\" / (12 × 27) = {cy:.2f} cy"

    if item_type == "ceiling_grid":
        wf = table["waste_factor"]
        return value * wf, "sq_ft", f"{value:.0f} sf × {wf} waste = {value * wf:.0f} sf"

    if item_type == "insulation":
        wf = table["waste_factor"]
        return value * wf, "sq_ft", f"{value:.0f} sf × {wf} waste"

    # Default: pass-through
    return value, unit, "no formula"


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _parse_numeric(value) -> Optional[float]:
    """Extract a CLEAN number from strings like '12'-6\"', '245 SF', '1,234', '3.5'.
    Returns None for catalog numbers, scale notations, and other text-with-digits
    that shouldn't be treated as physical quantities.
    The numeric value is returned in the SAME unit as the source — callers handle conversion."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    # Reject catalog/system identifiers like "W-L-2546" or "WL-1297" or "FCU-1"
    if re.match(r"^[A-Z]+[-\s]?[A-Z]?[-\s]?\d+$", s, re.IGNORECASE):
        return None
    # Reject anything that looks like "Letter-Number-Number" (UL system, panel codes)
    if re.match(r"^\S*[A-Za-z]+\d+[-/]\d+", s):
        return None

    # Reject scale notations: "1/4\" = 1'-0\"", "Scale 1/2\"=1'", "3/8\" = 1'-0\"", "NTS"
    if "=" in s or s.upper().strip() in ("NTS", "N.T.S.", "NOT TO SCALE"):
        return None
    if re.search(r"scale", s, re.IGNORECASE):
        return None

    # Reject pure ranges like "1 and 2", "1, 2, 3", "2 to 4". But NOT "1,250"
    # (thousands separator) or "12-6" (could be feet-inches without quotes).
    if " and " in s.lower() or " to " in s.lower():
        return None
    # "1, 2, 3" with spaces after commas → list, not number
    if re.search(r"\d+\s*,\s+\d", s):
        return None

    # Reject text that's mostly letters
    digits = sum(c.isdigit() for c in s)
    letters = sum(c.isalpha() for c in s)
    if letters > digits * 2:  # twice as many letters as digits → probably not a number
        return None

    # Feet-inches: 12'-6" or 12'6" — return in INCHES (more useful than mixed)
    m = re.match(r"^\s*(\d+)\s*[''′]\s*[-\s]?\s*(\d+(?:\.\d+)?)\s*[\"″]?\s*$", s)
    if m:
        feet = float(m.group(1))
        inches = float(m.group(2))
        return feet * 12 + inches    # return total inches

    # Just feet with explicit ': 12'
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[''′]\s*$", s)
    if m:
        return float(m.group(1)) * 12  # convert feet to inches

    # Mixed fraction: "1-1/2" or "1 1/2"
    m = re.match(r"^\s*(\d+)\s*[-\s]\s*(\d+)/(\d+)\s*[\"″]?\s*$", s)
    if m:
        return float(m.group(1)) + float(m.group(2)) / float(m.group(3))

    # Simple fraction: "3/4"
    m = re.match(r"^\s*(\d+)/(\d+)\s*[\"″]?\s*$", s)
    if m:
        return float(m.group(1)) / float(m.group(2))

    # Strip commas from thousands separators, then match a plain number with unit suffix
    s_clean = s.replace(",", "")
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*", s_clean)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None

    return None


def _area_from_dimensions(dims: str) -> Optional[float]:
    """Parse '12'-0\" x 15'-6\"' into square feet."""
    if not dims:
        return None
    parts = re.split(r"\s*[x×X]\s*", dims)
    if len(parts) != 2:
        return None
    a = _parse_numeric(parts[0])
    b = _parse_numeric(parts[1])
    if a and b:
        return a * b
    return None


def _convert_units(value: float, unit: str) -> Tuple[float, str]:
    """Convert input units to standard estimating units."""
    unit = (unit or "").lower().strip()
    conversions = {
        "sf": (value, "sq_ft"),
        "square feet": (value, "sq_ft"),
        "sq ft": (value, "sq_ft"),
        "sq.ft": (value, "sq_ft"),
        "sq_ft": (value, "sq_ft"),
        "lf": (value, "lf"),
        "linear feet": (value, "lf"),
        "ft": (value, "ft"),
        "feet": (value, "ft"),
        "in": (value, "in"),
        "inches": (value, "in"),
        "\"": (value, "in"),
        "cy": (value, "cy"),
        "cubic yards": (value, "cy"),
        "ea": (value, "ea"),
        "each": (value, "ea"),
        "ga": (value, "gallons"),
        "gal": (value, "gallons"),
    }
    return conversions.get(unit, (value, unit or "unit"))


def _classify_item(description: str, unit: str, sheet_type: str) -> str:
    """Map a description to an estimation table key by WORD-BOUNDARY keyword matching.
    Substring matching like `'door' in 'outdoor'` caused massive misclassification."""
    if not description:
        return "general"
    d = description.lower()

    # Tokenize: word boundaries only, no substring matches
    words = set(re.findall(r"[a-z][a-z0-9\-]+", d))

    for table_key, table in ESTIMATION_TABLES.items():
        for kw in table.get("keywords", []):
            kw_l = kw.lower()
            # Multi-word keyword: require the whole phrase to be present
            if " " in kw_l:
                if kw_l in d and not _is_substring_match(kw_l, d):
                    return table_key
            else:
                # Single word: exact token match (handles plurals: "door" matches "doors")
                if kw_l in words or (kw_l + "s") in words:
                    return table_key

    return "general"


def _is_substring_match(needle: str, haystack: str) -> bool:
    """Return True if needle appears only as a substring of a larger word (bad)."""
    idx = haystack.find(needle)
    if idx == -1:
        return False
    # Check char before and after — if alphanumeric, it's embedded in a word
    before = haystack[idx - 1] if idx > 0 else " "
    after = haystack[idx + len(needle)] if idx + len(needle) < len(haystack) else " "
    return before.isalnum() or after.isalnum()
