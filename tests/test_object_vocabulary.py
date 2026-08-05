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


# ── 24-05: the persisted vocabulary (V4-DET-02/04, defect F3) ────────────────
#
# The project-level naming pass was re-run against the API on EVERY run, so the
# object list the deterministic wall classifier binds against changed between
# runs — `Metal Downspout` on one, `Metal Downspouts` on the next. It is also
# the dominant repeat-run cost: the two saved paid runs charge $0.422 of a
# $0.599 run to the project-level passes.
#
# Both claims reduce to ONE observable thing offline: the analyzer CALL COUNT.
# No dollar figure is asserted — the saving is a consequence of the call count,
# and the call count is what a free test can actually see.
#
# Every test here points the learning store at a tmp path. The developer's real
# store is never read or written (the isolation discipline plan 22-01 landed for
# the output directory).

import pytest

from bobbytailor.learning import store as learning_store
from bobbytailor.pipeline.takeoff_pipeline import _canonicalise_persisted_vocabulary


@pytest.fixture()
def isolated_learning_store(tmp_path, monkeypatch):
    """Point the learning store at an isolated tmp DB (schema re-inits per path)."""
    db_path = tmp_path / "learning.db"
    monkeypatch.setattr(learning_store, "LEARNING_DB_PATH", db_path)
    monkeypatch.setattr(learning_store, "_initialized_for", None)
    return db_path


class _CountingAnalyzer:
    """Analyzer stub that COUNTS its invocations. No API, no credential."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def __call__(self, image_path, sheet_name, **kwargs):
        self.calls += 1
        # Fresh copy per call — the pass mutates what it parses.
        return json.loads(json.dumps(self._payload))


def _naming_payload():
    """A canned naming-convention library.

    Both names are canonicalisation IDENTITIES (neither matches an
    ITEM_NAME_MAP rule that would rewrite it), so the second run's fold is a
    no-op and `second == first` is a literal equality rather than an equality
    that happens to survive a rewrite. The fold itself is proven separately by
    the canonicalisation test below.
    """
    return {
        "objects": [
            {
                "canonical_name": "Columns",
                "aliases": ["COLUMN", "INTERIOR COLUMN"],
                "basis": "count",
                "binding_hint": "structural_grid_symbol",
                "variant": "",
                "thickness_in": "",
                "height_ft": "35",
            },
            {
                "canonical_name": "Exterior Tilt Up Wall",
                "aliases": ["S.C.C.P.", "TILT WALL PANEL"],
                "basis": "wall_area",
                "binding_hint": "exterior_wall",
                "variant": "exterior",
                "thickness_in": "",
                "height_ft": "36",
            },
        ]
    }


def test_persisted_vocabulary_is_preferred(isolated_learning_store):
    """A repeat run makes ZERO additional calls and gets the SAME object list.

    This is the determinism claim (identical list) and the cost claim (no
    additional call) in one assertion, because they are the same fact: the
    list only changed between runs BECAUSE it was re-derived.
    """
    analyzer = _CountingAnalyzer(_naming_payload())
    first_pipeline = TakeoffPipeline(analyzer=analyzer)
    assert first_pipeline._settings.learning_enabled, (
        "the persisted vocabulary is gated on learning_enabled; a disabled "
        "config would make this test pass by never storing anything"
    )

    first = first_pipeline._build_naming_conventions(
        "/tmp/plan.png", "KEYNOTES: ...", None, project_key="proj-a"
    )
    # The stub really was the source — otherwise 'no additional calls' below
    # would be true of a test that never called anything.
    assert analyzer.calls > 0
    assert [o["canonical_name"] for o in first] == [
        "Columns", "Exterior Tilt Up Wall",
    ]
    calls_after_first_run = analyzer.calls

    # ... and the derivation was stored, under this project key only.
    stored = learning_store.load_project_vocabulary(
        "proj-a", kind=learning_store.VOCAB_KIND_NAMING_CONVENTIONS
    )
    assert len(stored) == len(first)

    second_pipeline = TakeoffPipeline(analyzer=analyzer)
    second = second_pipeline._build_naming_conventions(
        "/tmp/plan.png", "KEYNOTES: ...", None, project_key="proj-a"
    )

    # THE cost claim: not "fewer calls" — zero additional calls.
    assert analyzer.calls == calls_after_first_run
    # THE determinism claim: the same object list, field for field.
    assert second == first


def test_persisted_vocabulary_is_not_reused_across_projects(
    isolated_learning_store,
):
    """A sibling project derives its own — the snapshot is per-project (T-24-20).

    Without this, 'zero additional calls' above could be satisfied by a global
    snapshot that every project inherits, which is a naming leak rather than a
    determinism fix.
    """
    analyzer = _CountingAnalyzer(_naming_payload())
    pipeline = TakeoffPipeline(analyzer=analyzer)
    pipeline._build_naming_conventions(
        "/tmp/plan.png", "t", None, project_key="proj-a"
    )
    calls_after_proj_a = analyzer.calls

    pipeline._build_naming_conventions(
        "/tmp/plan.png", "t", None, project_key="proj-b"
    )
    assert analyzer.calls > calls_after_proj_a

    # A run with NO project key never persists and never reuses.
    calls_after_proj_b = analyzer.calls
    pipeline._build_naming_conventions("/tmp/plan.png", "t", None)
    assert analyzer.calls > calls_after_proj_b
    assert learning_store.load_project_vocabulary(
        "", kind=learning_store.VOCAB_KIND_NAMING_CONVENTIONS
    ) == []


def test_persisted_vocabulary_is_canonicalised_on_read(isolated_learning_store):
    """A split spelling already in the store folds and is never authoritative.

    Rows written before 24-03 landed can hold BOTH spellings of one object —
    the singular/plural split defect F2 produced. Promoting that to authority
    would make persistence worse than the defect it fixes: the split would stop
    being a per-run accident and become a permanent property of the project.
    """
    learning_store.save_project_vocabulary(
        "proj-split",
        [
            {"canonical_name": "Bollard", "aliases": ["BOL"], "basis": "count"},
            {"canonical_name": "Bollards", "aliases": ["B"], "basis": "count"},
            {"canonical_name": "Dock Bumper", "aliases": [], "basis": "count"},
        ],
        kind=learning_store.VOCAB_KIND_NAMING_CONVENTIONS,
    )

    analyzer = _CountingAnalyzer(_naming_payload())
    pipeline = TakeoffPipeline(analyzer=analyzer)
    loaded = pipeline._build_naming_conventions(
        "/tmp/plan.png", "t", None, project_key="proj-split"
    )

    names = [o["canonical_name"] for o in loaded]
    # ONE entry for the object, under the canonical form 24-03 established.
    assert names.count("Bollards") == 1
    assert "Bollard" not in names
    # THE LOAD-BEARING NEGATIVE: a synonym is not a plural. `Dock Bumper`
    # matches ITEM_NAME_MAP's `dock.*bumper` rule whose canonical form is
    # `Dock Leveler`, and it must still resolve to ITSELF. If this ever fails,
    # the fold has become a synonym mapper and a genuinely distinct object is
    # disappearing from client reports.
    assert names == ["Bollards", "Dock Bumper"]
    # Nothing was deleted — the loser's spelling survives as an alias.
    bollards = loaded[0]
    assert "BOL" in bollards["aliases"] and "B" in bollards["aliases"]
    # And the fold cost no API call.
    assert analyzer.calls == 0


def test_persisted_vocabulary_fold_is_idempotent(isolated_learning_store):
    """Folding on read twice yields the same list — which is WHY no migration.

    24-RESEARCH section 13 forbids a destructive migration against the store.
    Canonicalising at the point of use is the stated alternative, and it is only
    a valid alternative if it is idempotent.
    """
    once = _canonicalise_persisted_vocabulary([
        {"canonical_name": "Bollard", "aliases": ["BOL"], "basis": "count"},
        {"canonical_name": "Bollards", "aliases": [], "basis": "count"},
    ])
    assert _canonicalise_persisted_vocabulary(once) == once


def test_persisted_vocabulary_broken_store_still_derives(
    isolated_learning_store, monkeypatch
):
    """A store that raises costs the run its saving, never the run itself."""
    def _boom(*a, **k):
        raise RuntimeError("learning db on fire")

    import bobbytailor.pipeline.takeoff_pipeline as tp
    monkeypatch.setattr(tp, "load_project_vocabulary", _boom)
    monkeypatch.setattr(tp, "save_project_vocabulary", _boom)

    analyzer = _CountingAnalyzer(_naming_payload())
    pipeline = TakeoffPipeline(analyzer=analyzer)
    result = pipeline._build_naming_conventions(
        "/tmp/plan.png", "t", None, project_key="proj-a"
    )
    assert [o["canonical_name"] for o in result] == [
        "Columns", "Exterior Tilt Up Wall",
    ]
    assert analyzer.calls > 0
