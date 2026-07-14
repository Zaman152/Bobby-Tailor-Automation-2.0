import base64
import json
import logging
import re
from pathlib import Path
from typing import Optional, Tuple
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MODEL_SCHEDULES

# Pass prompts relocated to bobbytailor.vision.prompts (21-08). Imported back
# and re-exported here so the root shim (`claude_analyzer`) and the package
# path both keep exposing them (21-01 shim contract; test_extraction_prompt).
from bobbytailor.vision.prompts import (  # noqa: F401  (re-exported)
    COUNT_PROMPT,
    EXTRACTION_PROMPT,
    LEGEND_PROMPT,
    MEASURE_ADDENDUM,
    SCHEDULE_PROMPT,
    SEMANTIC_LABELING_PROMPT,
    SYMBOL_GALLERY_PROMPT,
    VERIFY_RETRY_PROMPT,
    _SCHEDULE_LEGEND_USER_HINT,
)

try:
    from json_repair import repair_json as _repair_json
    _JSON_REPAIR_AVAILABLE = True
except ImportError:
    _JSON_REPAIR_AVAILABLE = False

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# USD per 1M tokens — July 2026 Anthropic price table (21-RESEARCH.md §5).
# Legacy slugs are KEPT so cached reports from older runs still cost out correctly.
PRICING = {
    # Current line-up (verified July 2026)
    "claude-haiku-4-5":   {"in": 1.0,  "out": 5.0},
    # Sonnet 5 price rises to $3/$15 on 2026-09-01 — update then
    "claude-sonnet-5":    {"in": 2.0,  "out": 10.0},
    "claude-opus-4-8":    {"in": 5.0,  "out": 25.0},
    "claude-fable-5":     {"in": 10.0, "out": 50.0},
    # Legacy slugs (pre-July-2026 runs reference these)
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
      1. sheet_pass_matrix.resolve_routed_model() when sheet_type is provided —
         exact (sheet_type, pass_type) MODEL_ROUTING entry, then the
         (WILDCARD_SHEET_TYPE, pass_type) wildcard row (MODEL_ROUTING v2).
      2. Sheet-name keyword heuristic — MEP codes and schedule-named sheets
         route to CLAUDE_MODEL_SCHEDULES.
      3. Default CLAUDE_MODEL (Haiku) for everything else.

    The sheet_pass_matrix import is deferred inside the function to avoid a
    circular dependency (sheet_pass_matrix imports _pick_model at module
    level). resolve_routed_model is a pure table lookup (no name heuristics),
    so delegating to it cannot recurse back into this function.
    """
    # 1. Routing table lookup when sheet_type is known
    if sheet_type:
        try:
            from sheet_pass_matrix import resolve_routed_model  # deferred to avoid circular import
            routed = resolve_routed_model(sheet_type, pass_type)
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
    sheet_type: Optional[str] = None,
    user_hint: Optional[str] = None,
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
    elif pass_type == "legend":
        system_prompt = LEGEND_PROMPT
    else:
        system_prompt = EXTRACTION_PROMPT  # "measure" or unknown → full extraction

    try:
        image_data, media_type = encode_image(screenshot_path)

        # Model selection: explicit override wins; otherwise routing heuristic
        if model_override:
            model = model_override
        else:
            model = _pick_model(sheet_name, pass_type, sheet_type=sheet_type)
        if model != CLAUDE_MODEL:
            logger.info(f"  Using {model} for sheet (pass={pass_type})")

        # System prompt with cache_control: cached after first call per-prompt,
        # saving ~90% on repeated drawing analyses.
        response = client.messages.create(
            model=model,
            max_tokens=16000,  # complex schedules/floor plans can produce 10k+ tokens of JSON
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
                            "text": _build_user_message(
                                sheet_name, pass_type, sheet_type, user_hint
                            ),
                        }
                    ],
                }
            ],
        )

        # Capture usage and calculate cost
        usage = response.usage
        # Unknown slugs default to the Sonnet steady-state rate (conservative
        # over-estimate for the budget guard; matches Sonnet 5 post-2026-09-01).
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
        logger.warning(f"Claude returned invalid JSON ({e}); attempting repair")
        if _JSON_REPAIR_AVAILABLE:
            try:
                repaired = _repair_json(raw_text, return_objects=True)
                if isinstance(repaired, dict):
                    repaired["_tokens_in"] = input_tokens
                    repaired["_tokens_out"] = output_tokens
                    repaired["_cost_usd"] = round(cost_usd, 6)
                    repaired["_model_used"] = model
                    repaired["_pass_type"] = pass_type
                    repaired["_source_sheet"] = sheet_name
                    repaired["_screenshot"] = screenshot_path
                    repaired["_repaired"] = True
                    logger.info(f"  [{pass_type}] JSON repaired — proceeding with partial extraction")
                    return repaired
            except Exception as repair_err:
                logger.error(f"JSON repair also failed: {repair_err}")
        logger.error(f"Claude returned invalid JSON (unrecoverable): {e}")
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


def _build_user_message(
    sheet_name: str,
    pass_type: str,
    sheet_type: Optional[str],
    user_hint: Optional[str],
) -> str:
    parts = []
    if sheet_name:
        parts.append(f"Sheet name: {sheet_name}")
    if user_hint:
        parts.append(user_hint)
    elif pass_type in ("schedule", "legend") and sheet_type == "floor_plan":
        parts.append(_SCHEDULE_LEGEND_USER_HINT)
    parts.append("Analyze this drawing and return the JSON.")
    return "\n\n".join(parts)


def _merge_schedule_lists(
    measure_result: dict,
    schedule_result: Optional[dict],
    legend_result: Optional[dict] = None,
) -> list:
    """Combine schedule tables from measure, schedule, and legend passes; prefer richest takeoff legend."""
    combined: list = []
    for src in (measure_result, schedule_result or {}, legend_result or {}):
        for sched in src.get("schedules") or []:
            if isinstance(sched, dict) and sched.get("rows"):
                combined.append(sched)
    if not combined:
        return []

    def _row_count(s: dict) -> int:
        rows = s.get("rows")
        return len(rows) if isinstance(rows, list) else 0

    legends = [
        s for s in combined
        if s.get("table_purpose") in ("takeoff_legend", "takeoff_schedule")
        and s.get("use_for_takeoff") is not False
    ]
    if legends:
        primary = max(legends, key=_row_count)
        rest = [
            s for s in combined
            if s is not primary
            and s.get("table_purpose") not in ("specification_reference", "general_notes")
        ]
        return [primary] + rest

    return combined


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

    merged["schedules"] = _merge_schedule_lists(
        measure_result, schedule_result, legend_result=None
    )

    return merged


def merge_all_passes(
    count_result: dict,
    measure_result: dict,
    schedule_result: Optional[dict] = None,
    legend_result: Optional[dict] = None,
) -> dict:
    """Merge count/measure/schedule/legend passes and apply accuracy rules."""
    merged = merge_passes(count_result, measure_result, schedule_result)
    if legend_result and legend_result.get("schedules"):
        merged["schedules"] = _merge_schedule_lists(
            merged, {"schedules": []}, legend_result
        )
    return apply_accuracy_rules(merged)


def apply_accuracy_rules(merged: dict) -> dict:
    """Drop conflicting room-derived items when takeoff legend rows exist."""
    schedules = merged.get("schedules") or []
    has_legend = any(
        s.get("table_purpose") in ("takeoff_legend", "takeoff_schedule")
        and s.get("rows")
        for s in schedules
        if isinstance(s, dict)
    )
    if not has_legend:
        return merged

    legend_text = " ".join(
        str(cell)
        for s in schedules
        for row in (s.get("rows") or [])
        if isinstance(row, dict)
        for cell in row.values()
    ).lower()

    slab_types = ("sealed", "exposed", "tilt", "cmu")
    if any(k in legend_text for k in slab_types):
        rooms = merged.get("rooms") or []
        filtered = []
        for room in rooms:
            if not isinstance(room, dict):
                continue
            notes = " ".join(
                str(room.get(k, "")) for k in ("notes", "name", "finish")
            ).lower()
            if "flooring" in notes or "vct" in notes or "carpet" in notes:
                filtered.append(room)
            elif not re.search(r"warehouse|distribution|industrial", notes, re.I):
                filtered.append(room)
        merged["rooms"] = filtered

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
