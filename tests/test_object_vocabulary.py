"""Offline tests for the autonomous project-vocabulary pass (hybrid naming).

No API calls anywhere — the analyzer is a stub callable. Pins:
- vocabulary_schema() carries zero numeric fields and accepts a sample list;
- build_project_vocabulary returns parsed object dicts from a stub, and
  returns [] (never raises) on a model-error result;
- the symbol-gallery candidate merge includes vocabulary labels alongside
  deterministic schedule labels (the wiring seam _run_sheet_vector uses).
"""
import json

from bobbytailor.vision.schemas import vocabulary_schema
from bobbytailor.vision.object_vocabulary import (
    build_project_vocabulary,
    build_vocabulary_hint,
    vocabulary_labels,
)
from bobbytailor.pipeline.takeoff_pipeline import (
    TakeoffPipeline,
    _dedupe_labels,
    _legend_labels_from_schedules,
    _MAX_LEGEND_LABELS,
)


# ── schema: no numbers + accepts a sample object list ────────────────────────


def _assert_no_numeric_types(node):
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


def _validate_against(schema, payload):
    """Minimal structural validation: required keys, additionalProperties,
    enum membership, and array/string typing — enough to prove a sample
    conforms without the (absent) jsonschema dependency."""
    node_type = schema.get("type")
    if "enum" in schema:
        assert payload in schema["enum"], (payload, schema["enum"])
        return
    if node_type == "object":
        assert isinstance(payload, dict), payload
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        assert required.issubset(payload.keys()), (required, payload.keys())
        if schema.get("additionalProperties") is False:
            assert set(payload.keys()).issubset(props.keys()), payload
        for key, subschema in props.items():
            if key in payload:
                _validate_against(subschema, payload[key])
    elif node_type == "array":
        assert isinstance(payload, list), payload
        for item in payload:
            _validate_against(schema["items"], item)
    elif node_type == "string":
        assert isinstance(payload, str), payload


def test_vocabulary_schema_has_no_numeric_fields():
    schema = vocabulary_schema()
    _assert_no_numeric_types(schema)
    serialized = json.dumps(schema)
    assert '"type": "integer"' not in serialized
    assert '"type": "number"' not in serialized


def test_vocabulary_schema_strict_objects_all_required():
    schema = vocabulary_schema()
    item = schema["properties"]["objects"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"].keys())
    assert item["properties"]["measure"]["enum"] == [
        "count",
        "linear",
        "wall_area",
        "floor_area",
        "roof_area",
    ]


def test_vocabulary_schema_accepts_sample_object_list():
    schema = vocabulary_schema()
    sample = {
        "objects": [
            {"name": "Column", "measure": "count", "unit": "ea", "aliases": ["COL"]},
            {"name": "Sealed Concrete", "measure": "floor_area", "unit": "sf", "aliases": []},
            {"name": "Exposed Structure", "measure": "roof_area", "unit": "sf", "aliases": []},
            {"name": "CMU Wall", "measure": "wall_area", "unit": "sf", "aliases": ["CMU"]},
            {"name": "Curb", "measure": "linear", "unit": "lf", "aliases": []},
        ]
    }
    _validate_against(schema, sample)


# ── build_project_vocabulary: stub analyzer, never raises ────────────────────


class _StubAnalyzer:
    """Records the call and returns a canned payload (no API)."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def __call__(self, image_path, sheet_name, **kwargs):
        self.calls.append((image_path, sheet_name, kwargs))
        return dict(self._payload)


def test_build_project_vocabulary_returns_object_dicts():
    payload = {
        "objects": [
            {"name": "Column", "measure": "count", "unit": "ea", "aliases": ["COL"]},
            {"name": "Bollard", "measure": "count", "unit": "ea", "aliases": []},
        ],
        "_cost_usd": 0.01,
    }
    analyzer = _StubAnalyzer(payload)
    objects = build_project_vocabulary(analyzer, "/tmp/plan.png", "KEYNOTES: ...")
    assert [o["name"] for o in objects] == ["Column", "Bollard"]
    # The pass routes as pass_type="vocabulary" and forwards plan text as hint.
    _, sheet_name, kwargs = analyzer.calls[0]
    assert kwargs["pass_type"] == "vocabulary"
    assert kwargs["output_schema"] == vocabulary_schema()
    assert "estimator" in kwargs["user_hint"].lower()


def test_build_project_vocabulary_error_result_returns_empty():
    analyzer = _StubAnalyzer({"error": "api down"})
    assert build_project_vocabulary(analyzer, "/tmp/plan.png", "text") == []


def test_build_project_vocabulary_raising_analyzer_returns_empty():
    def _boom(*a, **k):
        raise RuntimeError("network")

    assert build_project_vocabulary(_boom, "/tmp/plan.png", "text") == []


def test_build_project_vocabulary_charges_budget_guard():
    class _Guard:
        exhausted = False

        def __init__(self):
            self.charged = []

        def charge(self, amount):
            self.charged.append(amount)

    guard = _Guard()
    analyzer = _StubAnalyzer({"objects": [], "_cost_usd": 0.02})
    build_project_vocabulary(analyzer, "/tmp/p.png", "t", guard=guard)
    assert guard.charged == [0.02]


def test_build_project_vocabulary_skips_when_guard_exhausted():
    class _Guard:
        exhausted = True

        def charge(self, amount):  # pragma: no cover - must not be called
            raise AssertionError("should not charge an exhausted guard")

    analyzer = _StubAnalyzer({"objects": [{"name": "Column"}]})
    assert build_project_vocabulary(analyzer, "/tmp/p.png", "t", guard=_Guard()) == []
    assert analyzer.calls == []


def test_vocabulary_labels_flattens_names_and_aliases_deduped():
    objects = [
        {"name": "Hollow Metal", "aliases": ["HM", "hm"]},
        {"name": "column", "aliases": ["COL"]},
        {"name": "Column", "aliases": []},  # case-insensitive dup of "column"
    ]
    labels = vocabulary_labels(objects)
    assert labels == ["Hollow Metal", "HM", "column", "COL"]


def test_build_vocabulary_hint_includes_instruction_and_text():
    hint = build_vocabulary_hint("KEYNOTES: HM = Hollow Metal")
    assert "estimator" in hint.lower()
    assert "KEYNOTES" in hint
    # Empty plan text still yields the instruction.
    assert build_vocabulary_hint("") == build_vocabulary_hint(None)


# ── merge seam: vocabulary labels join the gallery candidate list ────────────


def test_gallery_candidate_merge_includes_vocab_labels():
    """The exact expression _run_sheet_vector uses to build legend_labels."""
    schedules = [
        {"rows": [
            {"TYPE": "Door A"},
            {"TYPE": "Door B"},
        ]}
    ]
    vocab_labels = ["Column", "Bollard", "door a"]  # 'door a' dup schedule label
    merged = _dedupe_labels(
        _legend_labels_from_schedules(schedules) + vocab_labels
    )
    assert "Door A" in merged
    assert "Column" in merged
    assert "Bollard" in merged
    # case-insensitive dedupe drops the vocab 'door a' duplicate
    assert sum(1 for m in merged if m.lower() == "door a") == 1


def test_dedupe_labels_caps_and_preserves_order():
    labels = ["Item%d" % i for i in range(_MAX_LEGEND_LABELS + 20)]
    capped = _dedupe_labels(labels)
    assert len(capped) == _MAX_LEGEND_LABELS
    assert capped[0] == "Item0"


def test_pipeline_stores_vocab_labels_and_merges_via_helper():
    """Pipeline seam: with vocab labels set, the gallery candidate expression
    (schedule labels + self._project_vocab_labels) includes both."""
    pipeline = TakeoffPipeline(analyzer=lambda *a, **k: {})
    assert pipeline._project_vocab_labels == []
    pipeline._project_vocab_labels = ["Column", "Bollard"]
    schedules = [{"rows": [{"NAME": "Door"}]}]
    legend_labels = _dedupe_labels(
        _legend_labels_from_schedules(schedules)
        + list(getattr(pipeline, "_project_vocab_labels", []) or [])
    )
    assert "Door" in legend_labels
    assert "Column" in legend_labels
    assert "Bollard" in legend_labels
