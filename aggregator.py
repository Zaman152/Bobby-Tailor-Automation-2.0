"""
Consolidate per-sheet takeoff items into project-level totals (StackCT summary format).
"""
import logging
import re
from collections import defaultdict
from typing import Dict, List

logger = logging.getLogger(__name__)

ITEM_NAME_MAP = [
    (r"bollard", "Bollards", "EA"),
    (r"column.*h.*\d+", "Columns", "EA"),
    (r"dumpster.*enclos", "Dumpster Enclosure", "EA"),
    (r"guard.*rail", "Guard Rail", "LF"),
    (r"hand.*rail", "Hand Rail", "LF"),
    (r"stair", "Stairs", "EA"),
    (r"strip", "Striping", "LF"),
    (r"mobiliz", "Mobilization", "EA"),
    (r"lift|elevator", "Lift", "EA"),
    (r"exposed.*struct", "Exposed Structure", "SF"),
    (r"exterior.*soffit", "Exterior Soffit", "SF"),
    (r"tilt.*up.*wall|ext.*wall", "Exterior Tilt Up Wall", "SF"),
    (r"interior.*concrete.*wall", "Interior Concrete Walls", "SF"),
    (r"gauge.*metal|metal.*gauge", "Gauge Metal", "EA"),
    (r"catch basin|bb ci", "Catch Basins", "EA"),
    (r"trench drain", "Trench Drain", "LF"),
    (r"gas.*pip|gas\s*pipe|black\s*steel.*pip|csst.*pip", "Gas Piping", "LF"),
    (r"(\d+).*lf.*pvc|pvc.*(\d+)|storm pipe|storm sewer", "Storm Pipe", "LF"),
    (r"sealed.*concrete|polished.*concrete|slab.on.grade", "Sealed Concrete", "SF"),
    (r"manhole", "Manholes", "EA"),
    (r"flooring|floor tile|lvt|vct|carpet", "Flooring", "SF"),
    (r"drywall|gwb|gypsum", "Drywall", "sheets"),
    (r"paint", "Paint", "gallons"),
    (r"ceiling.*tile|act|t-bar", "Ceiling Grid", "SF"),
    (r"door(?!.*frame)", "Doors", "EA"),
    (r"window|glazing", "Windows", "EA"),
    (r"insulation|batt|r-\d+", "Insulation", "SF"),
    (r"panel|mcc|switchboard", "Electrical Panels", "EA"),
    (r"light.*fix|fixture.*light|led", "Lighting Fixtures", "EA"),
    (r"receptacle|outlet", "Receptacles", "EA"),
    (r"exit sign", "Exit Signs", "EA"),
    (r"fan coil|fcu", "Fan Coil Units", "EA"),
    (r"air handler|ahu", "Air Handling Units", "EA"),
    (r"exhaust fan", "Exhaust Fans", "EA"),
    (r"headwall|flared end", "Headwall", "EA"),
]


def _extract_spec_for_name(canonical: str, description: str) -> str:
    if "Column" in canonical:
        m = re.search(r"h[-\s]*(\d+\'?\s*\d*\"?)", description, re.IGNORECASE)
        if m:
            return f"H-{m.group(1)}"
    if "Pipe" in canonical:
        m = re.search(r'(\d+)\s*(?:in|")', description, re.IGNORECASE)
        if m:
            return f'{m.group(1)}"'
    return ""


def normalize_item_name(description: str, item_type: str, unit: str) -> tuple:
    d = (description or "").lower()
    for pattern, name, default_unit in ITEM_NAME_MAP:
        if re.search(pattern, d, re.IGNORECASE):
            spec_match = _extract_spec_for_name(name, d)
            if spec_match:
                name = f"{name}-{spec_match}"
            return name, default_unit
    canonical = item_type.replace("_", " ").title() if item_type else (description or "")[:40]
    return canonical, unit or "EA"


def aggregate_takeoff(calculated_items: List[Dict]) -> List[Dict]:
    """Consolidate per-sheet items into project-level totals."""
    buckets: Dict[str, Dict] = defaultdict(lambda: {
        "quantity": 0.0,
        "unit": "",
        "source_sheets": set(),
        "source_rows": [],
        "item_type": "",
    })

    for item in calculated_items:
        desc = item.get("description", "")
        itype = item.get("item_type", "")
        unit = item.get("calculated_unit") or item.get("unit", "")
        qty_raw = item.get("calculated_quantity") or item.get("quantity", 0)
        try:
            qty = float(qty_raw)
        except (TypeError, ValueError):
            continue

        canonical_name, canonical_unit = normalize_item_name(desc, itype, unit)
        bucket = buckets[canonical_name]
        bucket["quantity"] += qty
        bucket["unit"] = canonical_unit or unit
        bucket["source_sheets"].add(item.get("source_sheet", ""))
        bucket["item_type"] = itype
        bucket["source_rows"].append({
            "sheet": item.get("source_sheet"),
            "qty": qty,
            "description": desc,
            "formula": item.get("formula_applied") or item.get("formula", ""),
        })

    result = []
    for name in sorted(buckets.keys()):
        b = buckets[name]
        qty = b["quantity"]
        qty_fmt = f"{qty:,.0f}" if qty == int(qty) else f"{qty:,.1f}"
        result.append({
            "item": name,
            "quantity": qty,
            "quantity_fmt": qty_fmt,
            "unit": (b["unit"] or "").upper(),
            "source_sheets": sorted(b["source_sheets"] - {""}),
            "item_type": b["item_type"],
            "line_count": len(b["source_rows"]),
            "detail": b["source_rows"],
        })
    return result
