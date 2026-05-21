import base64
import json
import logging
from pathlib import Path
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

EXTRACTION_PROMPT = """You are analyzing a construction drawing/plan sheet for quantity take-off estimation.

Extract ALL quantifiable data visible on this drawing. Be thorough and precise.

Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{
  "sheet_type": "floor_plan | elevation | section | detail | schedule | title_sheet | specification | other",
  "sheet_title": "the title shown on the drawing",
  "scale": "scale annotation if visible (e.g. 1/4\" = 1'-0\")",
  "measurements": [
    {
      "description": "what is being measured",
      "value": "numeric value",
      "unit": "ft | in | sq_ft | lf | ea | cy | sf | etc",
      "location": "where on the drawing (e.g. north wall, room 101, etc.)",
      "raw_text": "exact text from drawing"
    }
  ],
  "components": [
    {
      "name": "component/item name",
      "quantity": "numeric quantity or null if unknown",
      "unit": "unit of measure",
      "specification": "spec or description",
      "location": "where on the drawing"
    }
  ],
  "rooms": [
    {
      "name": "room name/number",
      "area": "area in sq ft if shown",
      "notes": "any relevant notes"
    }
  ],
  "annotations": [
    {
      "text": "annotation text",
      "type": "dimension | label | note | callout",
      "relevance": "high | medium | low"
    }
  ],
  "materials": [
    {
      "type": "material type",
      "specification": "spec details",
      "quantity": "if mentioned"
    }
  ],
  "confidence": "high | medium | low",
  "notes": "any important observations about this drawing"
}

Focus on:
- All dimension annotations (length, width, height, area)
- Room labels and areas
- Material callouts and specifications
- Door/window schedules
- Structural elements
- MEP (mechanical, electrical, plumbing) items
- Any quantity tags or callouts"""


def encode_image(filepath: str) -> tuple[str, str]:
    """Encode image to base64 and detect media type."""
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
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


def analyze_drawing(screenshot_path: str, sheet_name: str = "") -> dict:
    """
    Send a drawing screenshot to Claude for vision analysis.
    Returns structured extraction data.
    """
    logger.info(f"Analyzing drawing: {sheet_name or screenshot_path}")

    try:
        image_data, media_type = encode_image(screenshot_path)

        context = f"Sheet name: {sheet_name}\n\n" if sheet_name else ""
        prompt = context + EXTRACTION_PROMPT

        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
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
                            "text": prompt
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
        max_tokens=512,
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
