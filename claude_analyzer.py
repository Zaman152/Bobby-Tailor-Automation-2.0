import base64
import json
import logging
import re
from pathlib import Path
from typing import Tuple
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, CLAUDE_MODEL_SCHEDULES

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _pick_model(sheet_name: str) -> str:
    """Choose smarter model for sheets whose name suggests heavy tabular content.
    StackCT sheet naming conventions:
      E* = electrical (panel schedules, riser diagrams)
      M* = mechanical (equipment schedules, fan coil schedules)
      P* = plumbing schedules
      *SCHEDULE* / *PANEL* / *RISER* explicitly named
    """
    if not sheet_name:
        return CLAUDE_MODEL
    upper = sheet_name.upper()
    schedule_keywords = ("SCHEDULE", "PANEL", "RISER", "EQUIPMENT", "FIXTURE")
    if any(kw in upper for kw in schedule_keywords):
        return CLAUDE_MODEL_SCHEDULES
    # Electrical/mechanical/plumbing sheet codes (E3.1, M0.3, P1.0, etc.)
    if re.match(r"^[EMP]\d", upper):
        return CLAUDE_MODEL_SCHEDULES
    return CLAUDE_MODEL

EXTRACTION_PROMPT = """You are a quantity surveyor analyzing a construction drawing for take-off estimation.

YOUR JOB: Extract EVERY numeric value, dimension annotation, and TABLE ROW on this drawing.
Schedules and panel tables are the most important data — read EACH ROW with ALL its columns.

Return ONLY valid JSON (no markdown, no commentary):
{
  "sheet_type": "floor_plan | elevation | section | detail | schedule | panel_schedule | title_sheet | specification | other",
  "sheet_title": "title shown on the drawing (e.g. 'RISER DIAGRAM AND PANEL SCHEDULES')",
  "scale": "scale shown (e.g. 1/4\\" = 1'-0\\" or 'NTS')",
  "measurements": [
    {
      "description": "what this measures (e.g. 'north wall length', 'NEC equipment clearance', 'duct diameter')",
      "value": "EXACT value as shown (e.g. '12-6', '42', '230')",
      "unit": "ft | in | sq_ft | lf | cy | ea | kva | amps | mca | cfm",
      "location": "where on the drawing (e.g. 'detail 4 NEC clearances', 'panel HM1')",
      "raw_text": "exact text from drawing"
    }
  ],
  "components": [
    {
      "name": "component (e.g. 'PANEL HM1', 'FAN COIL UNIT FCU-1', 'TRANSFORMER T1')",
      "quantity": "numeric count or null — NEVER use 1 as placeholder",
      "unit": "ea | lf | sf",
      "specification": "spec details (e.g. '400 AMPS, 480Y/277V, 3 PHASE')",
      "location": "where on drawing"
    }
  ],
  "rooms": [
    {
      "name": "room name/number (e.g. 'CONFERENCE 106', 'SECURITY RM')",
      "area": "numeric area in sq ft if shown",
      "dimensions": "L x W if shown",
      "notes": "callouts"
    }
  ],
  "schedules": [
    {
      "name": "schedule name (e.g. 'PANEL HM1', 'DOOR SCHEDULE', 'FAN COIL UNIT SCHEDULE')",
      "schedule_type": "panel_schedule | door | window | finish | equipment | room | other",
      "header_info": "voltage/phase/wire/main/bus size/etc OR door type/size info",
      "columns": ["CKT", "DESCRIPTION", "NOTE", "BKR", "A", "B", "C", "BKR", "NOTE", "DESCRIPTION", "CKT"],
      "rows": [
        {"CKT": "1", "DESCRIPTION": "PIU-2-3", "BKR": "20/1", "A": "4.0", "B": "8.0", "C": "8.0"},
        {"CKT": "3", "DESCRIPTION": "EH ENTRANCE", "BKR": "30/1"}
      ],
      "totals": "connected loads, demand loads, total KVA if shown"
    }
  ],
  "materials": [
    {
      "type": "material name",
      "specification": "spec/grade",
      "quantity": "numeric if shown",
      "unit": "unit if shown"
    }
  ],
  "confidence": "high | medium | low",
  "notes": "key observations"
}

EXTRACTION RULES:
1. TABLES/SCHEDULES are top priority. For EVERY schedule visible (panel schedules, door schedules, equipment schedules, fan coil schedules, etc.):
   - Capture the schedule NAME (e.g. "PANEL HM1", "PANEL HI", "PANEL L2B", "PANEL ITI")
   - Capture the COLUMN HEADERS as an array
   - Capture EVERY ROW as an object keyed by column name — do not skip rows even if they look empty
   - Capture totals/footers (CONNECTED LOADS, DEMAND, TOTAL KVA, etc.)
2. PANEL SCHEDULES: For electrical panels, extract each circuit row with: CKT number, DESCRIPTION, BKR (breaker), A/B/C phase loads, NOTE.
3. NUMERIC MEASUREMENTS: capture every dimension annotation — 12'-6", 42", 230 KVA, 24 AMPS, 1250 SF, 36" MIN clearance, etc.
4. NEVER fabricate a value. If a cell is blank, omit it from the row object.
5. For details: extract every dimension callout (e.g. "42 MIN", "36 MIN", "24") with its label.
6. Read CAREFULLY — the text is small. Look at every row of every table."""


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


def analyze_drawing(screenshot_path: str, sheet_name: str = "") -> dict:
    """
    Send a drawing screenshot to Claude for vision analysis.
    Returns structured extraction data.
    """
    logger.info(f"Analyzing drawing: {sheet_name or screenshot_path}")

    try:
        image_data, media_type = encode_image(screenshot_path)

        # Auto-select smarter model for sheets likely to contain dense tables
        model = _pick_model(sheet_name)
        if model != CLAUDE_MODEL:
            logger.info(f"  Using {model} for table-heavy sheet")

        # Use a system prompt with cache_control so the large extraction prompt
        # is cached after the first call — saves ~90% on repeated drawing analyses.
        response = client.messages.create(
            model=model,
            max_tokens=8000,  # tables/panel schedules can produce a lot of JSON
            system=[
                {
                    "type": "text",
                    "text": EXTRACTION_PROMPT,
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
                            "text": f"Sheet name: {sheet_name}\n\nAnalyze this drawing and return the JSON." if sheet_name else "Analyze this drawing and return the JSON.",
                        }
                    ],
                }
            ],
        )

        raw_text = response.content[0].text.strip()

        # Strip markdown if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        extracted = json.loads(raw_text)
        extracted["_source_sheet"] = sheet_name
        extracted["_screenshot"] = screenshot_path
        logger.info(f"  Extracted {len(extracted.get('measurements', []))} measurements, "
                    f"{len(extracted.get('components', []))} components")
        return extracted

    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {e}")
        return {"error": "invalid_json", "raw": raw_text, "_source_sheet": sheet_name}
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return {"error": str(e), "_source_sheet": sheet_name}


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
