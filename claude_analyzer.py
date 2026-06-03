import base64
import json
import logging
import re
from pathlib import Path
from typing import Optional, Tuple
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MODEL_SCHEDULES

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PRICING = {
    "claude-haiku-4-5":   {"in": 1.0,  "out": 5.0},
    "claude-sonnet-4-6":  {"in": 3.0,  "out": 15.0},
    "claude-opus-4-7":    {"in": 5.0,  "out": 25.0},
}


def _pick_model(
    sheet_name: str,
    pass_type: str = "measure",
    sheet_type: Optional[str] = None,
) -> str:
    """Choose the best Claude model for a given pass type and sheet context.

    Priority:
      1. sheet_pass_matrix.MODEL_ROUTING lookup when sheet_type is provided
         (explicit per-(sheet_type, pass_type) Sonnet overrides).
      2. Sheet-name keyword heuristic — MEP codes and schedule-named sheets
         route to CLAUDE_MODEL_SCHEDULES.
      3. Default CLAUDE_MODEL (Haiku) for everything else.

    The sheet_pass_matrix import is deferred inside the function to avoid a
    circular dependency (sheet_pass_matrix imports _pick_model at module level).
    """
    # 1. Routing table lookup when sheet_type is known
    if sheet_type:
        try:
            from sheet_pass_matrix import MODEL_ROUTING  # deferred to avoid circular import
            routed = MODEL_ROUTING.get((sheet_type, pass_type))
            if routed:
                return routed
        except ImportError:
            pass

    # 2. Name-based heuristic (backward-compatible fallback)
    if not sheet_name:
        return CLAUDE_MODEL
    upper = sheet_name.upper()
    schedule_keywords = ("SCHEDULE", "PANEL", "RISER", "EQUIPMENT", "FIXTURE")
    if any(kw in upper for kw in schedule_keywords):
        return CLAUDE_MODEL_SCHEDULES
    # MEP sheet codes: E3.1 (electrical), M0.3 (mechanical), P1.0 (plumbing)
    if re.match(r"^[EMP]\d", upper):
        return CLAUDE_MODEL_SCHEDULES
    return CLAUDE_MODEL

EXTRACTION_PROMPT = """You are a professional quantity surveyor analyzing a construction drawing for take-off estimation.

YOUR PRIMARY MISSION: Extract EVERY quantity, dimension, count, and table that feeds into a bid estimate.

Return ONLY valid JSON. No markdown, no commentary, no code fences.

{
  "sheet_type": "floor_plan | elevation | section | detail | civil_site | schedule | panel_schedule | specification_detail | title_sheet | other",
  "sheet_title": "exact title from title block",
  "scale": "scale shown or NTS",
  "drawing_discipline": "architectural | civil | structural | mechanical | electrical | plumbing | landscape | survey",
  "measurements": [
    {
      "description": "clear description",
      "value": "EXACT numeric value only (strip ± but flag approximate)",
      "unit": "lf | sf | cy | ea | in | ft | amps | kva | cfm | gal | ton",
      "approximate": false,
      "location": "where on drawing",
      "raw_text": "exact text as shown"
    }
  ],
  "components": [
    {
      "name": "descriptive name including type and size",
      "quantity": "numeric count or null — NEVER fabricate 1",
      "unit": "ea | lf | sf",
      "specification": "spec data; GL/INV elevations for structures go here as text",
      "location": "where on drawing"
    }
  ],
  "rooms": [
    {
      "name": "room name and number",
      "area": "numeric sq ft or null",
      "dimensions": "L x W if shown",
      "notes": "callouts"
    }
  ],
  "schedules": [
    {
      "name": "schedule name",
      "table_purpose": "takeoff_schedule | specification_reference | general_notes | finish_schedule | room_schedule",
      "schedule_type": "panel | door | window | equipment | finish | pipe_sizing | manufacturer_catalog | notes | other",
      "use_for_takeoff": true,
      "lookup_key": "column name for spec tables e.g. PIPE SIZE",
      "description": "brief description",
      "header_info": "header above table",
      "columns": ["COL1", "COL2"],
      "rows": [{"COL1": "val"}],
      "totals": "footer totals if any"
    }
  ],
  "cross_references": [
    {
      "ref_number": "number/letter in bubble",
      "ref_sheet": "sheet code in box e.g. C-4",
      "ref_type": "detail | section | elevation | matchline",
      "item_described": "what the bubble points to",
      "context": "why it matters for takeoff",
      "on_this_sheet_data": {}
    }
  ],
  "pipe_runs": [
    {
      "length_lf": 25,
      "diameter_in": 12,
      "material": "PVC",
      "schedule_or_class": "SCH 40",
      "slope_pct": 4.81,
      "from_structure": "upstream ID",
      "to_structure": "downstream ID",
      "raw_text": "full annotation"
    }
  ],
  "civil_structures": [
    {
      "id": "BB CI#2",
      "type": "catch_basin | manhole | headwall | junction_box | cleanout | other",
      "quantity": 1,
      "detail_ref_number": "17",
      "detail_ref_sheet": "C-4",
      "ground_level": null,
      "invert_in": null,
      "invert_out": null,
      "specification": "construction notes"
    }
  ],
  "materials": [{"type": "", "specification": "", "quantity": null, "unit": ""}],
  "confidence": "high | medium | low",
  "notes": "observations"
}

RULES:
1. TABLE CLASSIFICATION: takeoff_schedule = rows with real quantities to install. specification_reference = manufacturer catalogs, pipe sizing charts — set use_for_takeoff: false. general_notes = numbered notes only.
2. CROSS-REFERENCES: Every detail bubble (circle number + sheet box) goes in cross_references[].
3. PIPE RUNS: "25 LF - 12\\"Ø SCH 40 PVC @ 4.81%" → pipe_runs[] with length_lf, diameter_in, slope_pct — NOT in measurements[].
4. CIVIL STRUCTURES: Catch basins/manholes with GL/INV → civil_structures[], NOT measurements[].
5. APPROXIMATE: ± prefix → set approximate: true on measurement.
6. EXCLUDE from measurements[]: scale, temperatures, GL/INV/EL/ELEV values, slope % alone, SEE SHEET refs without qty.
7. NEVER fabricate quantities. Read EVERY schedule row including spares."""


COUNT_PROMPT = """You are a professional quantity surveyor counting discrete construction items on this drawing.

YOUR MISSION: Count every physical object that exists as an individual unit (EA) to be installed or constructed.

Return ONLY valid JSON. No markdown, no commentary, no code fences.

{
  "sheet_type": "floor_plan | elevation | section | detail | civil_site | schedule | roof_plan | mep_plan | other",
  "has_schedules": false,
  "components": [
    {
      "name": "descriptive name including type and size",
      "quantity": null,
      "unit": "ea",
      "method": "direct | grid | note",
      "confidence": "high | medium | low",
      "location": "where on drawing",
      "notes": "any relevant observation"
    }
  ]
}

COUNTING RULES (apply to ALL symbol types):
1. COUNT physical objects depicted as icons or symbols on the plan: bollards, columns, catch
   basins, manholes, drains, luminaires, fixtures, trees, fire hydrants, parking stalls,
   hangers, ladders, lifts, equipment tags, doors, windows, vents, RTUs, VAV boxes, and
   any other discrete installed element.
2. DIMENSION LINE RULE: Any number adjacent to a dimension line (with arrows or extension
   lines) is a DIMENSION, not a count. "6'-0\" TYP", "24\" O.C.", "3'-6\" CLEAR" are
   spacing annotations — never EA quantities.
3. SPACING ANNOTATION RULE: Labels containing "TYP", "O.C.", "MAX", "MIN", or "EQ" after a
   number describe spacing or clearance. They are not object counts.
4. GRID LABEL RULE: Grid axis labels (1, 2, 3 / A, B, C) are reference coordinates.
   They are not counts of anything.
5. DETAIL SHEET RULE: When a detail sheet shows a TYPICAL symbol with spacing dimensions,
   count ZERO instances of that symbol — detail sheets show geometry, not project quantity.
6. TYPICAL NOTE RULE: If an item appears only with a note like "TYP @ ALL COLUMNS" or
   "SEE SCHEDULE", set quantity=null and confidence=low. Do not guess a total count.
7. GRID COUNT METHOD: For regularly gridded objects (structural columns, parking stalls),
   count all visible grid intersections with the symbol. Use method="grid" and record
   the grid axis description (e.g., "A-G x 1-14, 6x4=24").
8. UNCERTAINTY RULE: When you cannot reliably count an item, set quantity=null and
   confidence=low. NEVER fabricate a quantity.

EXCLUSIONS — do NOT extract in this pass:
- Dimension callout numbers (feet, inches, angles, slopes)
- Elevation labels (EL. 100'-0", GL, INV, RIM)
- Schedule row numbers (1, 2, 3 in a table)
- Linear or area quantities (LF, SF, CY)
- Text keynotes or note numbers standing alone"""


SCHEDULE_PROMPT = """You are a professional quantity surveyor extracting schedule and table data from a construction drawing.

YOUR MISSION: Extract ONLY the schedules and tables visible on this drawing.
Ignore plan elements, dimensions, notes paragraphs, and non-tabular content entirely.

Return ONLY valid JSON. No markdown, no commentary, no code fences.

{
  "schedules": [
    {
      "name": "schedule name as shown on drawing",
      "table_purpose": "takeoff_schedule | specification_reference | general_notes | finish_schedule | room_schedule",
      "schedule_type": "door | window | equipment | finish | panel | pipe_sizing | plumbing_fixture | hardware | other",
      "use_for_takeoff": true,
      "description": "brief description of what this table contains",
      "columns": ["MARK", "QTY", "TYPE", "MATERIAL", "SIZE", "NOTES"],
      "rows": [
        {"MARK": "D-1", "QTY": "4", "TYPE": "HM", "MATERIAL": "Hollow Metal", "SIZE": "3'-0\" x 7'-0\""}
      ],
      "totals": "footer totals row if present, else null"
    }
  ]
}

EXTRACTION RULES:
1. QTY COLUMN: Read QTY values exactly as printed. Do not calculate, infer, or sum quantities.
   Set use_for_takeoff=true ONLY when a QTY or COUNT column exists with numeric values.
2. ROW READING: Read every visible row completely. Do NOT skip rows, invent rows, or merge rows.
   Stop at the last visible row — do not extrapolate rows that extend off-page.
3. MATERIAL CLASSIFICATION: Classify rows using the material or type column values:
   - Door materials: HM (hollow metal), WD (wood), AL (aluminum), GL (glass), FRP
   - Window materials: AL (aluminum), VL (vinyl), WD (wood), FIX (fixed)
   - Pipe materials: PVC, HDPE, DIP, CU (copper), SS (stainless), GS (galvanized steel)
4. TABLE PURPOSE RULES:
   - takeoff_schedule: rows with quantities of items to install (doors, windows, equipment)
   - specification_reference: manufacturer catalogs, pipe sizing charts, performance tables
     → always set use_for_takeoff=false
   - general_notes: numbered notes list with no quantity column → use_for_takeoff=false
5. FOCUS: Return only the schedules[] array. Do NOT extract measurements[], components[],
   rooms[], or pipe_runs[] in this pass. If no table is visible, return {"schedules": []}."""


def encode_image(filepath: str) -> Tuple[str, str]:
    """Encode image to base64 and detect media type.
    Automatically compresses to stay under the Anthropic 5 MB base64 limit
    while preserving as much resolution as possible for table reading."""
    path = Path(filepath)
    ext = path.suffix.lower()
    media_type_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(ext, "image/jpeg")

    with open(filepath, "rb") as f:
        raw = f.read()

    # Anthropic limit: base64 ≤ 5 MB (≈ 3.75 MB raw before base64 inflation)
    # If we're under that, send as-is to preserve maximum quality.
    raw_limit = int(3.6 * 1024 * 1024)
    if len(raw) <= raw_limit:
        return base64.standard_b64encode(raw).decode("utf-8"), media_type

    # Otherwise convert PNG → JPEG quality 90 with iterative resizing.
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Iteratively reduce quality/size until under the limit
        quality = 92
        max_dim = 3200  # initial max longest side
        for _ in range(8):
            # Resize if needed
            w, h = img.size
            scale = min(1.0, max_dim / max(w, h))
            if scale < 1.0:
                resized = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            else:
                resized = img
            buf = io.BytesIO()
            resized.save(buf, "JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= raw_limit:
                logger.info(f"  Compressed image: {len(raw):,} → {len(data):,} bytes "
                            f"(quality={quality}, max_dim={max_dim})")
                return base64.standard_b64encode(data).decode("utf-8"), "image/jpeg"
            # Try smaller
            quality = max(60, quality - 8)
            max_dim = max(1600, max_dim - 400)

        # Last resort
        logger.warning(f"Could not compress below limit, sending {len(data):,} bytes")
        return base64.standard_b64encode(data).decode("utf-8"), "image/jpeg"
    except ImportError:
        logger.warning("Pillow not installed — sending uncompressed (may fail)")
        return base64.standard_b64encode(raw).decode("utf-8"), media_type


def analyze_drawing(
    screenshot_path: str,
    sheet_name: str = "",
    pass_type: str = "measure",
    model_override: Optional[str] = None,
) -> dict:
    """Send a drawing screenshot to Claude for vision-based extraction.

    Args:
        screenshot_path: Absolute path to the sheet image file.
        sheet_name:      Sheet identifier used for logging and model selection.
        pass_type:       Which extraction pass to run:
                           "measure"  — full EXTRACTION_PROMPT (default; backward compat)
                           "count"    — COUNT_PROMPT (discrete EA symbols only)
                           "schedule" — SCHEDULE_PROMPT (tables/schedules only)
        model_override:  When set, use this model slug directly; bypasses _pick_model.

    Returns:
        Structured extraction dict.  On error, returns a dict with "error" key.
    """
    logger.info(f"Analyzing drawing: {sheet_name or screenshot_path} [pass={pass_type}]")

    # Select system prompt for this pass
    if pass_type == "count":
        system_prompt = COUNT_PROMPT
    elif pass_type == "schedule":
        system_prompt = SCHEDULE_PROMPT
    else:
        system_prompt = EXTRACTION_PROMPT  # "measure" or unknown → full extraction

    try:
        image_data, media_type = encode_image(screenshot_path)

        # Model selection: explicit override wins; otherwise routing heuristic
        if model_override:
            model = model_override
        else:
            model = _pick_model(sheet_name, pass_type)
        if model != CLAUDE_MODEL:
            logger.info(f"  Using {model} for sheet (pass={pass_type})")

        # System prompt with cache_control: cached after first call per-prompt,
        # saving ~90% on repeated drawing analyses.
        response = client.messages.create(
            model=model,
            max_tokens=8000,  # tables/panel schedules can produce a lot of JSON
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Sheet name: {sheet_name}\n\nAnalyze this drawing and return the JSON."
                                if sheet_name
                                else "Analyze this drawing and return the JSON."
                            ),
                        }
                    ],
                }
            ],
        )

        # Capture usage and calculate cost
        usage = response.usage
        p = PRICING.get(model, {"in": 3.0, "out": 15.0})
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cost_usd = (input_tokens * p["in"] + output_tokens * p["out"]) / 1_000_000

        raw_text = response.content[0].text.strip()

        # Strip markdown if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        extracted = json.loads(raw_text)
        extracted["_tokens_in"] = input_tokens
        extracted["_tokens_out"] = output_tokens
        extracted["_cost_usd"] = round(cost_usd, 6)
        extracted["_model_used"] = model
        extracted["_pass_type"] = pass_type
        extracted["_source_sheet"] = sheet_name
        extracted["_screenshot"] = screenshot_path
        logger.info(
            f"  [{pass_type}] Extracted {len(extracted.get('measurements', []))} measurements, "
            f"{len(extracted.get('components', []))} components "
            f"[{input_tokens} in / {output_tokens} out tokens, ${cost_usd:.6f}]"
        )
        return extracted

    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {e}")
        return {
            "error": "invalid_json",
            "raw": raw_text,
            "_pass_type": pass_type,
            "_source_sheet": sheet_name,
            "_tokens_in": input_tokens,
            "_tokens_out": output_tokens,
            "_cost_usd": round(cost_usd, 6),
            "_model_used": model,
        }
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return {
            "error": str(e),
            "_pass_type": pass_type,
            "_source_sheet": sheet_name,
            "_tokens_in": 0,
            "_tokens_out": 0,
            "_cost_usd": 0,
            "_model_used": "",
        }


def merge_passes(
    count_result: dict,
    measure_result: dict,
    schedule_result: Optional[dict] = None,
) -> dict:
    """Merge multi-pass extraction results into a single unified dict.

    Merge strategy:
    - ``measure_result`` is the base (SF/LF quantities, pipe_runs, rooms,
      measurements, lintel_runs — all area/linear data comes from here).
    - ``count_result`` components are merged in, with high-confidence EA counts
      preferred over measure-pass nulls for the same component.
    - ``schedule_result`` replaces the ``schedules[]`` list when present.
    - Deduplication is by normalised component name (case-insensitive strip).
      Duplicate EA counts are never summed — count-pass wins on confidence.

    This is the canonical implementation.  ``takeoff_pipeline.merge_passes``
    delegates to this function so both entry points remain in sync.

    Args:
        count_result:    Extraction dict from the "count" pass.
        measure_result:  Extraction dict from the "measure" pass (may be empty
                         dict ``{}`` when only a count pass was run).
        schedule_result: Extraction dict from the "schedule" pass, or None.

    Returns:
        Merged extraction dict with deduplicated components.
    """
    merged: dict = dict(measure_result)

    # Index measure-pass components by normalised name for O(1) dedup lookups
    seen: dict[str, dict] = {
        c["name"].strip().lower(): c
        for c in merged.get("components", [])
        if isinstance(c, dict) and c.get("name")
    }

    for c in count_result.get("components", []):
        if not isinstance(c, dict) or not c.get("name"):
            continue
        key = c["name"].strip().lower()
        if key not in seen:
            # New EA component from count pass — append it
            merged.setdefault("components", []).append(c)
            seen[key] = c
        else:
            existing = seen[key]
            # Upgrade quantity when count-pass is high-confidence and measure-pass is null
            if c.get("confidence") == "high" and existing.get("quantity") is None:
                existing["quantity"] = c["quantity"]
                existing["_count_pass_upgrade"] = True

    # Schedule pass replaces schedules[] when present and non-empty
    if schedule_result and schedule_result.get("schedules"):
        merged["schedules"] = schedule_result["schedules"]

    return merged


def make_navigation_decision(screenshot_path: str, current_state: dict) -> dict:
    """
    Ask Claude to make a navigation decision based on current screen state.
    Used for handling unexpected UI states.
    """
    image_data, media_type = encode_image(screenshot_path)

    prompt = f"""You are controlling a construction estimation software (STACK CT).
Current state: {json.dumps(current_state)}

Look at this screenshot and tell me what action to take next.
Return JSON only:
{{
  "action": "click | wait | navigate | skip",
  "target": "description of element to click or URL to navigate to",
  "reason": "brief explanation",
  "is_drawing_loaded": true/false,
  "has_error": true/false
}}"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": prompt}
            ]
        }]
    )

    try:
        return json.loads(response.content[0].text.strip())
    except Exception:
        return {"action": "wait", "reason": "Could not parse response"}
