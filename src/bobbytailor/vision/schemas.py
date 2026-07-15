"""Structured-output JSON schemas for the vision fusion protocol (21-08, V3-ACC-01).

Design contract (21-RESEARCH.md §3, normative):

- Anthropic structured outputs GA: ``output_config.format = {"type":
  "json_schema", "schema": {...}}``. GA requirements enforced on every
  schema built here: ``additionalProperties: false`` at EVERY object level
  and every property listed in ``required``.
- ID fields are ``enum`` lists built from the ACTUAL candidate set, so an
  answer outside the candidate set is grammatically impossible — the
  strongest possible grounding.
- **No numeric fields on vector-sheet schemas.** Vision NEVER produces a
  number on the vector path; quantities come from geometry / the text
  layer. The ONLY schema permitted ``"type": "integer"`` / ``"type":
  "number"`` properties is :func:`raster_extraction_schema`, used solely on
  the raster fallback path (scanned plans with no vector geometry).
- Never ask the model for coordinates — candidates carry their PDF-point
  bboxes in our own registry keyed by ID.

Every builder returns a fresh dict (safe to mutate / serialize per call).
"""

from typing import List

CONFIDENCE_ENUM = ["high", "medium", "low"]

# Label a symbol group as this when no legend item matches.
UNKNOWN_LABEL = "unknown"


def _require_candidates(name: str, values: List[str]) -> List[str]:
    """Validate a candidate-ID list destined for an enum.

    JSON Schema enums must be non-empty; an empty candidate set means the
    caller has nothing to ask about and must not issue the request at all.
    """
    if not values:
        raise ValueError(
            "{}: candidate list must be non-empty (enum-of-candidates "
            "grounding requires at least one ID)".format(name)
        )
    if len(set(values)) != len(values):
        raise ValueError("{}: candidate list contains duplicates: {!r}".format(name, values))
    return list(values)


def _confidence_property() -> dict:
    """Per-answer confidence as an enum (string-typed — never numeric)."""
    return {"enum": list(CONFIDENCE_ENUM)}


def semantic_labeling_schema(region_ids: List[str], wall_class_ids: List[str]) -> dict:
    """Schema for the annotated-overlay semantic pass (handoff pattern 1).

    The model identifies the main floor-plan region and labels each wall
    class per the sheet's wall legend. Region and wall-class answers are
    enums of the actual candidate IDs.

    Args:
        region_ids:     Viewport/region candidate IDs drawn on the overlay
                        (e.g. ``["R1", "R2", "R3"]``).
        wall_class_ids: Wall-thickness-class candidate IDs (color-coded on
                        the overlay, e.g. ``["W1", "W2"]``).

    Returns:
        JSON schema dict (vector path — no numeric properties).
    """
    region_ids = _require_candidates("semantic_labeling_schema.region_ids", region_ids)
    wall_class_ids = _require_candidates(
        "semantic_labeling_schema.wall_class_ids", wall_class_ids
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["main_plan_region", "wall_class_labels", "confidence"],
        "properties": {
            "main_plan_region": {"enum": list(region_ids)},
            "wall_class_labels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["wall_class_id", "label", "confidence"],
                    "properties": {
                        "wall_class_id": {"enum": list(wall_class_ids)},
                        # Free-text semantic label from the wall legend
                        # (e.g. "CMU", "tilt-up") — a name, never a number.
                        "label": {"type": "string"},
                        "confidence": _confidence_property(),
                    },
                },
            },
            "confidence": _confidence_property(),
        },
    }


def symbol_gallery_schema(symbol_ids: List[str], legend_labels: List[str]) -> dict:
    """Schema for the crop-gallery symbol matching pass (handoff pattern 2).

    Maps each SYM-n candidate to one legend item label or ``"unknown"``.
    Both sides of the mapping are enums: symbol IDs from the clustering
    registry, labels from the legend rows (+ the unknown sentinel).

    Args:
        symbol_ids:    Symbol-group candidate IDs (e.g. ``["SYM-1", "SYM-2"]``).
        legend_labels: Legend item labels read from the sheet legend.

    Returns:
        JSON schema dict (vector path — no numeric properties).
    """
    symbol_ids = _require_candidates("symbol_gallery_schema.symbol_ids", symbol_ids)
    legend_labels = _require_candidates(
        "symbol_gallery_schema.legend_labels", legend_labels
    )
    label_choices = list(legend_labels)
    if UNKNOWN_LABEL not in label_choices:
        label_choices.append(UNKNOWN_LABEL)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["matches"],
        "properties": {
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["symbol_id", "label", "confidence"],
                    "properties": {
                        "symbol_id": {"enum": list(symbol_ids)},
                        "label": {"enum": label_choices},
                        "confidence": _confidence_property(),
                    },
                },
            },
        },
    }


def legend_structuring_schema() -> dict:
    """Schema for legend/schedule region structuring (handoff pattern 4).

    Vision reconciles table LAYOUT only; every cell value is a string read
    verbatim from the drawing (quantities in cells are authoritative
    text-layer ground truth, transported as strings — never typed numeric,
    so the model cannot compute or invent them).

    Returns:
        JSON schema dict (vector path — no numeric properties).
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["tables"],
        "properties": {
            "tables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "table_purpose", "columns", "rows"],
                    "properties": {
                        "name": {"type": "string"},
                        "table_purpose": {
                            "enum": [
                                "takeoff_legend",
                                "takeoff_schedule",
                                "specification_reference",
                                "general_notes",
                                "finish_schedule",
                                "room_schedule",
                            ],
                        },
                        "columns": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        # Row-major cell text; cells align to `columns`.
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }


def verify_retry_schema(choices: List[str]) -> dict:
    """Schema for the targeted-crop verify-retry pass (handoff pattern 3).

    A single narrow arbitration question ("ladder or stair?") answered by
    picking one of the caller-supplied choices — nothing else is expressible.

    Args:
        choices: The allowed answers (e.g. ``["ladder", "stair", "neither"]``).

    Returns:
        JSON schema dict (vector path — no numeric properties).
    """
    choices = _require_candidates("verify_retry_schema.choices", choices)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "confidence"],
        "properties": {
            "answer": {"enum": list(choices)},
            "confidence": _confidence_property(),
        },
    }


def vocabulary_schema() -> dict:
    """Schema for the autonomous project-vocabulary pass (hybrid naming).

    Replaces the deleted hand-authored manifest: an estimator-style read of
    the drawing PLUS its keynotes / general notes / abbreviations / schedule
    headers, producing the list of distinct object TYPES a take-off would
    quantify. This pass NAMES candidate object types only — it feeds the
    symbol-gallery candidate list so geometry symbol clusters can bind to a
    real object name. It MUST NOT emit any quantity: like every vector-path
    schema it carries zero numeric properties (``measure`` is a string enum
    describing HOW the type is quantified, never HOW MUCH).

    Shape::

        {"objects": [
            {"name": str,
             "measure": "count"|"linear"|"wall_area"|"floor_area"|"roof_area",
             "unit": str, "aliases": [str, ...]},
            ...
        ]}

    The ``measure`` value is a MEASURE BASIS telling fusion which deterministic
    geometry to bind to the named object (semantic-only — still zero numeric
    fields):

    - ``count``      — discrete items counted EA (columns, bollards, doors,
                       ladders, stairs, lifts) → symbol-group counts.
    - ``linear``     — items measured in LF that are NOT walls (curbs, rails).
    - ``wall_area``  — vertical walls quantified as SF (CMU, tilt-up); fusion
                       computes area = wall LF × wall height.
    - ``floor_area`` — slab / floor coverings spanning the building (sealed
                       concrete, flooring, concrete slab) → footprint area.
    - ``roof_area``  — roof / ceiling / exposed structure spanning the building
                       → footprint area.

    Returns:
        JSON schema dict (semantic path — no numeric properties).
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["objects"],
        "properties": {
            "objects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "measure", "unit", "aliases"],
                    "properties": {
                        # Distinct object type name (e.g. "Column", "Bollard").
                        "name": {"type": "string"},
                        # The MEASURE BASIS — HOW the type is quantified — a
                        # string enum, never a number (semantic discipline).
                        # Tells fusion which geometry to bind: count/linear/
                        # wall_area/floor_area/roof_area.
                        "measure": {
                            "enum": [
                                "count",
                                "linear",
                                "wall_area",
                                "floor_area",
                                "roof_area",
                            ]
                        },
                        # Unit label as a string (e.g. "ea", "sf", "lf") —
                        # read as text, never computed.
                        "unit": {"type": "string"},
                        # Common aliases / abbreviations for the type
                        # (e.g. "HM" for "Hollow Metal").
                        "aliases": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def raster_extraction_schema() -> dict:
    """Schema for the raster fallback path — the ONLY schema with numbers.

    Used solely when a sheet has no usable vector geometry (scanned plans,
    ``measurement_mode="raster"``). ``count_estimate`` is explicitly an
    estimate: downstream provenance is ``vision_ensemble`` and every
    quantity is flagged for review.

    Returns:
        JSON schema dict (raster path — ``count_estimate`` is integer-typed).
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["components"],
        "properties": {
            "components": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "count_estimate", "unit", "confidence"],
                    "properties": {
                        "name": {"type": "string"},
                        # Permitted numeric field — raster fallback only.
                        "count_estimate": {"type": "integer", "minimum": 0},
                        "unit": {"enum": ["ea", "lf", "sf"]},
                        "confidence": _confidence_property(),
                    },
                },
            },
        },
    }
