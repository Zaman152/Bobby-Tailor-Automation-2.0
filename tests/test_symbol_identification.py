"""In-context Set-of-Mark symbol identification tests (symid).

All offline — stub analyzers only, ZERO real API calls. Pins the fix that
replaced the tiny-crop symbol gallery with a full-plan Set-of-Mark overlay
plus per-cluster repetition counts:

- a LABELED symbol cluster's deterministic ``count`` becomes the component
  quantity (provenance geometry) — a 136-count column grid is a 136-EA line
  item, never an eye-count;
- ``_build_symbol_count_hint`` lists each marked cluster's repetition count
  (``SYM-1×136``), sorted by count descending;
- ``_structured_vision_call`` forwards ``user_hint`` to the analyzer so the
  symbol pass can hand the counts to the model;
- the vector symbol pass sends the count hint AND a full-plan overlay image
  list (not isolated crop tiles) to the model.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bobbytailor.pipeline.takeoff_pipeline import (
    RunSettings,
    TakeoffPipeline,
    _build_symbol_count_hint,
)
from bobbytailor.vision.fusion import fuse_sheet

FIXTURES = Path(__file__).parent / "fixtures"
CROW_PDF = FIXTURES / "crow_cass" / "crow_cass_plans.pdf"


# ---------------------------------------------------------------------------
# 1. Labeled symbol cluster count → component quantity (fusion, verified)
# ---------------------------------------------------------------------------


def test_labeled_symbol_group_count_becomes_component_quantity():
    """A vision label on SYM-1 binds to the deterministic count of 136 — the
    labeled cluster emits a "Column" component with quantity == group.count,
    unit EA, provenance geometry (vision names, geometry counts)."""
    bundle = {
        "symbol_groups": [
            {
                "candidate_id": "SYM-1",
                "count": 136,
                "representative_bbox_pt": (0.0, 0.0, 10.0, 10.0),
            }
        ],
        "sheet_name": "A-101",
    }
    vision_labels = {
        "matches": [
            {"symbol_id": "SYM-1", "label": "Column", "confidence": "high"}
        ]
    }

    fused = fuse_sheet(bundle, vision_labels)

    columns = [c for c in fused["components"] if c["name"] == "Column"]
    assert len(columns) == 1, "labeled cluster must emit exactly one component"
    col = columns[0]
    assert col["quantity"] == 136, "quantity must be the deterministic count"
    assert col["unit"] == "EA"
    assert col["provenance"] == "geometry"
    assert col["candidate_id"] == "SYM-1"


def test_unknown_symbol_label_never_emits_the_sentinel_as_a_named_item():
    """An "unknown" label is flag-don't-guess: the deterministic count is
    still carried but the group stays flagged for review and the literal
    "unknown" sentinel is never emitted as a real line-item name."""
    bundle = {
        "symbol_groups": [
            {
                "candidate_id": "SYM-9",
                "count": 5,
                "representative_bbox_pt": (0.0, 0.0, 10.0, 10.0),
                "contained_texts": [],
            }
        ],
        "sheet_name": "A-101",
    }
    vision_labels = {
        "matches": [
            {"symbol_id": "SYM-9", "label": "unknown", "confidence": "low"}
        ]
    }

    fused = fuse_sheet(bundle, vision_labels)

    names = [c["name"] for c in fused["components"]]
    assert "unknown" not in [n.lower() for n in names]
    # Plan 24-04: nor is the candidate ID emitted as a substitute name. The
    # group carries no text of its own and no anchor, so nothing the drawing
    # printed identifies it — it is ledgered, and the assertion above is not
    # left vacuously true by the row having vanished.
    assert [c for c in fused["components"] if c.get("candidate_id") == "SYM-9"] == []
    led = [r for r in fused["unnamed_geometry"] if r["candidate_id"] == "SYM-9"]
    assert len(led) == 1
    assert led[0]["quantity"] == 5                   # the deterministic count
    assert led[0]["unit"] == "EA"
    assert "unknown" not in str(led[0]["evidence_texts"]).lower()


# ---------------------------------------------------------------------------
# 2. Count hint construction
# ---------------------------------------------------------------------------


def test_symbol_count_hint_lists_counts_sorted_desc():
    symbols = [
        {"candidate_id": "SYM-2", "count": 56},
        {"candidate_id": "SYM-1", "count": 136},
        {"candidate_id": "SYM-3", "count": 54},
    ]
    hint = _build_symbol_count_hint(symbols)

    assert "SYM-1×136" in hint
    assert "SYM-2×56" in hint
    assert "SYM-3×54" in hint
    # Highest-signal cluster leads (sorted by count descending).
    assert hint.index("SYM-1×136") < hint.index("SYM-2×56") < hint.index("SYM-3×54")
    # The estimator-style reasoning cues and the unknown escape hatch are present.
    assert "column" in hint.lower()
    assert "bollard" in hint.lower()
    assert "unknown" in hint.lower()


def test_symbol_count_hint_empty_when_no_groups():
    assert _build_symbol_count_hint([]) == ""
    assert _build_symbol_count_hint([{"count": 3}]) == ""  # no candidate_id → skipped


# ---------------------------------------------------------------------------
# 3. _structured_vision_call forwards user_hint to the analyzer
# ---------------------------------------------------------------------------


def test_structured_vision_call_forwards_user_hint():
    captured = {}

    def recording_analyzer(
        screenshot_path,
        sheet_name="",
        pass_type="measure",
        model_override=None,
        sheet_type=None,
        user_hint=None,
        output_schema=None,
        images=None,
    ):
        captured["user_hint"] = user_hint
        captured["images"] = images
        return {
            "matches": [],
            "_cost_usd": 0.0,
            "_tokens_in": 1,
            "_tokens_out": 1,
            "_model_used": "stub",
        }

    pipeline = TakeoffPipeline(analyzer=recording_analyzer)
    hint = "Each marked symbol ID repeats this many times on the sheet: SYM-1×136."
    pipeline._structured_vision_call(
        "img.png",
        "A-101",
        "symbol_gallery",
        "floor_plan",
        {"type": "object"},
        ["overlay-image"],
        None,
        user_hint=hint,
    )

    assert captured["user_hint"] == hint
    assert captured["images"] == ["overlay-image"]


def test_structured_vision_call_defaults_user_hint_empty():
    """Existing callers that omit user_hint keep forwarding "" (backward compat)."""
    captured = {}

    def recording_analyzer(
        screenshot_path,
        sheet_name="",
        pass_type="measure",
        model_override=None,
        sheet_type=None,
        user_hint=None,
        output_schema=None,
        images=None,
    ):
        captured["user_hint"] = user_hint
        return {
            "matches": [],
            "_cost_usd": 0.0,
            "_tokens_in": 1,
            "_tokens_out": 1,
            "_model_used": "stub",
        }

    pipeline = TakeoffPipeline(analyzer=recording_analyzer)
    pipeline._structured_vision_call(
        "img.png", "A-101", "semantic", "floor_plan", {"type": "object"}, [], None
    )
    assert captured["user_hint"] == ""


# ---------------------------------------------------------------------------
# 4. End-to-end: the vector symbol pass sends an overlay + the count hint
# ---------------------------------------------------------------------------


class _RecordingSemanticAnalyzer:
    """Grounded structured-output stub that records per-pass images + hints.

    Answers are read off the enum constraints (grammar-constrained sampling)
    so every symbol_id maps to a real legend label — exactly what a real
    structured-output response guarantees. Records the images and user_hint of
    each symbol_gallery request so a test can assert the in-context overlay +
    count hint actually flowed to the model.
    """

    def __init__(self):
        self.symbol_gallery_images = None
        self.symbol_gallery_hint = None
        self.pass_types: list = []

    def __call__(
        self,
        screenshot_path,
        sheet_name="",
        pass_type="measure",
        model_override=None,
        sheet_type=None,
        user_hint=None,
        output_schema=None,
        images=None,
    ):
        self.pass_types.append(pass_type)
        meta = {
            "_cost_usd": 0.01,
            "_tokens_in": 100,
            "_tokens_out": 50,
            "_model_used": "canned-model",
        }
        if pass_type == "semantic":
            # Answers in the dependency-ordered grammar (24-07, V4-DET-03):
            # wall skeleton first, regions second, rooms citing both.
            props = output_schema["properties"]
            regions = props["regions"]["items"]["properties"]["region_id"]["enum"]
            wall_ids = props["wall_classes"]["items"]["properties"][
                "wall_class_id"
            ]["enum"]
            answer = {
                "wall_classes": [
                    {"wall_class_id": wid, "label": "CMU", "confidence": "high"}
                    for wid in wall_ids
                ],
                "regions": [
                    {
                        "region_id": rid,
                        "is_main_plan": rid == regions[0],
                        "confidence": "high",
                    }
                    for rid in regions
                ],
                "confidence": "high",
            }
            if "rooms" in props:
                room_ids = props["rooms"]["items"]["properties"]["room_id"]["enum"]
                answer["rooms"] = [
                    {
                        "room_id": rid,
                        "region_id": regions[0],
                        "bounding_wall_ids": list(wall_ids),
                        "label": "",
                        "confidence": "medium",
                    }
                    for rid in room_ids
                ]
            answer.update(meta)
            return answer
        if pass_type == "symbol_gallery":
            self.symbol_gallery_images = images
            self.symbol_gallery_hint = user_hint
            items = output_schema["properties"]["matches"]["items"]["properties"]
            symbol_ids = items["symbol_id"]["enum"]
            labels = items["label"]["enum"]
            answer = {
                "matches": [
                    {"symbol_id": sid, "label": labels[0], "confidence": "medium"}
                    for sid in symbol_ids
                ],
            }
            answer.update(meta)
            return answer
        answer = {"components": [], "measurements": []}
        answer.update(meta)
        return answer


@pytest.mark.skipif(not CROW_PDF.exists(), reason="Crow fixture PDF not available")
def test_vector_symbol_pass_sends_overlay_and_count_hint():
    """On the real Crow plan the symbol pass sends a full-plan overlay image
    list (Set-of-Mark) AND a repetition-count hint — not isolated crop tiles —
    and the fused result carries geometry-provenance EA components whose
    quantities come from the deterministic cluster counts."""
    analyzer = _RecordingSemanticAnalyzer()
    pipeline = TakeoffPipeline(analyzer=analyzer, settings=RunSettings())
    # Prime the autonomous project-vocabulary labels (normally produced by the
    # vocabulary pass during a full project run) so the symbol-identification
    # pass has a non-empty candidate enum — exactly the manifest-replacement
    # path the fix targets.
    pipeline._project_vocab_labels = ["Column", "Bollard", "Ladder", "Door"]
    result = pipeline.run_sheet(
        image_path="A-101.png",
        sheet_name="A-101",
        sheet_type="floor_plan",
        pdf_path=str(CROW_PDF),
        page_index=0,
    )

    assert "symbol_gallery" in analyzer.pass_types
    # In-context overlay: a non-empty list of full-plan images was sent.
    assert isinstance(analyzer.symbol_gallery_images, list)
    assert analyzer.symbol_gallery_images
    assert len(analyzer.symbol_gallery_images) <= 20
    # The repetition-count hint reached the model.
    assert analyzer.symbol_gallery_hint
    assert "repeats this many times" in analyzer.symbol_gallery_hint
    assert "SYM-1×" in analyzer.symbol_gallery_hint

    # Deterministic counts became named EA line items via fusion.
    ea_components = [
        c
        for c in result.get("components") or []
        if c.get("unit") == "EA" and c.get("provenance") == "geometry"
    ]
    assert ea_components, "labeled symbol clusters must emit geometry EA components"
    assert all(
        isinstance(c.get("quantity"), int) and c["quantity"] >= 1
        for c in ea_components
    )
