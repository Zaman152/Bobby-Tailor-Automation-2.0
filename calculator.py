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
    "storm_pipe": {
        "unit_out": "lf",
        "waste_factor": 1.05,
        "formula": "length × 1.05",
        "description": "Storm sewer pipe LF",
        "keywords": ["pvc", "hdpe", "rcp", "storm pipe", "culvert", "sch 40", "storm sewer"],
    },
    "trench_drain": {
        "unit_out": "lf",
        "waste_factor": 1.05,
        "formula": "length × 1.05",
        "description": "Trench/channel drain LF",
        "keywords": ["trench drain", "channel drain", "slot drain", "linear drain"],
    },
    "catch_basin": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Catch basin / drop inlet",
        "keywords": ["catch basin", "bb ci", "drop inlet", "curb inlet", "storm inlet"],
    },
    "manhole": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Manhole structures",
        "keywords": ["manhole", "mh", "access structure"],
    },
    "headwall": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Pipe headwall / flared end section",
        "keywords": ["headwall", "flared end", "end section", "fes", "wingwall"],
    },
    "bollard": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Bollards",
        "keywords": ["bollard", "pipe bollard"],
    },
    "guard_rail": {
        "unit_out": "lf",
        "waste_factor": 1.03,
        "formula": "length × 1.03",
        "description": "Guard rail LF",
        "keywords": ["guard rail", "guardrail", "barrier rail", "w-beam"],
    },
    "hand_rail": {
        "unit_out": "lf",
        "waste_factor": 1.05,
        "formula": "length × 1.05",
        "description": "Handrail LF",
        "keywords": ["hand rail", "handrail", "stair rail"],
    },
    "striping": {
        "unit_out": "lf",
        "formula": "length",
        "description": "Pavement striping LF",
        "keywords": ["striping", "stripe", "pavement marking", "lane marking"],
    },
    "concrete_pavement": {
        "unit_out": "sq_ft",
        "waste_factor": 1.03,
        "formula": "area × 1.03",
        "description": "Concrete pavement SF",
        "keywords": ["concrete pavement", "pcc", "flatwork", "sidewalk"],
    },
    "asphalt": {
        "unit_out": "sq_ft",
        "waste_factor": 1.03,
        "formula": "area × 1.03",
        "description": "Asphalt pavement SF",
        "keywords": ["asphalt", "hma", "blacktop"],
    },
    "tilt_up_wall": {
        "unit_out": "sq_ft",
        "formula": "area",
        "description": "Tilt-up wall panels SF",
        "keywords": ["tilt up", "tilt-up", "tiltup", "precast panel"],
    },
    "exposed_structure": {
        "unit_out": "sq_ft",
        "formula": "area",
        "description": "Exposed structure SF",
        "keywords": ["exposed structure", "exposed concrete", "exposed steel"],
    },
    "exterior_soffit": {
        "unit_out": "sq_ft",
        "formula": "area",
        "description": "Exterior soffit SF",
        "keywords": ["soffit", "exterior soffit", "canopy soffit"],
    },
    "sealed_concrete": {
        "unit_out": "sq_ft",
        "waste_factor": 1.0,
        "formula": "area",
        "description": "Sealed/polished concrete floor SF",
        "keywords": ["sealed concrete", "polished concrete", "concrete floor", "slab on grade", "sog"],
    },
    "cmu_wall": {
        "unit_out": "sq_ft",
        "waste_factor": 1.0,
        "formula": "area",
        "description": "CMU masonry wall SF",
        "keywords": ["cmu wall", "cmu", "masonry", "block wall", "concrete masonry"],
    },
    "internal_tilt_up_wall": {
        "unit_out": "sq_ft",
        "waste_factor": 1.0,
        "formula": "area",
        "description": "Internal tilt-up wall panel SF",
        "keywords": [
            "internal tilt", "interior tilt", "interior concrete wall",
            "internal tilt up", "int tilt", "tilt up wall",
        ],
    },
    "columns": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Structural columns EA",
        "keywords": ["columns", "column", "structural column", "steel column", "concrete column"],
    },
    "stairs": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Stairs EA",
        "keywords": ["stair", "stairway", "staircase"],
    },
    "ladder": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Fixed ladder EA",
        "keywords": ["ladder", "roof ladder", "wall ladder"],
    },
    "lift": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Material lift / elevator EA",
        "keywords": ["lift", "material lift", "personnel lift", "elevator"],
    },
    "mobilization": {
        "unit_out": "ea",
        "formula": "count",
        "description": "Mobilization lump sum EA",
        "keywords": ["mobilization", "mobilisation", "mobilize"],
    },
    "canopy": {
        "unit_out": "sq_ft",
        "waste_factor": 1.0,
        "formula": "area",
        "description": "Metal/shade canopy SF",
        "keywords": ["canopy", "metal canopy", "entrance canopy", "shade canopy"],
    },
    "eifs": {
        "unit_out": "sq_ft",
        "waste_factor": 1.05,
        "formula": "area × 1.05",
        "description": "Exterior Insulation and Finish System (EIFS/Dryvit) SF",
        "keywords": ["eifs", "exterior insulation", "dryvit", "synthetic stucco"],
    },
    "cmu_paint": {
        "unit_out": "sq_ft",
        "waste_factor": 1.0,
        "formula": "area (SF of CMU surface to paint)",
        "description": "CMU/masonry wall surface area to paint (SF)",
        "keywords": ["cmu paint", "block paint", "masonry paint", "epoxy block"],
    },
    "gas_pipe": {
        "unit_out": "lf",
        "waste_factor": 1.05,
        "formula": "length × 1.05",
        "description": "Gas piping LF (black steel / CSST)",
        "keywords": ["gas pipe", "gas piping", "black steel pipe", "csst", "gas line"],
    },
    "lintel": {
        "unit_out": "lf",
        "waste_factor": 1.05,
        "formula": "length × 1.05",
        "description": "Steel lintel LF over openings",
        "keywords": ["lintel", "steel lintel", "angle lintel", "l-4", "lintel run"],
    },
    "duct_lf": {
        "unit_out": "lf",
        "waste_factor": 1.10,
        "formula": "length × 1.10",
        "description": "HVAC ductwork LF (10% allowance for fittings/connections)",
        "keywords": ["duct lf", "ductwork", "rectangular duct", "round duct", "spiral duct", "flex duct"],
    },
    "conduit_lf": {
        "unit_out": "lf",
        "waste_factor": 1.10,
        "formula": "length × 1.10",
        "description": "Electrical conduit LF (10% allowance for fittings)",
        "keywords": ["conduit", "emt", "pvc conduit", "rigid conduit", "wireway", "cable tray", "raceway"],
    },
}


# ─── Project-type profiles ────────────────────────────────────────────────────
# Each profile defines how to calculate room areas when drawing content is silent.
# Priority: room content (notes/materials) > profile defaults > auto fallback.
PROJECT_TYPE_PROFILES: Dict[str, Dict] = {
    "industrial": {
        "default_floor_items": ["sealed_concrete"],
        "default_ceiling_items": ["exposed_structure"],
        "default_wall_items": [],
        "skip_items": ["flooring", "ceiling_grid", "drywall"],
        "expect_items": ["tilt_up_wall", "bollard", "columns"],
        "area_tolerance": 0.05,
    },
    "retail": {
        "default_floor_items": ["flooring"],
        "default_ceiling_items": ["ceiling_grid"],
        "default_wall_items": ["paint", "drywall"],
        "skip_items": ["sealed_concrete"],
        "expect_items": ["storefront", "bollard", "canopy"],
        "area_tolerance": 0.03,
    },
    "office": {
        "default_floor_items": ["flooring"],
        "default_ceiling_items": ["ceiling_grid"],
        "default_wall_items": ["paint", "drywall"],
        "skip_items": ["sealed_concrete", "tilt_up_wall"],
        "expect_items": ["drywall", "doors", "windows"],
        "area_tolerance": 0.03,
    },
    "civil": {
        "default_floor_items": [],
        "default_ceiling_items": [],
        "default_wall_items": [],
        "skip_items": ["flooring", "ceiling_grid", "drywall"],
        "expect_items": ["storm_pipe", "manhole", "catch_basin", "striping"],
        "area_tolerance": 0.05,
    },
    "residential": {
        "default_floor_items": ["flooring"],
        "default_ceiling_items": [],
        "default_wall_items": ["paint", "drywall", "insulation"],
        "skip_items": ["exposed_structure", "tilt_up_wall"],
        "expect_items": ["drywall", "insulation", "windows", "doors"],
        "area_tolerance": 0.03,
    },
    "institutional": {
        "default_floor_items": ["flooring"],
        "default_ceiling_items": ["ceiling_grid"],
        "default_wall_items": ["paint", "drywall"],
        "skip_items": ["sealed_concrete"],
        "expect_items": ["drywall", "doors", "windows"],
        "area_tolerance": 0.03,
    },
    "mixed_use": {
        "default_floor_items": ["flooring"],
        "default_ceiling_items": [],
        "default_wall_items": ["paint", "drywall"],
        "skip_items": [],
        "expect_items": ["storefront", "parking"],
        "area_tolerance": 0.05,
    },
    # Determined by content-first logic; profile keys are empty (no-op defaults).
    "auto": {
        "default_floor_items": [],
        "default_ceiling_items": [],
        "default_wall_items": [],
        "skip_items": [],
        "expect_items": [],
        "area_tolerance": 0.05,
    },
}


# ─── Material/note → item-type map ───────────────────────────────────────────
# Ordered list: first match wins within the same category.
# (regex_pattern, item_type)
MATERIAL_NOTE_MAP = [
    # Floor surface types — explicitly override generic "flooring"
    (r"sealed\s*concrete|polished\s*concrete|sog\b|slab[- ]on[- ]grade", "sealed_concrete"),
    # Generic flooring (avoid plain "tile" to prevent matching acoustic tile)
    (r"\bvct\b|lvt\b|lvp\b|\bcarpet\b|\bhardwood\b|\blaminate\b"
     r"|vinyl\s*floor|floor\s*tile|ceramic\s*tile|porcelain\s*tile", "flooring"),
    # Ceiling types
    (r"acoustic\s*tile|ceiling\s*tile|ceiling\s*grid|\bact\b|lay.?in\s*ceil|t.?bar\s*ceil", "ceiling_grid"),
    (r"exposed\s*structure|exposed\s*deck|open\s*web\s*joist|bar\s*joist", "exposed_structure"),
    # Wall types
    (r"tilt[- ]?up\s*panel?|precast\s*panel", "tilt_up_wall"),
    (r"\bcmu\b|block\s*wall|concrete\s*masonry\s*unit", "cmu_wall"),
    (r"\beifs\b|exterior\s*insulation|dryvit|synthetic\s*stucco", "eifs"),
    (r"\bcanopy\b|metal\s*canopy|entrance\s*canopy", "canopy"),
    # Wall finishes
    (r"cmu\s*paint|block\s*paint|masonry\s*paint|epoxy\s*block", "cmu_paint"),
]


# ─── Public entry point ──────────────────────────────────────────────────────

def apply_estimation_tables(extracted_data: dict, project_type: str = "auto") -> List[dict]:
    """
    Apply estimation tables to extracted drawing data.

    Args:
        extracted_data: Dict produced by Claude extraction for a single sheet.
        project_type: Building type key from PROJECT_TYPE_PROFILES. Defaults to
            "auto", which uses content-first note matching with a universal fallback.

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

    # 3) Process rooms — content-first area calculations
    for room in extracted_data.get("rooms", []):
        estimates.extend(_calculate_from_room(room, sheet_name, project_type))

    # 4) Process schedules — takeoff schedules only
    for sched in extracted_data.get("schedules", []):
        estimates.extend(_calculate_from_schedule(sched, sheet_name))

    # 5) Pipe runs, civil structures, and lintel runs (v2.1)
    estimates.extend(_calculate_from_pipe_runs(extracted_data.get("pipe_runs", []), sheet_name))
    estimates.extend(_calculate_from_civil_structures(extracted_data.get("civil_structures", []), sheet_name))
    estimates.extend(_calculate_from_lintel_runs(extracted_data.get("lintel_runs", []), sheet_name))

    estimates = _suppress_profile_duplicates(estimates)
    logger.info(f"  Calculated {len(estimates)} estimates from {sheet_name}")
    return estimates


def resolve_spec_lookups(all_extracted: List[dict], estimates: List[dict]) -> List[dict]:
    """Enrich estimates with matching specification reference table rows."""
    spec_refs: Dict[str, Dict] = {}
    for d in all_extracted:
        for sched in d.get("schedules", []):
            if sched.get("table_purpose") != "specification_reference":
                continue
            key_col = sched.get("lookup_key") or "PIPE SIZE"
            table_rows = {}
            for row in sched.get("rows", []):
                if not isinstance(row, dict):
                    continue
                k = row.get(key_col) or row.get("PIPE SIZE") or row.get("Pipe Size")
                if k:
                    table_rows[str(k).strip()] = row
            if table_rows:
                spec_refs[sched.get("name", "spec")] = {"rows": table_rows, "columns": sched.get("columns", [])}

    if not spec_refs:
        return estimates

    enriched = []
    for est in estimates:
        desc = (est.get("description") or "").lower()
        size_match = re.search(r'(\d+)\s*(?:in|inch|")', desc)
        if size_match:
            size_str = f'{size_match.group(1)} in'
            for table_name, table_data in spec_refs.items():
                if size_str in table_data["rows"]:
                    est = dict(est)
                    est["spec_reference"] = {
                        "table": table_name,
                        "matched_size": size_str,
                        "spec": table_data["rows"][size_str],
                    }
                    break
        enriched.append(est)
    return enriched


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

        # Detail sheets: dimension callouts are not install counts (RC-6)
        if sheet_type == "detail" and item_type in ("bollard", "stairs", "columns", "ladder", "lift"):
            return None

        # Apply formula
        calc_qty, calc_unit, formula_used = _apply_formula(
            item_type, std_value, std_unit, raw_value
        )

        # GATE: don't put rows in calculations.csv that have no formula applied.
        # Single dimension annotations (mounting heights, clearances, etc.) belong in
        # raw_items.csv, not calculations.csv — they're references, not order quantities.
        if formula_used in ("no formula", "", None):
            return None

        # GATE: EA items derived from dimension measurements must be whole numbers ≥ 1.
        # A fractional EA value (e.g. 0.10 bollards, 0.01 stairs) means a dimension
        # annotation was misclassified as a count.  Drop to prevent noise in the takeoff.
        if calc_unit == "ea" and isinstance(calc_qty, (int, float)):
            if calc_qty < 1:
                return None
            if calc_qty != int(calc_qty):
                return None

        table = ESTIMATION_TABLES.get(item_type, {})
        is_approx = bool(m.get("approximate", False))
        formula_out = formula_used
        if is_approx:
            formula_out = f"{formula_used} [FIELD VERIFY ±]"

        return {
            "item_type": item_type,
            "description": description,
            "raw_value": raw_value,
            "raw_unit": raw_unit,
            "quantity": round(calc_qty, 2) if isinstance(calc_qty, (int, float)) else calc_qty,
            "unit": calc_unit,
            "waste_factor_applied": table.get("waste_factor", 1.0),
            "formula": formula_out,
            "approximate": is_approx,
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


def _room_note_text(room: dict) -> str:
    """Collect all textual fields from a room dict into a single string for pattern matching."""
    parts: List[str] = []
    for key in ("notes", "material_notes", "ceiling", "finish", "spec"):
        val = room.get(key)
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            parts.extend(str(v) for v in val if v)
    materials = room.get("materials")
    if isinstance(materials, list):
        parts.extend(str(m) for m in materials if m)
    elif isinstance(materials, str) and materials:
        parts.append(materials)
    return " ".join(parts)


def _calculate_from_room(room: dict, sheet_name: str, project_type: str = "auto") -> List[dict]:
    """Content-first room area calculation.

    Priority chain:
      1. Room notes/materials parsed through MATERIAL_NOTE_MAP (per category)
      2. PROJECT_TYPE_PROFILES[project_type] defaults (floor/ceiling/wall)
      3. Universal fallback for "auto" profile (flooring + ceiling_grid + paint + drywall)

    Profile skip_items are respected at every level.
    """
    results: List[dict] = []
    room_name = room.get("name", "unknown")
    area_raw = room.get("area")
    dimensions = room.get("dimensions", "")

    area = _parse_numeric(str(area_raw)) if area_raw else None
    if not area and dimensions:
        area = _area_from_dimensions(dimensions)
    if not area or area == 0:
        return results

    ceiling_ht = 9  # ft — default wall height
    perimeter = 4 * (area ** 0.5)
    wall_area = perimeter * ceiling_ht
    src_area = dimensions or f"area={area_raw}"
    src_wall = f"wall area ≈ perimeter ({perimeter:.0f}lf) × {ceiling_ht}ft ceiling"

    profile = PROJECT_TYPE_PROFILES.get(project_type, PROJECT_TYPE_PROFILES["auto"])
    skip = set(profile.get("skip_items", []))

    # --- Step 1: content-first matching via MATERIAL_NOTE_MAP ---
    note_text = _room_note_text(room)

    _FLOOR_TYPES = {"sealed_concrete", "flooring", "concrete_pavement", "asphalt"}
    _CEIL_TYPES = {"ceiling_grid", "exposed_structure", "exterior_soffit"}
    _WALL_TYPES = {"paint", "drywall", "cmu_wall", "cmu_paint", "eifs", "tilt_up_wall", "insulation"}

    content_floor: List[str] = []
    content_ceil: List[str] = []
    content_wall: List[str] = []

    # Content matches are NOT filtered by skip_items — explicit drawing content always
    # overrides the profile (e.g. VCT note on industrial project → flooring, not sealed_concrete).
    # skip_items only prevents profile *defaults* from being applied when content is silent.
    for pattern, matched_type in MATERIAL_NOTE_MAP:
        if re.search(pattern, note_text, re.IGNORECASE):
            if matched_type in _FLOOR_TYPES and matched_type not in content_floor:
                content_floor.append(matched_type)
            elif matched_type in _CEIL_TYPES and matched_type not in content_ceil:
                content_ceil.append(matched_type)
            elif matched_type in _WALL_TYPES and matched_type not in content_wall:
                content_wall.append(matched_type)

    # --- Step 2: produce floor items ---
    if content_floor:
        for item_type in content_floor:
            results.append(_room_calc(room_name, item_type, area, "sq_ft", sheet_name, src_area))
    else:
        # Profile defaults, then universal fallback
        floor_defaults = [i for i in profile.get("default_floor_items", []) if i not in skip]
        if floor_defaults:
            for item_type in floor_defaults:
                results.append(_room_calc(room_name, item_type, area, "sq_ft", sheet_name, src_area))
        elif "flooring" not in skip:
            # Universal fallback (auto profile has empty defaults)
            results.append(_room_calc(room_name, "flooring", area, "sq_ft", sheet_name, src_area))

    # --- Step 3: produce ceiling items ---
    if content_ceil:
        for item_type in content_ceil:
            results.append(_room_calc(room_name, item_type, area, "sq_ft", sheet_name, src_area))
    else:
        ceil_defaults = [i for i in profile.get("default_ceiling_items", []) if i not in skip]
        if ceil_defaults:
            for item_type in ceil_defaults:
                results.append(_room_calc(room_name, item_type, area, "sq_ft", sheet_name, src_area))
        elif "ceiling_grid" not in skip:
            results.append(_room_calc(room_name, "ceiling_grid", area, "sq_ft", sheet_name, src_area))

    # --- Step 4: produce wall items ---
    if content_wall:
        for item_type in content_wall:
            results.append(_room_calc(room_name, item_type, wall_area, "sq_ft", sheet_name, src_wall))
    else:
        wall_defaults = [i for i in profile.get("default_wall_items", []) if i not in skip]
        if wall_defaults:
            for item_type in wall_defaults:
                results.append(_room_calc(room_name, item_type, wall_area, "sq_ft", sheet_name, src_wall))
        else:
            # Universal fallback — paint + drywall (unless profile explicitly skips them)
            if "paint" not in skip:
                results.append(_room_calc(room_name, "paint", wall_area, "sq_ft", sheet_name, src_wall))
            if "drywall" not in skip:
                results.append(_room_calc(room_name, "drywall", wall_area, "sq_ft", sheet_name, src_wall))

    return [r for r in results if r]


def _schedule_is_takeoff(sched: dict) -> bool:
    purpose = sched.get("table_purpose", "takeoff_schedule")
    if purpose in ("specification_reference", "general_notes", "finish_schedule", "room_schedule"):
        return False
    if sched.get("use_for_takeoff") is False:
        return False
    return True


def _detect_pipe_item_type(run: dict) -> str:
    """Classify a pipe run into a calculator item type from material/raw_text.

    Classification priority (first match wins):
      gas_pipe   — gas, black steel, CSST, yellow PE
      duct_lf    — HVAC ductwork (rectangular/spiral/flex duct)
      conduit_lf — electrical conduit, wireway, cable tray, raceway
      guard_rail — guard rail run material
      hand_rail  — hand rail / pipe rail
      striping   — pavement marking / striping
      trench_drain — trench/channel drain
      storm_pipe — default (PVC, HDPE, RCP, other piping)
    """
    material = (run.get("material") or "").lower()
    raw_text = (run.get("raw_text") or "").lower()
    pipe_type = (run.get("type") or "").lower()
    combined = f"{material} {raw_text} {pipe_type}"

    if re.search(r"gas\b|gas\s*pip|black\s*steel|csst|yellow\s*pe|gas\s*line", combined):
        return "gas_pipe"
    if re.search(r"duct\b|ductwork|rectangular\s*duct|spiral\s*duct|flex\s*duct|sheet\s*metal\s*duct", combined):
        return "duct_lf"
    if re.search(r"\bconduit\b|emt\b|wireway|cable\s*tray|raceway\b", combined):
        return "conduit_lf"
    if re.search(r"guard\s*rail|guardrail|barrier\s*rail|w.?beam", combined):
        return "guard_rail"
    if re.search(r"hand\s*rail|handrail|stair\s*rail|pipe\s*rail", combined):
        return "hand_rail"
    if re.search(r"\bstrip|pavement\s*mark|lane\s*mark", combined):
        return "striping"
    if re.search(r"trench.*drain|channel.*drain|slot.*drain|linear.*drain", combined):
        return "trench_drain"
    return "storm_pipe"


def _calculate_from_pipe_runs(pipe_runs: list, sheet_name: str) -> List[dict]:
    results = []
    _TYPE_LABEL = {
        "gas_pipe": "gas piping",
        "trench_drain": "trench drain",
        "guard_rail": "guard rail",
        "hand_rail": "hand rail",
        "striping": "striping",
        "duct_lf": "duct",
        "conduit_lf": "conduit",
        "storm_pipe": "storm pipe",
    }
    for run in pipe_runs:
        if not isinstance(run, dict):
            continue
        length = run.get("length_lf")
        if length is None:
            continue
        try:
            lf = float(length)
        except (TypeError, ValueError):
            continue
        if lf <= 0:
            continue
        diam = run.get("diameter_in", "")
        material = run.get("material", "")
        item_type = _detect_pipe_item_type(run)
        label = _TYPE_LABEL.get(item_type, "pipe run")
        desc = f'{diam}" {material} {label}'.strip() if diam else f"{label.title()} run"
        calc_qty, calc_unit, formula = _apply_formula(item_type, lf, "lf", str(lf))
        table = ESTIMATION_TABLES.get(item_type, {})
        results.append({
            "item_type": item_type,
            "description": desc,
            "raw_value": lf,
            "raw_unit": "lf",
            "quantity": round(calc_qty, 2),
            "unit": calc_unit,
            "waste_factor_applied": table.get("waste_factor", 1.0),
            "formula": formula,
            "source_sheet": sheet_name,
            "source_location": run.get("raw_text", "")[:80],
            "source_raw": run.get("raw_text", ""),
            "table_used": item_type,
            "specification": f"slope {run.get('slope_pct')}%" if run.get("slope_pct") else "",
        })
    return results


def _calculate_from_civil_structures(structures: list, sheet_name: str) -> List[dict]:
    results = []
    type_map = {
        "catch_basin": "catch_basin",
        "manhole": "manhole",
        "headwall": "headwall",
        "junction_box": "catch_basin",
        "cleanout": "catch_basin",
    }
    for s in structures:
        if not isinstance(s, dict):
            continue
        stype = (s.get("type") or "other").lower()
        item_type = type_map.get(stype, "catch_basin" if "basin" in stype or "bb" in stype else "general")
        if item_type == "general":
            continue
        qty = s.get("quantity", 1)
        try:
            n = float(qty)
        except (TypeError, ValueError):
            n = 1.0
        sid = s.get("id", "structure")
        spec = s.get("specification", "")
        if s.get("ground_level") is not None:
            spec = f"{spec} GL={s.get('ground_level')}".strip()
        calc_qty, calc_unit, formula = _apply_formula(item_type, n, "ea", str(n))
        table = ESTIMATION_TABLES.get(item_type, {})
        results.append({
            "item_type": item_type,
            "description": sid,
            "raw_value": n,
            "raw_unit": "ea",
            "quantity": round(calc_qty, 2),
            "unit": calc_unit,
            "waste_factor_applied": table.get("waste_factor", 1.0),
            "formula": formula,
            "source_sheet": sheet_name,
            "source_location": sid,
            "source_raw": spec,
            "table_used": item_type,
            "specification": spec,
        })
    return results


def _calculate_from_lintel_runs(lintel_runs: list, sheet_name: str) -> List[dict]:
    """Convert lintel_runs[] entries into takeoff items (LF with 5% waste).

    Each run can supply total_lf directly, or individual_length_ft × count.
    Runs with zero computed length are silently skipped.
    """
    results = []
    for run in lintel_runs:
        if not isinstance(run, dict):
            continue
        total_lf = run.get("total_lf")
        if not total_lf:
            ind = run.get("individual_length_ft") or 0
            cnt = run.get("count") or 1
            try:
                total_lf = float(ind) * float(cnt)
            except (TypeError, ValueError):
                total_lf = 0
        try:
            total_lf = float(total_lf)
        except (TypeError, ValueError):
            continue
        if total_lf <= 0:
            continue

        mark = run.get("mark", "")
        size = run.get("size", "")
        ind_lf = run.get("individual_length_ft")
        cnt = run.get("count")
        desc = f"Lintel {mark} {size}".strip()
        if ind_lf and cnt:
            formula_str = f"{ind_lf} lf × {cnt} = {total_lf} lf"
        else:
            formula_str = f"{total_lf} lf (total annotated)"

        calc_qty, calc_unit, formula_out = _apply_formula("lintel", total_lf, "lf", str(total_lf))
        table = ESTIMATION_TABLES.get("lintel", {})
        results.append({
            "item_type": "lintel",
            "description": desc or "Lintel run",
            "raw_value": total_lf,
            "raw_unit": "lf",
            "quantity": round(calc_qty, 2),
            "unit": calc_unit,
            "waste_factor_applied": table.get("waste_factor", 1.05),
            "formula": formula_out,
            "source_sheet": sheet_name,
            "source_location": run.get("location", ""),
            "source_raw": run.get("raw_text", ""),
            "table_used": "lintel",
            "specification": f"mark={mark}" if mark else "",
        })
    return results


def _row_schedule_unit(row: dict) -> str:
    """Read UNIT/UOM from a schedule row; default EA when absent."""
    for k in ("UNIT", "Unit", "UOM", "uom", "U/M"):
        if row.get(k):
            return str(row[k]).strip()
    return "ea"


def _normalize_schedule_unit(unit_raw: str) -> str:
    u = (unit_raw or "ea").lower().strip().replace(".", "")
    if u in ("sf", "sqft", "sq ft", "s f", "square feet", "square foot"):
        return "sq_ft"
    if u in ("lf", "lnft", "ln ft", "lin ft", "linear feet", "linear foot"):
        return "lf"
    if u in ("cy", "cubic yards", "cubic yard"):
        return "cy"
    if u in ("ea", "each", "no", "nos", "qty", "pc", "pcs"):
        return "ea"
    return u


def _suppress_profile_duplicates(estimates: List[dict]) -> List[dict]:
    """When a takeoff legend/schedule row supplies an item type, drop room-profile duplicates."""
    schedule_types = {
        e["item_type"]
        for e in estimates
        if e.get("qty_source") == "schedule" and e.get("item_type") in ESTIMATION_TABLES
    }
    if not schedule_types:
        return estimates

    _AREA_TYPES = {
        "sealed_concrete", "exposed_structure", "internal_tilt_up_wall", "tilt_up_wall",
        "cmu_wall", "flooring", "ceiling_grid",
    }
    out: List[dict] = []
    for e in estimates:
        if e.get("qty_source") == "schedule":
            out.append(e)
            continue
        itype = e.get("item_type", "")
        if itype == "flooring" and schedule_types.intersection(_AREA_TYPES):
            continue
        if itype in schedule_types and itype in _AREA_TYPES:
            continue
        out.append(e)
    return out


def _calculate_from_schedule(sched: dict, sheet_name: str) -> List[dict]:
    """Each row of a schedule becomes a counted item ONLY when there's a real quantity.
    Skip rows that just define a type/spec without a count — those belong in raw_items.csv,
    not calculations.csv (no math to do)."""
    if not _schedule_is_takeoff(sched):
        logger.info(f"  Skipping non-takeoff table: {sched.get('name')} ({sched.get('table_purpose')})")
        return []

    results = []
    sched_name = sched.get("name", "Schedule")
    rows = sched.get("rows", [])

    # A "takeoff_legend" is an authoritative, pre-computed take-off (e.g. parsed
    # from the estimator's companion take-off export). Its quantities are FINAL —
    # the estimator already accounted for waste and conversions — so we must pass
    # them through verbatim and never re-apply waste factors or unit formulas.
    authoritative = sched.get("table_purpose") == "takeoff_legend"

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
        for k in ("QUANTITY", "QTY", "Qty", "COUNT", "Count", "AMOUNT", "Amount"):
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

        row_unit = _normalize_schedule_unit(_row_schedule_unit(row))
        item_type = _classify_item(desc or sched_name, row_unit, "schedule")
        if item_type == "general":
            item_type = _classify_item(sched_name, row_unit, "schedule")
        # Area-unit rows must not become stud counts or slab CY from generic tokens
        if row_unit == "sq_ft" and item_type in ("wall_framing", "concrete_slab"):
            retry = _classify_item(desc or sched_name, "sq_ft", "schedule")
            if retry not in ("general", "wall_framing", "concrete_slab"):
                item_type = retry
            elif re.search(r"\bcmu\b|masonry|block\s*wall", (desc or "").lower()):
                item_type = "cmu_wall"
            elif re.search(r"sealed|polished|exposed\s*struct", (desc or "").lower()):
                item_type = "sealed_concrete" if "sealed" in (desc or "").lower() else "exposed_structure"
        full_desc = desc or sched_name
        if mark and mark not in full_desc:
            full_desc = f"{mark} - {full_desc}"
        row_text = " | ".join(f"{k}={v}" for k, v in row.items() if v)

        if authoritative:
            # Authoritative legend: use the printed quantity/unit verbatim. Keep the
            # legend's original unit token (e.g. "SF", "LF") rather than the
            # internal normalized form so the output mirrors the estimator's sheet.
            legend_unit = (row.get("UNIT") or row.get("Unit") or "").strip().upper() or row_unit
            results.append({
                "item_type": item_type if item_type in ESTIMATION_TABLES else "schedule_item",
                "description": full_desc,
                "raw_value": qty_source,
                "raw_unit": legend_unit,
                "quantity": round(qty, 2),
                "unit": legend_unit,
                "waste_factor_applied": 1.0,
                "formula": f"authoritative takeoff legend ({qty_source} {legend_unit})",
                "qty_source": "companion_takeoff_legend",
                "source_sheet": sheet_name,
                "source_location": f"{sched_name}{' row ' + mark if mark else ''}",
                "source_raw": row_text,
                "table_used": "takeoff_legend",
                "specification": row.get("SPECIFICATION") or row.get("SPEC") or "",
            })
        elif item_type in ESTIMATION_TABLES:
            calc_qty, calc_unit, formula_out = _apply_formula(
                item_type, qty, row_unit, qty_source
            )
            if formula_out in ("no formula", "", None):
                calc_qty, calc_unit = qty, row_unit
                formula_out = f"qty from schedule ({qty_source})"
            table = ESTIMATION_TABLES.get(item_type, {})
            results.append({
                "item_type": item_type,
                "description": full_desc,
                "raw_value": qty_source,
                "raw_unit": row_unit,
                "quantity": round(calc_qty, 2) if isinstance(calc_qty, (int, float)) else calc_qty,
                "unit": calc_unit,
                "waste_factor_applied": table.get("waste_factor", 1.0),
                "formula": formula_out,
                "qty_source": "schedule",
                "source_sheet": sheet_name,
                "source_location": f"{sched_name}{' row ' + mark if mark else ''}",
                "source_raw": row_text,
                "table_used": item_type,
                "specification": row.get("SPECIFICATION") or row.get("SPEC") or "",
            })
        else:
            out_unit = "ea" if row_unit == "ea" else row_unit
            results.append({
                "item_type": "schedule_item",
                "description": full_desc,
                "raw_value": qty_source,
                "raw_unit": row_unit,
                "quantity": qty,
                "unit": out_unit,
                "waste_factor_applied": 1.0,
                "formula": f"count from schedule (qty column = {qty_source})",
                "qty_source": "schedule",
                "source_sheet": sheet_name,
                "source_location": f"{sched_name}{' row ' + mark if mark else ''}",
                "source_raw": row_text,
                "table_used": "none",
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

    if item_type in ("storm_pipe", "trench_drain", "guard_rail", "hand_rail", "striping",
                      "gas_pipe", "lintel", "duct_lf", "conduit_lf"):
        wf = table.get("waste_factor", 1.0)
        return value * wf, "lf", f"{value:.0f} lf × {wf} = {value * wf:.0f} lf"

    if item_type in (
        "catch_basin", "manhole", "headwall", "bollard",
        "columns", "stairs", "ladder", "lift", "mobilization",
    ):
        return value, "ea", "count"

    if item_type in ("concrete_pavement", "asphalt", "tilt_up_wall", "exposed_structure",
                      "exterior_soffit", "sealed_concrete", "cmu_wall", "internal_tilt_up_wall",
                      "canopy", "eifs", "cmu_paint"):
        wf = table.get("waste_factor", 1.0)
        return value * wf, "sq_ft", f"{value:.0f} sf × {wf} = {value * wf:.0f} sf"

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

    # Reject elevation/invert survey data (not takeoff quantities)
    if re.search(r'(?:GL|INV|EL|ELEV|INV\s*IN|INV\s*OUT)\s*[=:]\s*\d', s, re.IGNORECASE):
        return None
    # Reject pure percentage (pipe slope)
    if re.match(r'^\d+\.?\d*\s*%$', s.strip()):
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
    # Tokenize on separators (hyphens in "Columns-H-35'" must not become one token)
    words = set(re.findall(r"[a-z][a-z0-9]+", re.sub(r"[-_/']+", " ", d)))

    # Pass 1: multi-word phrases (e.g. "sealed concrete" before bare "concrete" → slab CY)
    for table_key, table in ESTIMATION_TABLES.items():
        for kw in table.get("keywords", []):
            kw_l = kw.lower()
            if " " in kw_l and kw_l in d and not _is_substring_match(kw_l, d):
                return table_key

    # Pass 2: single-token keywords
    for table_key, table in ESTIMATION_TABLES.items():
        for kw in table.get("keywords", []):
            kw_l = kw.lower()
            if " " in kw_l:
                continue
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


def _detect_project_type(all_pages: List[dict]) -> str:
    """Heuristic: infer building type from sheet titles and notes across all pages.

    Uses keyword scoring per project category (RESEARCH §11.4 table).
    Returns the winning type key, or "auto" when no category scores above zero.
    """
    _KEYWORD_SCORES: Dict[str, List[str]] = {
        "industrial": [
            "warehouse", "distribution", "industrial", "manufacturing",
            "tilt-up", "tilt up", "sealed concrete", "dock door",
        ],
        "retail": [
            "retail", "store", "showroom", "merchandise", "sales floor",
            "storefront", "shopping",
            # omit bare "tenant" — matches "Tenant Space" on industrial warehouses
        ],
        "office": [
            "office", "tenant improvement", r"\bti\b", "corporate",
            "suites", "open plan",
        ],
        "civil": [
            "site plan", "grading", "utility plan", "civil",
            "storm sewer", "paving plan", "grading plan",
        ],
        "residential": [
            "residence", "dwelling", "single family", "unit plan",
            "townhouse", "apartment",
        ],
        "institutional": [
            "school", "hospital", "clinic", "government",
            "civic", "university", "library",
        ],
    }

    scores: Dict[str, int] = {k: 0 for k in _KEYWORD_SCORES}
    for page in all_pages:
        title = (page.get("sheet_title") or page.get("_source_sheet") or page.get("_sheet_name") or "").lower()
        notes = (page.get("notes") or "").lower()
        sheet_type = (page.get("sheet_type") or page.get("_sheet_type") or "").lower()
        combined = f"{title} {notes} {sheet_type}"
        for ptype, keywords in _KEYWORD_SCORES.items():
            for kw in keywords:
                if re.search(kw, combined, re.IGNORECASE):
                    scores[ptype] += 1
        # Content signals: large sealed-concrete / tilt-up rooms → industrial
        for room in page.get("rooms") or []:
            if not isinstance(room, dict):
                continue
            room_text = " ".join(
                filter(None, [
                    room.get("notes") or "",
                    " ".join(room.get("materials") or []),
                    room.get("name") or "",
                ])
            ).lower()
            if re.search(
                r"sealed\s*concrete|tilt[- ]?up|warehouse|distribution|manufacturing",
                room_text,
                re.IGNORECASE,
            ):
                scores["industrial"] += 2
        # Takeoff legend / schedule rows (authoritative on industrial warehouses)
        for sched in page.get("schedules") or []:
            if not isinstance(sched, dict) or not _schedule_is_takeoff(sched):
                continue
            for row in sched.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                row_text = " ".join(str(v) for v in row.values() if v).lower()
                if re.search(
                    r"sealed\s*concrete|tilt[- ]?up|bollard|mobilization|warehouse|"
                    r"distribution|dock\s*door|cmu\s*wall|exposed\s*structure",
                    row_text,
                    re.IGNORECASE,
                ):
                    scores["industrial"] += 3

    best_score = max(scores.values())
    if best_score == 0:
        return "auto"

    winners = [k for k, v in scores.items() if v == best_score]
    if len(winners) > 1:
        if "industrial" in winners and scores["industrial"] >= 3:
            return "industrial"
        return "mixed_use"
    return winners[0]
