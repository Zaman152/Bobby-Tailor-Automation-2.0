"""
Supplement vision extraction with lump-sum hints from the PDF text layer.

Generic rules only — no project names or sheet numbers.
"""
import re
from typing import Dict, List


_TEXT_COMPONENT_RULES: List[tuple] = [
    (r"access\s+ladder", "Access Ladder", "ea", 1),
    (r"\bmobilization\b", "Mobilization", "ea", 1),
    (r"personnel\s+lift|material\s+lift", "Lift", "ea", 1),
]


def enrich_components_from_page_text(extracted: dict, page_text: str) -> dict:
    """Add discrete components when the text layer states them explicitly."""
    if not page_text:
        return extracted

    text = page_text.lower()
    components = list(extracted.get("components") or [])
    existing = {c.get("name", "").lower() for c in components if isinstance(c, dict)}

    for pattern, name, unit, qty in _TEXT_COMPONENT_RULES:
        if not re.search(pattern, text, re.IGNORECASE):
            continue
        if name.lower() in existing:
            continue
        components.append({
            "name": name,
            "quantity": qty,
            "unit": unit,
            "method": "note",
            "confidence": "medium",
            "location": "general notes / plan text",
            "notes": "from PDF text layer",
        })
        existing.add(name.lower())

    extracted["components"] = components
    return extracted
