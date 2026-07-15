"""Unit tests for the vision fusion request side (21-08, V3-ACC-01/V3-ACC-04).

Pins the semantic-only vision contract:
- vector-sheet structured-output schemas contain NO numeric property types
  (quantity hallucination is grammatically impossible);
- candidate-ID enums exactly equal the deterministic candidate set;
- Set-of-Mark overlays respect the 40-marker budget and round-trip
  pixel <-> PDF-point within 2pt;
- crop galleries respect the 20-image request budget;
- analyze_drawing's structured path passes output_config through and stamps
  the usage metadata convention.

No API calls anywhere — the anthropic client is stubbed.
"""
import json

import fitz
import pytest
from PIL import Image

from bobbytailor.vision.schemas import (
    UNKNOWN_LABEL,
    legend_structuring_schema,
    raster_extraction_schema,
    semantic_labeling_schema,
    symbol_gallery_schema,
    verify_retry_schema,
    vocabulary_schema,
)
from bobbytailor.vision.overlay import (
    MAX_IMAGES_PER_REQUEST,
    MAX_MARKERS_PER_IMAGE,
    build_crop_gallery,
    render_overlay,
)

# Bind to the package module — the single canonical import path since the
# 21-18 shim deletion. test_pipeline_parity scopes its claude_analyzer mock to
# its own spec loads (key restored afterward), so this is the real module under
# any collection order; the contract is exercised in
# test_package_and_pipeline_import_contracts below.
import bobbytailor.vision.claude_analyzer as claude_analyzer


# ── Recursive schema walks ────────────────────────────────────────────────────


def _iter_object_nodes(node):
    """Yield every ``{"type": "object"}`` node in a JSON schema tree."""
    if isinstance(node, dict):
        if node.get("type") == "object":
            yield node
        for value in node.values():
            for sub in _iter_object_nodes(value):
                yield sub
    elif isinstance(node, list):
        for value in node:
            for sub in _iter_object_nodes(value):
                yield sub


def _assert_strict_objects(schema):
    """GA requirements: additionalProperties False + all properties required
    at EVERY object level."""
    object_nodes = list(_iter_object_nodes(schema))
    assert object_nodes, "schema has no object nodes"
    for node in object_nodes:
        assert node.get("additionalProperties") is False, node
        props = node.get("properties", {})
        assert props, "object node without properties: %r" % (node,)
        assert set(node.get("required", [])) == set(props.keys()), node


def _assert_no_numeric_types(node):
    """Rejection walk: no node anywhere may declare "integer" or "number"."""
    if isinstance(node, dict):
        declared = node.get("type")
        if isinstance(declared, str):
            assert declared not in ("integer", "number"), node
        elif isinstance(declared, list):
            assert "integer" not in declared and "number" not in declared, node
        for value in node.values():
            _assert_no_numeric_types(value)
    elif isinstance(node, list):
        for value in node:
            _assert_no_numeric_types(value)


_VECTOR_BUILDERS = [
    pytest.param(lambda: semantic_labeling_schema(["R1", "R2"], ["W1", "W2"]),
                 id="semantic_labeling"),
    pytest.param(lambda: symbol_gallery_schema(["SYM-1", "SYM-2"], ["Bollard", "Column"]),
                 id="symbol_gallery"),
    pytest.param(legend_structuring_schema, id="legend_structuring"),
    pytest.param(lambda: verify_retry_schema(["ladder", "stair", "neither"]),
                 id="verify_retry"),
    pytest.param(vocabulary_schema, id="vocabulary"),
]


# ── 1. Vector schemas: strict objects, no numbers, exact ID enums ────────────


@pytest.mark.parametrize("builder", _VECTOR_BUILDERS)
def test_vector_schema_strict_objects_all_required(builder):
    _assert_strict_objects(builder())


@pytest.mark.parametrize("builder", _VECTOR_BUILDERS)
def test_vector_schema_rejects_numeric_property_types(builder):
    schema = builder()
    _assert_no_numeric_types(schema)
    # Belt-and-braces on the serialized form as well.
    serialized = json.dumps(schema)
    assert '"type": "integer"' not in serialized
    assert '"type": "number"' not in serialized


def test_semantic_labeling_enums_equal_candidate_lists():
    schema = semantic_labeling_schema(["R1", "R2", "R3"], ["W1", "W2"])
    assert schema["properties"]["main_plan_region"]["enum"] == ["R1", "R2", "R3"]
    item = schema["properties"]["wall_class_labels"]["items"]
    assert item["properties"]["wall_class_id"]["enum"] == ["W1", "W2"]
    # Acceptance criterion literal: serialized form carries the exact enum.
    assert '"enum": ["R1", "R2", "R3"]' in json.dumps(schema)


def test_symbol_gallery_enums_candidates_plus_unknown():
    schema = symbol_gallery_schema(["SYM-1", "SYM-2"], ["Bollard", "Catch Basin"])
    item = schema["properties"]["matches"]["items"]
    assert item["properties"]["symbol_id"]["enum"] == ["SYM-1", "SYM-2"]
    assert item["properties"]["label"]["enum"] == ["Bollard", "Catch Basin", UNKNOWN_LABEL]


def test_verify_retry_answer_enum_equals_choices():
    schema = verify_retry_schema(["ladder", "stair"])
    assert schema["properties"]["answer"]["enum"] == ["ladder", "stair"]


def test_schema_builders_reject_empty_or_duplicate_candidates():
    with pytest.raises(ValueError):
        semantic_labeling_schema([], ["W1"])
    with pytest.raises(ValueError):
        symbol_gallery_schema(["SYM-1"], [])
    with pytest.raises(ValueError):
        verify_retry_schema([])
    with pytest.raises(ValueError):
        verify_retry_schema(["ladder", "ladder"])


# ── 2. Raster fallback: the ONLY schema allowed numbers (positive control) ───


def test_raster_schema_allows_count_estimate_numeric():
    schema = raster_extraction_schema()
    _assert_strict_objects(schema)
    item = schema["properties"]["components"]["items"]
    assert item["properties"]["count_estimate"]["type"] == "integer"
    # And the numeric permission is CONFINED to count_estimate.
    with pytest.raises(AssertionError):
        _assert_no_numeric_types(schema)


# ── 3-4. Overlay renders + crop galleries ────────────────────────────────────


@pytest.fixture()
def arch_page():
    """Synthetic 3024x2160pt arch-D sheet (fixture PDF geometry not needed)."""
    doc = fitz.open()
    page = doc.new_page(width=3024, height=2160)
    yield page
    doc.close()


def test_render_overlay_single_image_under_marker_budget(arch_page):
    candidates = {"R1": (100, 100, 900, 700), "W1": (200, 1200, 2400, 1260)}
    img = render_overlay(arch_page, candidates)
    assert isinstance(img, Image.Image)
    assert max(img.size) <= 1600
    assert img.info["overlay_ids"] == ["R1", "W1"]


def test_render_overlay_partitions_45_candidates_into_two_images(arch_page):
    candidates = {
        "SYM-%d" % i: (50 + 12 * i, 50, 80 + 12 * i, 90) for i in range(45)
    }
    images = render_overlay(arch_page, candidates)
    assert isinstance(images, list)
    assert len(images) == 2
    subsets = [set(img.info["overlay_ids"]) for img in images]
    assert len(subsets[0]) == MAX_MARKERS_PER_IMAGE
    assert subsets[0].isdisjoint(subsets[1])
    assert subsets[0] | subsets[1] == set(candidates.keys())


def test_render_overlay_pixel_bbox_roundtrips_within_2pt(arch_page):
    bbox_pt = (123.4, 567.8, 910.1, 1112.3)
    img = render_overlay(arch_page, {"R1": bbox_pt})
    zoom = img.info["zoom"]
    bbox_px = img.info["marker_boxes_px"]["R1"]
    roundtrip_pt = tuple(v / zoom for v in bbox_px)
    for got, expected in zip(roundtrip_pt, bbox_pt):
        assert abs(got - expected) <= 2.0, (roundtrip_pt, bbox_pt)


def test_build_crop_gallery_25_groups_respects_20_image_budget(arch_page):
    groups = [
        {
            "candidate_id": "SYM-%d" % (i + 1),
            "representative_bbox_pt": (100 + 30 * i, 100, 125 + 30 * i, 125),
            "instance_bboxes_pt": [
                (100 + 30 * i, 100, 125 + 30 * i, 125),
                (100 + 30 * i, 200, 125 + 30 * i, 225),
            ],
        }
        for i in range(25)
    ]
    images = build_crop_gallery(
        arch_page, groups, legend_crop_rect=(2500, 100, 2900, 700)
    )
    assert 1 <= len(images) <= MAX_IMAGES_PER_REQUEST
    assert images[0].info.get("is_legend") is True
    covered = [cid for img in images[1:] for cid in img.info["gallery_ids"]]
    assert covered == ["SYM-%d" % (i + 1) for i in range(25)]


# ── 5. analyze_drawing structured-output path (client stubbed, no API) ───────


class _StubUsage:
    input_tokens = 1000
    output_tokens = 200


class _StubBlock:
    def __init__(self, text):
        self.text = text


class _StubResponse:
    def __init__(self, text):
        self.usage = _StubUsage()
        self.content = [_StubBlock(text)]


class _StubMessages:
    def __init__(self, text):
        self._text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _StubResponse(self._text)


class _StubClient:
    def __init__(self, payload):
        self.messages = _StubMessages(json.dumps(payload))


def test_analyze_drawing_structured_path_passes_output_config_and_stamps_metadata(monkeypatch):
    payload = {"main_plan_region": "R1", "wall_class_labels": [], "confidence": "high"}
    stub = _StubClient(payload)
    monkeypatch.setattr(claude_analyzer, "client", stub)

    schema = semantic_labeling_schema(["R1", "R2"], ["W1"])
    overlay_img = Image.new("RGB", (64, 64), "#ffffff")
    result = claude_analyzer.analyze_drawing(
        "",
        sheet_name="A1.0",
        pass_type="semantic",
        sheet_type="floor_plan",
        output_schema=schema,
        images=[overlay_img],
        model_override="claude-sonnet-5",
    )

    # Request assertions
    assert len(stub.messages.calls) == 1
    kwargs = stub.messages.calls[0]
    assert kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": schema}
    }
    content = kwargs["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "text"]
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "ONLY job is semantic labeling" in kwargs["system"][0]["text"]

    # Response metadata convention (PATTERNS: underscore fields)
    assert result["main_plan_region"] == "R1"
    assert result["_tokens_in"] == 1000
    assert result["_tokens_out"] == 200
    assert result["_model_used"] == "claude-sonnet-5"
    assert result["_pass_type"] == "semantic"
    expected_cost = round((1000 * 2.0 + 200 * 10.0) / 1_000_000, 6)
    assert result["_cost_usd"] == expected_cost


def test_analyze_drawing_structured_path_multiple_image_blocks(monkeypatch):
    payload = {"matches": []}
    stub = _StubClient(payload)
    monkeypatch.setattr(claude_analyzer, "client", stub)

    schema = symbol_gallery_schema(["SYM-1"], ["Bollard"])
    gallery = [Image.new("RGB", (32, 32)), Image.new("RGB", (32, 32))]
    result = claude_analyzer.analyze_drawing(
        "",
        sheet_name="A1.0",
        pass_type="symbol_gallery",
        sheet_type="floor_plan",
        output_schema=schema,
        images=gallery,
        model_override="claude-sonnet-5",
    )
    content = stub.messages.calls[0]["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "image", "text"]
    assert result["matches"] == []
    assert result["_pass_type"] == "symbol_gallery"


def test_analyze_drawing_structured_path_routes_via_pick_model_for_pass(monkeypatch):
    payload = {"answer": "ladder", "confidence": "high"}
    stub = _StubClient(payload)
    monkeypatch.setattr(claude_analyzer, "client", stub)

    from bobbytailor.pipeline.sheet_pass_matrix import pick_model_for_pass
    expected = pick_model_for_pass("floor_plan", "verify_retry", "") or claude_analyzer.CLAUDE_MODEL

    result = claude_analyzer.analyze_drawing(
        "",
        pass_type="verify_retry",
        sheet_type="floor_plan",
        output_schema=verify_retry_schema(["ladder", "stair"]),
        images=[Image.new("RGB", (32, 32))],
    )
    assert stub.messages.calls[0]["model"] == expected
    assert result["_model_used"] == expected


def test_analyze_drawing_error_path_keeps_zero_cost_convention(monkeypatch):
    class _Boom:
        class messages:  # noqa: N801 — mimics client.messages namespace
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("api down")

    monkeypatch.setattr(claude_analyzer, "client", _Boom())
    result = claude_analyzer.analyze_drawing(
        "",
        pass_type="semantic",
        sheet_type="floor_plan",
        output_schema=semantic_labeling_schema(["R1"], ["W1"]),
        images=[Image.new("RGB", (16, 16))],
    )
    assert result["error"] == "api down"
    assert result["_cost_usd"] == 0
    assert result["_tokens_in"] == 0


# ── Import contracts (21-18 package paths + 20-00/20-03 pipeline contracts) ──


def test_package_and_pipeline_import_contracts():
    import importlib

    # 21-18 contract: the root shims are gone; the package path is the single
    # canonical import path and holds the REAL module (test_pipeline_parity
    # scopes its claude_analyzer mock to its own spec loads and restores the
    # key, so this must hold under any collection order).
    mod = importlib.import_module("bobbytailor.vision.claude_analyzer")
    assert mod is claude_analyzer
    # Prompt constants remain importable through the package path.
    assert "MEASURE PASS ADDENDUM" in mod.EXTRACTION_PROMPT
    assert mod.SEMANTIC_LABELING_PROMPT is claude_analyzer.SEMANTIC_LABELING_PROMPT

    # takeoff_pipeline contracts (20-00/20-03): analyze_drawing injectable +
    # canonical merge_passes re-export stay intact after the prompt refactor.
    # Functional (not identity) assertions: test_pipeline_parity spec-loads a
    # fresh exec copy of takeoff_pipeline for its own use, so object identity
    # across module copies is not order-stable — behavior is the contract.
    from bobbytailor.pipeline import takeoff_pipeline
    assert takeoff_pipeline.merge_passes.__name__ == "merge_passes"
    merged = takeoff_pipeline.merge_passes(
        {"components": [{"name": "Bollard", "quantity": 28, "unit": "ea",
                         "confidence": "high"}]},
        {"components": []},
    )
    assert merged["components"][0]["name"] == "Bollard"
    pipeline = takeoff_pipeline.TakeoffPipeline(analyzer=lambda *a, **k: {})
    assert pipeline is not None
