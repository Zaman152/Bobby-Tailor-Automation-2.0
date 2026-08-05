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
import pathlib

import fitz
import pytest
from PIL import Image

from bobbytailor.pipeline import takeoff_pipeline
from bobbytailor.pipeline.takeoff_pipeline import (
    _build_anchor_hint,
)
from bobbytailor.vision import prompts
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
    _CHIP_MAX_ANCHOR_CHARS,
    _anchor_text_for,
    _chip_box,
    _marker_label,
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
    pytest.param(
        lambda: semantic_labeling_schema(
            ["R1", "R2"], ["W1", "W2"], ["ROOM-1", "ROOM-2"]
        ),
        id="semantic_labeling_with_rooms",
    ),
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
    region_item = schema["properties"]["regions"]["items"]
    assert region_item["properties"]["region_id"]["enum"] == ["R1", "R2", "R3"]
    item = schema["properties"]["wall_classes"]["items"]
    assert item["properties"]["wall_class_id"]["enum"] == ["W1", "W2"]
    # Acceptance criterion literal: serialized form carries the exact enum.
    assert '"enum": ["R1", "R2", "R3"]' in json.dumps(schema)


# ── 1b. Dependency-ordered schema topology (24-07, V4-DET-03) ────────────────
#
# The flat predecessor made an unbounded sliver EXPRESSIBLE — rooms carried no
# relationship to the walls enclosing them, and both saved paid runs published
# four rooms at ~10-11 SF each on a 397,600 SF warehouse. Ordering the levels
# makes that gap unexpressible rather than merely flagged.


def test_dependency_ordered_levels_precede_every_reference_to_them():
    """Wall skeleton first, regions second, rooms citing only what is above."""
    schema = semantic_labeling_schema(
        ["R1", "R2"], ["W1", "W2"], ["ROOM-1", "ROOM-2"]
    )
    order = list(schema["properties"].keys())
    assert order.index("wall_classes") < order.index("regions")
    assert order.index("regions") < order.index("rooms")
    # `required` declares the same order — it is the generation order the
    # model follows, so the two must not disagree.
    assert schema["required"] == order

    room = schema["properties"]["rooms"]["items"]["properties"]
    # Every ID a room names is an enum of a level DEFINED ABOVE IT, never a
    # free string: a reference to something undefined is unexpressible.
    assert room["region_id"]["enum"] == ["R1", "R2"]
    assert room["bounding_wall_ids"]["items"]["enum"] == ["W1", "W2"]
    assert room["room_id"]["enum"] == ["ROOM-1", "ROOM-2"]
    assert "type" not in room["region_id"]
    assert "type" not in room["room_id"]


def test_dependency_ordered_a_room_may_cite_no_bounding_wall():
    """The model is never FORCED to invent a reference it cannot make."""
    schema = semantic_labeling_schema(["R1"], ["W1"], ["ROOM-1"])
    item = schema["properties"]["rooms"]["items"]
    # The GA contract puts every property in `required` ...
    assert "bounding_wall_ids" in item["required"]
    # ... so omittability is expressed as an ALLOWED EMPTY LIST, and nothing
    # in the schema forbids one (no minItems, no required entry count).
    wall_ref = item["properties"]["bounding_wall_ids"]
    assert wall_ref["type"] == "array"
    assert "minItems" not in wall_ref
    # That present-and-empty citation is exactly what fusion's orphan-room
    # branch reads, under exactly this key.
    from bobbytailor.vision.fusion import ROOM_WALL_REFERENCE_FIELD

    assert ROOM_WALL_REFERENCE_FIELD in item["properties"]


def test_dependency_ordered_rooms_are_absent_rather_than_empty_enum():
    """No room candidates → no rooms level. An enum can never be empty."""
    for schema in (
        semantic_labeling_schema(["R1"], ["W1"]),
        semantic_labeling_schema(["R1"], ["W1"], []),
        semantic_labeling_schema(["R1"], ["W1"], None),
    ):
        assert "rooms" not in schema["properties"]
        assert "rooms" not in schema["required"]
        _assert_strict_objects(schema)


def test_dependency_ordered_still_guards_every_id_list():
    """`_require_candidates` keeps an invalid enum grammatically impossible."""
    with pytest.raises(ValueError):
        semantic_labeling_schema([], ["W1"], ["ROOM-1"])
    with pytest.raises(ValueError):
        semantic_labeling_schema(["R1"], [], ["ROOM-1"])
    with pytest.raises(ValueError):
        semantic_labeling_schema(["R1"], ["W1"], ["ROOM-1", "ROOM-1"])


def test_no_numeric_fields_anywhere_on_any_vector_path_builder():
    """The ban is structural: walked over EVERY vector builder in the module.

    Discovered by module introspection rather than by naming builders one by
    one, so a schema added later cannot slip in uncovered — which is precisely
    how a quantity field would arrive.
    """
    import inspect

    from bobbytailor.vision import schemas as schemas_module

    # Sample arguments for the builders that take candidate lists; anything
    # taking arguments we cannot supply would silently skip, so that is an
    # explicit failure rather than a quiet pass.
    sample_args = {
        "semantic_labeling_schema": (["R1", "R2"], ["W1", "W2"], ["ROOM-1"]),
        "symbol_gallery_schema": (["SYM-1"], ["Bollard"]),
        "verify_retry_schema": (["ladder", "stair"],),
    }
    builders = [
        (name, fn)
        for name, fn in vars(schemas_module).items()
        if inspect.isfunction(fn)
        and name.endswith("_schema")
        and not name.startswith("_")
        and name != "raster_extraction_schema"  # the one flagged raster path
    ]
    assert len(builders) >= 5, [n for n, _ in builders]

    for name, builder in builders:
        args = sample_args.get(name, ())
        if not args and inspect.signature(builder).parameters:
            required = [
                p for p in inspect.signature(builder).parameters.values()
                if p.default is inspect.Parameter.empty
            ]
            assert not required, (
                "%s takes arguments this test cannot supply, so it would be "
                "silently skipped — add it to sample_args" % name
            )
        schema = builder(*args)
        _assert_no_numeric_types(schema)
        serialized = json.dumps(schema)
        # The whole serialized form, not just typed nodes: a numeric field
        # smuggled in as a description or a constraint is still a numeric field.
        assert "integer" not in serialized, name
        assert "number" not in serialized, name


def test_the_raster_path_remains_the_one_schema_permitted_a_number():
    """A positive control: the ban above is a real constraint, not vacuous."""
    serialized = json.dumps(raster_extraction_schema())
    assert "integer" in serialized


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


# ── 4b. The anchor-bearing Set-of-Mark chip (24-07, V4-DET-01) ───────────────
#
# The marker chip used to carry ONLY the candidate ID, which is precisely the
# symbol-conveyed condition the evidence base measures at 0.03-0.39 accuracy
# against 0.65-0.92 for text-anchored classes. These pin that the chip now
# carries the drawing's own printed callout, that a candidate with a RECORDED
# ABSENCE still renders exactly the bare-ID chip it always did, and that the
# request never contains a candidate the drawing does not name.


def _anchor(cid, text, kind="nearest_word"):
    """A 24-01 anchor record; ``text=None`` is the RECORDED ABSENCE."""
    return {
        "candidate_id": cid,
        "anchor_text": text,
        "anchor_kind": None if text is None else kind,
        "anchor_dist_pt": None if text is None else 4.0,
        "anchor_source": None if text is None else "page_words",
        "ambiguity_reason": "",
    }


def test_anchor_chip_carries_the_candidate_id_and_its_anchor_text():
    """The one edit V4-DET-01 rests on: the chip gives the model text to READ."""
    assert _marker_label("SYM-1", "BOLLARD") == "SYM-1 BOLLARD"
    assert _marker_label("WALL-TC1", "CMU") == "WALL-TC1 CMU"


def test_anchor_chip_without_an_anchor_is_the_bare_id_with_no_placeholder():
    """A recorded absence renders today's chip — no placeholder, no separator."""
    assert _marker_label("SYM-1", "") == "SYM-1"
    assert _marker_label("SYM-1") == "SYM-1"
    # And a recorded absence resolves to "" rather than to the string "None".
    assert _anchor_text_for({"SYM-1": _anchor("SYM-1", None)}, "SYM-1") == ""
    # As does a candidate the map does not mention at all.
    assert _anchor_text_for({"SYM-2": _anchor("SYM-2", "GATE")}, "SYM-1") == ""
    assert _anchor_text_for(None, "SYM-1") == ""


def test_anchor_chip_reads_the_24_01_record_or_a_bare_string():
    """Callers may hand `bundle['candidate_anchors']` straight through."""
    assert _anchor_text_for({"SYM-1": _anchor("SYM-1", "BOLLARD")}, "SYM-1") == "BOLLARD"
    assert _anchor_text_for({"SYM-1": "BOLLARD"}, "SYM-1") == "BOLLARD"
    # The chip is measured and drawn as ONE line, so whitespace is collapsed.
    assert _anchor_text_for({"W1": _anchor("W1", "CMU\n WALL")}, "W1") == "CMU WALL"


def test_anchor_chip_text_is_bounded_so_a_chip_cannot_outgrow_the_sheet():
    """A pathological harvest is bounded on the CHIP; the hint keeps it whole."""
    long_text = "X" * 200
    chip = _anchor_text_for({"SYM-1": _anchor("SYM-1", long_text)}, "SYM-1")
    assert len(chip) <= _CHIP_MAX_ANCHOR_CHARS
    # A genuine two-token material tag (Moxy prints 166 of them) is untouched.
    assert _anchor_text_for({"SYM-1": _anchor("SYM-1", "WC 01")}, "SYM-1") == "WC 01"


def test_the_chip_box_is_placed_exactly_as_before_when_it_already_fits():
    """Positional non-regression: the clamp is a NO-OP for a chip that fits."""
    # Room above the box → chip sits directly above it, left edges aligned.
    assert _chip_box(100, 200, 40, 16, (1568, 1120)) == (100, 184, 140, 200)
    # No room above → chip sits inside the box (the pre-existing top rule).
    assert _chip_box(100, 8, 40, 16, (1568, 1120)) == (100, 8, 140, 24)
    # No image size supplied → identical placement, no clamp at all.
    assert _chip_box(100, 200, 40, 16, None) == (100, 184, 140, 200)


def test_the_chip_box_is_clamped_inside_the_right_edge():
    """T-24-32: a longer anchor label slides left rather than off the sheet."""
    box = _chip_box(1540, 200, 120, 16, (1568, 1120))
    assert box[2] <= 1568, box
    assert box[0] == 1568 - 120
    # A chip wider than the whole image pins at 0 rather than going negative.
    assert _chip_box(1540, 200, 9000, 16, (1568, 1120))[0] == 0


def test_render_overlay_with_a_recorded_absence_is_byte_identical(arch_page):
    """Every existing caller is unaffected: no anchor argument, same raster."""
    candidates = {"R1": (100, 100, 900, 700), "W1": (200, 1200, 2400, 1260)}
    plain = render_overlay(arch_page, candidates)
    absences = render_overlay(
        arch_page, candidates,
        anchors={"R1": _anchor("R1", None), "W1": _anchor("W1", None)},
    )
    assert plain.tobytes() == absences.tobytes()
    assert plain.info["overlay_ids"] == absences.info["overlay_ids"]
    assert plain.info["marker_boxes_px"] == absences.info["marker_boxes_px"]


def test_render_overlay_with_an_anchor_actually_changes_the_raster(arch_page):
    """The anchor reaches the pixels the model reads, not just a variable."""
    candidates = {"R1": (100, 100, 900, 700)}
    plain = render_overlay(arch_page, candidates)
    anchored = render_overlay(
        arch_page, candidates, anchors={"R1": _anchor("R1", "OFFICE")}
    )
    assert plain.tobytes() != anchored.tobytes()
    # The grounding metadata is untouched by the longer chip.
    assert plain.info["marker_boxes_px"] == anchored.info["marker_boxes_px"]
    assert plain.info["zoom"] == anchored.info["zoom"]


def test_the_marker_budget_and_partition_survive_anchor_text(arch_page):
    """Longer chips must not perturb the 40-marker budget or the partition."""
    candidates = {
        "SYM-%d" % i: (50 + 12 * i, 50, 80 + 12 * i, 90) for i in range(45)
    }
    anchors = {cid: _anchor(cid, "DOCK BUMPER TYP") for cid in candidates}
    images = render_overlay(arch_page, candidates, anchors=anchors)
    assert isinstance(images, list)
    assert len(images) == 2
    subsets = [set(img.info["overlay_ids"]) for img in images]
    assert len(subsets[0]) == MAX_MARKERS_PER_IMAGE
    assert subsets[0].isdisjoint(subsets[1])
    assert subsets[0] | subsets[1] == set(candidates.keys())


# ── 4c. The anchor table in the user hint (T-24-27) ──────────────────────────


def test_the_anchor_hint_is_wrapped_in_the_pdf_text_delimiters():
    """Drawing-derived text entering a prompt MUST be delimiter-wrapped."""
    hint = _build_anchor_hint(
        {"SYM-1": "BOLLARD", "SYM-2": "LADDER"}, ["SYM-1", "SYM-2"]
    )
    assert prompts.PDF_TEXT_OPEN in hint
    assert prompts.PDF_TEXT_CLOSE in hint
    # Every anchor string sits INSIDE the delimiters, never outside them.
    body = hint.split(prompts.PDF_TEXT_OPEN, 1)[1].split(prompts.PDF_TEXT_CLOSE, 1)[0]
    assert "SYM-1: BOLLARD" in body
    assert "SYM-2: LADDER" in body
    assert "BOLLARD" not in hint.split(prompts.PDF_TEXT_OPEN, 1)[0]


def test_the_anchor_hint_carries_the_full_text_the_chip_had_to_bound():
    """The chip bounds a long harvest; the hint is its lossless delivery."""
    long_text = "SOUTH ELEVATION DOCK BUMPER ASSEMBLY TYPICAL"
    hint = _build_anchor_hint({"SYM-1": long_text}, ["SYM-1"])
    assert long_text in hint


def test_the_anchor_hint_is_empty_when_no_listed_candidate_is_anchored():
    """No anchors → no table, and therefore no empty delimiter block."""
    assert _build_anchor_hint({}, ["SYM-1"]) == ""
    assert _build_anchor_hint({"SYM-9": "GATE"}, ["SYM-1", "SYM-2"]) == ""


def test_the_anchor_selector_drops_a_recorded_absence_and_keeps_real_text():
    """`anchor_text is None` is an absence, never the string 'None'."""
    bundle = {
        "candidate_anchors": {
            "SYM-1": _anchor("SYM-1", "BOLLARD"),
            "SYM-2": _anchor("SYM-2", None),
            "SYM-3": _anchor("SYM-3", "   "),
        }
    }
    assert takeoff_pipeline._anchor_texts(bundle) == {"SYM-1": "BOLLARD"}
    assert takeoff_pipeline._anchor_texts({}) == {}


def test_a_recorded_absence_and_an_absent_record_are_not_the_same_thing():
    """INV-08: the drawing printing nothing is not the same as never asking."""
    bundle = {
        "candidate_anchors": {
            "SYM-1": _anchor("SYM-1", "BOLLARD"),
            "SYM-2": _anchor("SYM-2", None),
            "SYM-3": _anchor("SYM-3", "   "),
        }
    }
    # Interrogated and nothing printed → a recorded absence.
    assert takeoff_pipeline._anchor_absences(bundle) == {"SYM-2", "SYM-3"}
    # Never interrogated → NOT an absence, however unanchored it looks.
    assert "SYM-9" not in takeoff_pipeline._anchor_absences(bundle)
    # A bundle whose anchor computation failed records no absence at all.
    assert takeoff_pipeline._anchor_absences({}) == set()
    assert takeoff_pipeline._anchor_absences({"candidate_anchors": {}}) == set()


# ── 4d. The symbol pass never asks about a candidate the drawing does not name


class _SchemaRecordingAnalyzer:
    """Records every structured request; answers nothing (labels are additive)."""

    def __init__(self):
        self.calls = []

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
        self.calls.append(
            {
                "pass_type": pass_type,
                "output_schema": output_schema,
                "user_hint": user_hint,
                "images": images,
            }
        )
        return {
            "_cost_usd": 0.0,
            "_tokens_in": 0,
            "_tokens_out": 0,
            "_model_used": "stub",
        }

    def symbol_call(self):
        for call in self.calls:
            if call["pass_type"] == "symbol_gallery":
                return call
        return None


_CROW_PDF = (
    pathlib.Path(__file__).parent / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"
)


def _run_crow_symbol_pass(monkeypatch, anchor_override):
    """Run Crow page 0's vector flow with a controlled anchor map."""
    from bobbytailor.pipeline.takeoff_pipeline import RunSettings, TakeoffPipeline

    original = TakeoffPipeline._deterministic_bundle

    def patched(self, *args, **kwargs):
        bundle = original(self, *args, **kwargs)
        bundle["candidate_anchors"] = anchor_override(bundle)
        return bundle

    monkeypatch.setattr(TakeoffPipeline, "_deterministic_bundle", patched)
    analyzer = _SchemaRecordingAnalyzer()
    pipeline = TakeoffPipeline(analyzer=analyzer, settings=RunSettings())
    pipeline._project_vocab_labels = ["Column", "Bollard", "Ladder", "Door"]
    pipeline.run_sheet(
        image_path="A-101.png",
        sheet_name="A-101",
        sheet_type="floor_plan",
        pdf_path=str(_CROW_PDF),
        page_index=0,
    )
    return analyzer


@pytest.mark.skipif(not _CROW_PDF.exists(), reason="Crow fixture PDF not available")
def test_the_symbol_pass_asks_only_about_candidates_the_drawing_names(monkeypatch):
    """An unanchored cluster is ABSENT from the request, not asked and dropped."""
    kept = {}

    def only_two_anchored(bundle):
        ids = [
            str(g.candidate_id if hasattr(g, "candidate_id") else g["candidate_id"])
            for g in bundle.get("symbol_groups") or []
        ]
        assert len(ids) > 2, "Crow page 0 must offer more clusters than we anchor"
        kept["anchored"] = ids[:2]
        kept["unanchored"] = ids[2:]
        anchors = {cid: _anchor(cid, None) for cid in ids}
        for cid in kept["anchored"]:
            anchors[cid] = _anchor(cid, "BOLLARD")
        return anchors

    analyzer = _run_crow_symbol_pass(monkeypatch, only_two_anchored)
    call = analyzer.symbol_call()
    assert call is not None, "the symbol pass must still run for anchored clusters"
    enum = call["output_schema"]["properties"]["matches"]["items"]["properties"][
        "symbol_id"
    ]["enum"]
    assert set(enum) == set(kept["anchored"])
    for cid in kept["unanchored"]:
        assert cid not in enum
    # The count hint names only the clusters actually asked about.
    assert kept["unanchored"][0] + "×" not in (call["user_hint"] or "")
    # And the anchor table rode along, inside the delimiters.
    assert prompts.PDF_TEXT_OPEN in call["user_hint"]
    assert kept["anchored"][0] + ": BOLLARD" in call["user_hint"]


@pytest.mark.skipif(not _CROW_PDF.exists(), reason="Crow fixture PDF not available")
def test_the_symbol_pass_is_skipped_rather_than_sent_with_no_candidates(monkeypatch):
    """`_require_candidates` raises on an empty enum by design — never issue one."""
    analyzer = _run_crow_symbol_pass(
        monkeypatch,
        lambda bundle: {
            str(g.candidate_id if hasattr(g, "candidate_id") else g["candidate_id"]):
            _anchor("x", None)
            for g in bundle.get("symbol_groups") or []
        },
    )
    assert analyzer.symbol_call() is None
    assert [c["pass_type"] for c in analyzer.calls].count("symbol_gallery") == 0


@pytest.mark.skipif(not _CROW_PDF.exists(), reason="Crow fixture PDF not available")
def test_an_absent_anchor_map_is_not_read_as_every_candidate_unanchored(monkeypatch):
    """INV-08: a failed anchor computation must not silently empty the pass."""
    analyzer = _run_crow_symbol_pass(monkeypatch, lambda bundle: {})
    call = analyzer.symbol_call()
    assert call is not None, (
        "an absent anchor map means the computation did not run — reading it as "
        "'no candidate is anchored' turns an infrastructure failure into a "
        "silently empty pass"
    )


# ── 4e. The dependency-ordered answer reaches its existing consumers ─────────
#
# The SCHEMA topology changed; the internal label contract deliberately did
# not. fusion, the reporter and the merged result keep reading the keys they
# always read, so the change stops at one adapter in `_run_sheet_vector`.


def test_the_main_plan_answer_survives_the_regions_level():
    """One claim answers; nothing claiming, or two claiming, answers nothing."""
    pick = takeoff_pipeline._main_region_from_answer
    assert pick([
        {"region_id": "R1", "is_main_plan": False, "confidence": "high"},
        {"region_id": "R2", "is_main_plan": True, "confidence": "high"},
    ]) == "R2"
    # Nothing claims it → no answer, rather than the first region by default.
    assert pick([{"region_id": "R1", "is_main_plan": False}]) is None
    # TWO claim it → a contest, and picking one would be guessing which of two
    # disagreeing answers to trust. The deterministic selection still stands.
    assert pick([
        {"region_id": "R1", "is_main_plan": True},
        {"region_id": "R2", "is_main_plan": True},
    ]) is None
    assert pick(None) is None
    assert pick([]) is None


def test_the_room_wall_citation_lands_on_the_record_fusion_reads():
    """V4-DET-03: the field 24-04's orphan-room branch already reads."""
    from bobbytailor.vision.fusion import ROOM_WALL_REFERENCE_FIELD

    rooms = [
        {"candidate_id": "ROOM-1", "polygon_wkt": "", "area_pt2": 10.0},
        {"candidate_id": "ROOM-2", "polygon_wkt": "", "area_pt2": 20.0},
        {"candidate_id": "ROOM-3", "polygon_wkt": "", "area_pt2": 30.0},
    ]
    applied = takeoff_pipeline._apply_room_wall_references(
        rooms,
        [
            {"room_id": "ROOM-1", ROOM_WALL_REFERENCE_FIELD: ["W1", "W2"]},
            # Answered, and cited NOTHING — the room saying it cannot name the
            # walls enclosing it. This is what gets ledgered, not published.
            {"room_id": "ROOM-2", ROOM_WALL_REFERENCE_FIELD: []},
            # Answered WITHOUT the key at all — never asked, so never judged.
            {"room_id": "ROOM-3", "label": "OFFICE"},
        ],
    )
    assert applied == 2
    assert rooms[0][ROOM_WALL_REFERENCE_FIELD] == ["W1", "W2"]
    assert rooms[1][ROOM_WALL_REFERENCE_FIELD] == []
    assert ROOM_WALL_REFERENCE_FIELD not in rooms[2], (
        "an answer omitting the citation must leave the field ABSENT — writing "
        "an empty list would manufacture the citation failure the branch exists "
        "to detect (INV-08)"
    )


def test_the_room_wall_citation_writes_to_a_dataclass_record_too():
    """Bundle rooms are RoomPolygon dataclasses on the real path, not dicts."""
    from bobbytailor.deterministic.rooms import RoomPolygon
    from bobbytailor.vision.fusion import ROOM_WALL_REFERENCE_FIELD

    room = RoomPolygon(
        polygon_wkt="", area_pt2=10.0, label="", label_source="none",
        candidate_id="ROOM-1", confidence="medium",
    )
    applied = takeoff_pipeline._apply_room_wall_references(
        [room], [{"room_id": "ROOM-1", ROOM_WALL_REFERENCE_FIELD: ["W1"]}]
    )
    assert applied == 1
    assert getattr(room, ROOM_WALL_REFERENCE_FIELD) == ["W1"]


def test_the_request_never_asks_about_a_marker_it_did_not_send(arch_page):
    """The image budget can truncate the partition; the enum must follow it."""
    candidates = {
        "SYM-%d" % i: (50 + 12 * i, 50, 80 + 12 * i, 90) for i in range(45)
    }
    images = render_overlay(arch_page, candidates)
    assert isinstance(images, list) and len(images) == 2
    # Everything drawn across the whole partition is askable ...
    assert takeoff_pipeline._ids_shown_on(images) == set(candidates)
    # ... but a truncated batch narrows the askable set to what it carries.
    first_only = takeoff_pipeline._ids_shown_on(images[:1])
    assert first_only == set(images[0].info["overlay_ids"])
    assert first_only < set(candidates)
    assert takeoff_pipeline._ids_shown_on([]) == set()


@pytest.mark.skipif(not _CROW_PDF.exists(), reason="Crow fixture PDF not available")
def test_the_semantic_pass_sends_the_dependency_ordered_schema(monkeypatch):
    """End to end on a real sheet: ordering, rooms, and zero numeric fields."""
    analyzer = _run_crow_symbol_pass(monkeypatch, lambda bundle: {})
    semantic = next(
        (c for c in analyzer.calls if c["pass_type"] == "semantic"), None
    )
    assert semantic is not None, "the semantic pass must still run"
    schema = semantic["output_schema"]
    order = list(schema["properties"].keys())
    assert order.index("wall_classes") < order.index("regions")
    if "rooms" in order:
        assert order.index("regions") < order.index("rooms")
        room = schema["properties"]["rooms"]["items"]["properties"]
        walls = schema["properties"]["wall_classes"]["items"]["properties"]
        # Every wall a room may cite is one the same request defined above it.
        assert set(room["bounding_wall_ids"]["items"]["enum"]) == set(
            walls["wall_class_id"]["enum"]
        )
    # Every ID asked about was actually MARKED on an image that was sent.
    shown = takeoff_pipeline._ids_shown_on(semantic["images"])
    for level, id_key in (
        ("wall_classes", "wall_class_id"),
        ("regions", "region_id"),
        ("rooms", "room_id"),
    ):
        if level not in schema["properties"]:
            continue
        enum = schema["properties"][level]["items"]["properties"][id_key]["enum"]
        assert set(enum) <= shown, (level, set(enum) - shown)
    # And the whole real-sheet request still carries no numeric field.
    serialized = json.dumps(schema)
    assert "integer" not in serialized
    assert "number" not in serialized


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
