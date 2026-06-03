"""
Consolidate per-sheet takeoff items into project-level totals (StackCT summary format).
"""
import logging
import re
from collections import defaultdict
from typing import Dict, List

logger = logging.getLogger(__name__)

ITEM_NAME_MAP = [
    # ── Civil / Site ──────────────────────────────────────────────────────────
    (r"bollard", "Bollards", "EA"),
    (r"catch basin|bb ci|drop inlet|curb inlet|storm inlet", "Catch Basins", "EA"),
    (r"manhole|\bmh\b|access structure", "Manholes", "EA"),
    (r"headwall|flared end|end section|\bfes\b|wingwall", "Headwall", "EA"),
    (r"trench drain|channel drain|slot drain|linear drain", "Trench Drain", "LF"),
    (r"gas.*pip|gas\s*pipe|black\s*steel.*pip|csst.*pip|gas\s*line", "Gas Piping", "LF"),
    # Conduit/duct before storm pipe to prevent PVC conduit matching \bpvc\b
    (r"\bconduit\b|\bemt\b|wireway|cable.*tray|raceway\b", "Conduit LF", "LF"),
    (r"duct.*lf|ductwork|\bduct\b(?!.*liner)", "Duct LF", "LF"),
    # Storm pipe — match PVC/HDPE/RCP only in piping context; conduit must be excluded above
    (r"pvc.*pipe|pvc.*sch|pvc.*sewer|\bhdpe\b|\brcp\b|\bdip\b|storm pipe|storm sewer|culvert|sanitary sewer", "Storm Pipe", "LF"),
    (r"guard.*rail|guardrail|barrier.*rail|w.?beam", "Guard Rail", "LF"),
    (r"hand.*rail|handrail|stair.*rail|pipe.*rail", "Hand Rail", "LF"),
    (r"strip|pavement.*mark|lane.*mark", "Striping", "LF"),
    (r"curb.*gutter|curb.*and.*gutter|\bcurb\b", "Curb & Gutter", "LF"),
    (r"\basphalt\b|\bhma\b|blacktop", "Asphalt", "SF"),
    # Concrete pavement — match common abbreviations and context phrases
    (r"concrete.*pavement|\bpcc\b|\bflatwork\b|concrete.*drive|concrete.*walk|concrete.*sidewalk", "Concrete Pavement", "SF"),
    (r"dumpster.*enclos", "Dumpster Enclosure", "EA"),

    # ── Structure ─────────────────────────────────────────────────────────────
    (r"column.*h.*\d+", "Columns", "EA"),
    (r"\bcolumn\b(?!.*h.*\d)", "Columns", "EA"),
    (r"sealed.*concrete|polished.*concrete|slab.on.grade|\bsog\b|concrete.*floor", "Sealed Concrete", "SF"),
    (r"exposed.*struct|exposed.*deck|open.*web.*joist|bar.*joist", "Exposed Structure", "SF"),
    (r"exterior.*soffit|canopy.*soffit", "Exterior Soffit", "SF"),
    # Tilt-up: interior variants before exterior catch-all
    (r"internal.*tilt|interior.*tilt|int.*tilt.*up", "Interior Tilt Up Walls", "SF"),
    (r"tilt.*up.*wall|tiltup.*wall|precast.*panel|ext.*tilt", "Exterior Tilt Up Wall", "SF"),
    # CMU paint BEFORE CMU Wall (both match \bcmu\b; paint is more specific)
    (r"cmu.*paint|block.*paint|masonry.*paint|epoxy.*block", "CMU Paint", "gallons"),
    (r"\bcmu\b|masonry.*wall|block.*wall|concrete.*masonry", "CMU Wall", "SF"),
    (r"\blintel\b|steel.*lintel|angle.*lintel", "Lintels", "LF"),
    (r"stair", "Stairs", "EA"),
    (r"\bladder\b", "Ladder", "EA"),
    (r"\blift\b|elevator", "Lift", "EA"),
    (r"mobiliz", "Mobilization", "EA"),

    # ── Architectural ─────────────────────────────────────────────────────────
    (r"flooring|floor tile|\blvt\b|\bvct\b|\bcarpet\b|luxury.*vinyl|ceramic.*tile|porcelain.*tile", "Flooring", "SF"),
    (r"ceiling.*tile|\bact\b|t.bar.*ceil|acoustic.*ceil|lay.in.*ceil", "Ceiling Grid", "SF"),
    (r"drywall|\bgwb\b|gypsum.*board|sheetrock|wallboard", "Drywall", "sheets"),
    (r"\bpaint\b|primer|finish.*coat|epoxy.*floor", "Paint", "gallons"),
    (r"\beifs\b|exterior.*insulation|dryvit|synthetic.*stucco", "EIFS", "SF"),
    (r"\bcanopy\b|metal.*canopy|entrance.*canopy|shade.*canopy", "Canopy", "SF"),
    (r"insulation|\bbatt\b|rigid.*insul|spray.*foam|r-\d+", "Insulation", "SF"),
    # Door type separation — Frame-HM and specific types BEFORE generic door catch-all
    (r"hollow.?metal.*frame|frame.*hollow.?metal|frame.*\bhm\b|\bhm\b.*frame", "Frame-HM", "EA"),
    (r"door.*hollow.?metal|hollow.?metal.*door|hm.*door(?!.*frame)|door.*\bhm\b(?!.*frame)", "Doors-HM", "EA"),
    (r"door.*\bwood\b|\bwood\b.*door|\bwd\b.*door|door.*\bwd\b", "Doors-WD", "EA"),
    (r"door.*alum|alum.*door|\bal\b.*door|door.*\bal\b", "Doors-AL", "EA"),
    # Generic door catch-all — must follow specific types above
    (r"door(?!.*frame)", "Doors", "EA"),
    (r"window|glazing|storefront.*glass", "Windows", "EA"),
    (r"gauge.*metal|metal.*gauge", "Gauge Metal", "EA"),
    (r"interior.*concrete.*wall", "Interior Concrete Walls", "SF"),

    # ── MEP ───────────────────────────────────────────────────────────────────
    (r"panel|mcc\b|switchboard|distribution.*board", "Electrical Panels", "EA"),
    (r"light.*fix|fixture.*light|\bled\b|luminaire", "Lighting Fixtures", "EA"),
    (r"receptacle|outlet\b", "Receptacles", "EA"),
    (r"exit sign", "Exit Signs", "EA"),
    (r"fan coil|\bfcu\b", "Fan Coil Units", "EA"),
    (r"air handler|\bahu\b", "Air Handling Units", "EA"),
    (r"exhaust fan", "Exhaust Fans", "EA"),
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
