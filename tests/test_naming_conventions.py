"""Offline tests for AI-driven NAMING-CONVENTION extraction + geometry binding.

No API calls anywhere — the analyzer is a stub callable; reading the real Crow
PDF text layer in-test is allowed (and encouraged) to close the offline≠real
gap. Pins:

- naming_convention_schema() carries ZERO numeric fields (recursive check);
- extract_naming_conventions parses a stubbed convention library, returns []
  (never raises) on error, and majority-KEEPS across voted samples;
- extract_naming_text harvests keynotes + abbreviations + detail labels from
  the REAL Crow plan set;
- geometry binding is DRIVEN by the naming library: a structural-grid cluster
  binds to Columns, a perimeter ring to Bollards, wall thickness classes map to
  tilt-up(ext)/CMU with the plan height, ambiguous → needs_review;
- unnamed clusters surface as DISTINCT flagged EA rows (no "Component" blob).
"""
import json
import logging
from pathlib import Path

import pytest

from bobbytailor.vision.schemas import naming_convention_schema
from bobbytailor.vision.object_vocabulary import (
    extract_naming_conventions,
    majority_keep_conventions,
    _tolerant_json_object,
)
from bobbytailor.deterministic.component_library import (
    extract_naming_text,
    distill_naming_text,
    harvest_detail_labels,
    harvest_naming_signal_lines,
    merge_with_naming_conventions,
    normalize_estimator_name,
    apply_estimator_names,
)
from bobbytailor.vision.object_vocabulary import NAMING_CONVENTION_INSTRUCTION
from bobbytailor.vision.fusion import (
    fuse_sheet,
    map_wall_classes_from_library,
    merge_with_provenance,
)
from bobbytailor.pipeline.calculator import apply_estimation_tables
from bobbytailor.pipeline.reporter import _normalize_calculated
from bobbytailor.pipeline.aggregator import aggregate_takeoff, normalize_item_name


CROW_PDF = Path(__file__).parent / "fixtures" / "crow_cass" / "crow_cass_plans.pdf"


# ── helpers ──────────────────────────────────────────────────────────────────


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


def _stub_analyzer(payload):
    """A stub analyzer returning *payload* (dict) for any call."""
    def _call(*args, **kwargs):
        return payload
    return _call


def _summary_from(symbol_groups=None, bundle_extra=None, vocabulary=None,
                  matches=None, wall_height_ft=None, wall_height_source=None):
    """Full offline downstream path with a naming-library vocabulary."""
    bundle = {"sheet_name": "S-101"}
    if symbol_groups is not None:
        bundle["symbol_groups"] = symbol_groups
    if bundle_extra:
        bundle.update(bundle_extra)
    fused = fuse_sheet(
        bundle,
        {"matches": matches or []},
        vocabulary=vocabulary,
        wall_height_ft=wall_height_ft,
        wall_height_source=wall_height_source,
    )
    merged = merge_with_provenance([fused])
    merged["_source_sheet"] = "S-101"
    merged["sheet_type"] = "floor_plan"
    estimates = apply_estimation_tables(merged, project_type="commercial")
    calculated = _normalize_calculated(estimates)
    return aggregate_takeoff(calculated), fused


def _row(summary, item):
    for r in summary:
        if r.get("item") == item:
            return r
    return None


def _filled_grid(cols, rows, step=30.0, size=8.0, origin=(200.0, 200.0)):
    ox, oy = origin
    return [
        (ox + c * step, oy + r * step, ox + c * step + size, oy + r * step + size)
        for r in range(rows) for c in range(cols)
    ]


def _perimeter_ring(n_per_side, step=25.0, size=6.0, origin=(100.0, 100.0)):
    """A hollow rectangular ring of instance bboxes."""
    ox, oy = origin
    boxes = []
    span = n_per_side * step
    for i in range(n_per_side):
        d = i * step
        boxes.append((ox + d, oy, ox + d + size, oy + size))                 # top
        boxes.append((ox + d, oy + span, ox + d + size, oy + span + size))   # bottom
        boxes.append((ox, oy + d, ox + size, oy + d + size))                 # left
        boxes.append((ox + span, oy + d, ox + span + size, oy + d + size))   # right
    return boxes


# ── 1. schema: zero numeric fields ───────────────────────────────────────────


def test_naming_convention_schema_has_no_numeric_fields():
    _assert_no_numeric_types(naming_convention_schema())


def test_naming_convention_schema_thickness_height_are_strings():
    props = naming_convention_schema()["properties"]["objects"]["items"]["properties"]
    assert props["thickness_in"]["type"] == "string"
    assert props["height_ft"]["type"] == "string"


# ── 2. extract_naming_conventions: stub, error, budget ───────────────────────


def _canned_library():
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


def test_extract_naming_conventions_parses_stub():
    objs = extract_naming_conventions(_stub_analyzer(_canned_library()), "/tmp/p.png", "text")
    names = {o["canonical_name"] for o in objs}
    assert names == {"Columns", "Exterior Tilt Up Wall"}
    cols = next(o for o in objs if o["canonical_name"] == "Columns")
    assert cols["binding_hint"] == "structural_grid_symbol"
    assert cols["basis"] == "count"
    ext = next(o for o in objs if o["canonical_name"] == "Exterior Tilt Up Wall")
    assert ext["variant"] == "exterior" and ext["binding_hint"] == "exterior_wall"


def test_extract_naming_conventions_unknown_hint_normalised_to_other():
    payload = {"objects": [{"canonical_name": "X", "binding_hint": "wat", "basis": "bogus"}]}
    objs = extract_naming_conventions(_stub_analyzer(payload), "/tmp/p.png", "t")
    assert objs[0]["binding_hint"] == "other"
    assert objs[0]["basis"] is None


def test_extract_naming_conventions_error_result_returns_empty():
    assert extract_naming_conventions(_stub_analyzer({"error": "boom"}), "/tmp/p.png", "t") == []


def test_extract_naming_conventions_raising_analyzer_returns_empty():
    def _boom(*a, **k):
        raise RuntimeError("model down")
    assert extract_naming_conventions(_boom, "/tmp/p.png", "t") == []


def test_extract_naming_conventions_charges_budget_guard():
    charged = {}

    class _Guard:
        exhausted = False
        def charge(self, usd):
            charged["usd"] = usd

    payload = dict(_canned_library())
    payload["_cost_usd"] = 0.042
    extract_naming_conventions(_stub_analyzer(payload), "/tmp/p.png", "t", guard=_Guard())
    assert charged.get("usd") == 0.042


# ── 3. majority-KEEP across voted samples ────────────────────────────────────


def test_majority_keep_drops_minority_object():
    a = [{"canonical_name": "Columns", "binding_hint": "structural_grid_symbol", "basis": "count"}]
    b = [{"canonical_name": "Columns", "binding_hint": "structural_grid_symbol", "basis": "count"}]
    c = [
        {"canonical_name": "Columns", "binding_hint": "structural_grid_symbol", "basis": "count"},
        {"canonical_name": "Ghost", "binding_hint": "other", "basis": "count"},
    ]
    kept = majority_keep_conventions([a, b, c])
    names = {o["canonical_name"] for o in kept}
    assert "Columns" in names        # 3/3 majority
    assert "Ghost" not in names      # 1/3 minority dropped


def test_majority_keep_single_sample_unchanged():
    a = [{"canonical_name": "Bollards", "binding_hint": "perimeter_jamb_symbol"}]
    assert majority_keep_conventions([a]) == a


# ── 4. comprehensive naming-text extraction (REAL Crow PDF) ──────────────────


@pytest.mark.skipif(not CROW_PDF.is_file(), reason="Crow Cass PDF fixture missing")
def test_extract_naming_text_includes_keynotes_abbr_details_from_crow():
    import fitz
    doc = fitz.open(str(CROW_PDF))
    pages = [{"full_page_text": doc[i].get_text() or ""} for i in range(doc.page_count)]
    doc.close()
    text = extract_naming_text(pages)
    upper = text.upper()
    # Keynotes / general notes that PRINT the takeoff object names.
    assert "BOLLARD" in upper
    assert "INTERIOR COLUMN" in upper
    assert "TILT WALL" in upper or "S.C.C.P" in upper
    assert "36' CLEAR" in upper or "36'" in upper
    # Explicit ABBREVIATIONS section is surfaced.
    assert "=== ABBREVIATIONS ===" in text
    # Detail / section labels are surfaced.
    assert "=== DETAIL / SECTION LABELS ===" in text
    assert "DETAIL" in upper


def test_harvest_detail_labels_drops_pure_refs_keeps_named():
    text = "TYPICAL S.C.C.P. JOINT DETAIL\nDETAIL 7/A-401\nSTAIR SECTION\nDETAIL 3/A-201"
    labels = harvest_detail_labels(text)
    assert "TYPICAL S.C.C.P. JOINT DETAIL" in labels
    assert "STAIR SECTION" in labels
    assert all("A-401" not in lbl for lbl in labels)


def test_extract_naming_text_empty_input_is_empty_string():
    assert extract_naming_text([]) == ""


# ── 5. symbol binding DRIVEN by the naming library ───────────────────────────


def test_structural_grid_binds_to_columns_136_ea():
    groups = [{
        "candidate_id": "SYM-1",
        "count": 136,
        "representative_bbox_pt": (200.0, 200.0, 208.0, 208.0),
        "instance_bboxes_pt": _filled_grid(17, 8),
        "bbox_size_ft": (1.0, 0.4),
        "contained_texts": [],
        "confidence": "medium",
    }]
    vocab = [{"name": "Columns", "basis": "count", "binding_hint": "structural_grid_symbol"}]
    summary, _ = _summary_from(symbol_groups=groups, vocabulary=vocab)
    cols = _row(summary, "Columns")
    assert cols is not None, "structural-grid cluster did not bind to Columns"
    assert float(cols["quantity"]) == 136.0
    assert (cols.get("unit") or "").upper() == "EA"


def test_perimeter_ring_binds_to_bollards():
    groups = [{
        "candidate_id": "SYM-2",
        "count": 56,
        "representative_bbox_pt": (100.0, 100.0, 106.0, 106.0),
        "instance_bboxes_pt": _perimeter_ring(14),
        "bbox_size_ft": (0.8, 0.9),
        "contained_texts": [],
        "confidence": "medium",
    }]
    vocab = [{"name": "Bollards", "basis": "count", "binding_hint": "perimeter_jamb_symbol"}]
    summary, _ = _summary_from(symbol_groups=groups, vocabulary=vocab)
    boll = _row(summary, "Bollards")
    assert boll is not None, "perimeter ring did not bind to Bollards"
    assert float(boll["quantity"]) == 56.0


def test_grid_and_ring_bind_together_columns_and_bollards():
    groups = [
        {
            "candidate_id": "SYM-1", "count": 136,
            "representative_bbox_pt": (200.0, 200.0, 208.0, 208.0),
            "instance_bboxes_pt": _filled_grid(17, 8),
            "bbox_size_ft": (1.0, 0.4), "contained_texts": [], "confidence": "medium",
        },
        {
            "candidate_id": "SYM-2", "count": 56,
            "representative_bbox_pt": (900.0, 900.0, 906.0, 906.0),
            "instance_bboxes_pt": _perimeter_ring(14, origin=(900.0, 900.0)),
            "bbox_size_ft": (0.8, 0.9), "contained_texts": [], "confidence": "medium",
        },
    ]
    vocab = [
        {"name": "Columns", "basis": "count", "binding_hint": "structural_grid_symbol"},
        {"name": "Bollards", "basis": "count", "binding_hint": "perimeter_jamb_symbol"},
    ]
    summary, _ = _summary_from(symbol_groups=groups, vocabulary=vocab)
    assert float(_row(summary, "Columns")["quantity"]) == 136.0
    assert float(_row(summary, "Bollards")["quantity"]) == 56.0


def test_large_item_not_bound_as_bollard_perimeter():
    # A large (8.8 ft) perimeter-ish cluster is NOT a small marker → no bollard bind.
    groups = [{
        "candidate_id": "SYM-4", "count": 40,
        "representative_bbox_pt": (100.0, 100.0, 200.0, 200.0),
        "instance_bboxes_pt": _perimeter_ring(10, step=120.0, size=90.0),
        "bbox_size_ft": (8.8, 8.7), "contained_texts": [], "confidence": "medium",
    }]
    vocab = [{"name": "Bollards", "basis": "count", "binding_hint": "perimeter_jamb_symbol"}]
    summary, _ = _summary_from(symbol_groups=groups, vocabulary=vocab)
    assert _row(summary, "Bollards") is None


# ── 6. wall thickness class → naming-library wall object ──────────────────────


def _wall_bundle():
    """TC1 = thick (12") perimeter, 1714 LF; TC2 = 8", 63 LF. fpp = 1.0."""
    walls = [
        {"thickness_class": "TC1", "thickness_pt": 1.0, "length_pt": 1714.0},
        {"thickness_class": "TC2", "thickness_pt": 8.0 / 12.0, "length_pt": 63.0},
    ]
    return {
        "walls": walls,
        "wall_lf_by_class": {"TC1": 1714.0, "TC2": 63.0},
        "fpp": 1.0,
    }


def _wall_library():
    return [
        {"name": "Exterior Tilt Up Wall", "basis": "wall_area",
         "binding_hint": "exterior_wall", "variant": "exterior"},
        {"name": "CMU Wall", "basis": "wall_area",
         "binding_hint": "masonry_wall", "thickness_in": "8"},
    ]


def test_map_wall_classes_thickness_and_hint():
    mapping = map_wall_classes_from_library(
        {"TC1": 1714.0, "TC2": 63.0},
        {"TC1": 12.0, "TC2": 8.0},
        _wall_library(),
    )
    assert mapping["TC2"][0] == "CMU Wall"          # thickness match (authoritative)
    assert mapping["TC2"][2] is True                # confident
    assert mapping["TC1"][0] == "Exterior Tilt Up Wall"  # dominant → exterior
    assert mapping["TC1"][2] is False               # hint bind → not confident


def test_wall_binding_through_fusion_sf_with_plan_height():
    _, fused = _summary_from(
        bundle_extra=_wall_bundle(),
        vocabulary=_wall_library(),
        wall_height_ft=36.0,
        wall_height_source="plan",
    )
    comps = {c["name"]: c for c in fused["components"]}
    assert "Exterior Tilt Up Wall" in comps
    ext = comps["Exterior Tilt Up Wall"]
    assert ext["unit"] == "SF"
    assert ext["quantity"] == round(1714.0 * 36.0, 1)
    assert ext["needs_review"] is True              # hint bind flagged
    cmu = comps["CMU Wall"]
    assert cmu["unit"] == "SF"
    assert cmu["quantity"] == round(63.0 * 36.0, 1)


def test_ambiguous_wall_class_stays_needs_review():
    # A third thickness class no library object claims → unlabeled needs_review.
    bundle = _wall_bundle()
    bundle["walls"].append(
        {"thickness_class": "TC3", "thickness_pt": 2.0, "length_pt": 300.0}
    )
    bundle["wall_lf_by_class"]["TC3"] = 300.0
    _, fused = _summary_from(
        bundle_extra=bundle, vocabulary=_wall_library(),
        wall_height_ft=36.0, wall_height_source="plan",
    )
    tc3 = next(c for c in fused["components"] if c.get("candidate_id") == "WALL-TC3")
    assert tc3["needs_review"] is True
    assert tc3["unit"] == "LF"                       # never a silent wrong SF bind


# ── 6b. tilt-up = perimeter × height; CMU = small interior class × height ─────


def test_tiltup_wall_binds_to_building_perimeter_times_height():
    # Crow golden: "Internal Tilt up walls" = footprint perimeter (2972 LF) ×
    # 36' clear ≈ 108,443 SF — NOT the thickness-class linework LF.
    bundle = {
        "walls": [{"thickness_class": "TC1", "thickness_pt": 1.0, "length_pt": 300.0}],
        "wall_lf_by_class": {"TC1": 300.0},   # class LF is deliberately NOT the basis
        "fpp": 1.0,
        "footprint": {"perimeter_lf": 2972.0, "area_sf": 397600.0, "confidence": "high"},
    }
    vocab = [
        {"name": "Internal Tilt up walls", "basis": "wall_area",
         "binding_hint": "exterior_wall", "variant": "exterior"},
    ]
    _, fused = _summary_from(
        bundle_extra=bundle, vocabulary=vocab,
        wall_height_ft=36.0, wall_height_source="plan",
    )
    comps = {c["name"]: c for c in fused["components"]}
    tilt = comps["Internal Tilt up walls"]
    assert tilt["unit"] == "SF"
    assert tilt["quantity"] == round(2972.0 * 36.0, 1)   # perimeter × height
    assert abs(tilt["quantity"] - 108443.0) / 108443.0 < 0.03   # within ±3% of golden
    assert "perimeter" in tilt["formula"]


def test_cmu_binds_to_small_interior_class_not_dominant_perimeter():
    # Two ~8" classes: the dominant perimeter (2972 LF) and a small interior
    # pump-room wall (61 LF). CMU must bind to the SMALL one → ~2,204 SF.
    lf = {"TC1": 2972.0, "TC2": 61.0}
    thick = {"TC1": 8.0, "TC2": 8.0}   # identical thickness — LF must break the tie
    wall_objects = [
        {"name": "Internal Tilt up walls", "basis": "wall_area",
         "binding_hint": "exterior_wall", "variant": "exterior"},
        {"name": "CMU Wall", "basis": "wall_area",
         "binding_hint": "masonry_wall", "thickness_in": "8"},
    ]
    mapping = map_wall_classes_from_library(lf, thick, wall_objects)
    assert mapping["TC2"][0] == "CMU Wall"                    # small interior class
    assert mapping["TC1"][0] == "Internal Tilt up walls"     # dominant → tilt-up

    bundle = {
        "walls": [
            {"thickness_class": "TC1", "thickness_pt": 8.0 / 12.0, "length_pt": 2972.0},
            {"thickness_class": "TC2", "thickness_pt": 8.0 / 12.0, "length_pt": 61.0},
        ],
        "wall_lf_by_class": lf, "fpp": 1.0,
        "footprint": {"perimeter_lf": 2972.0, "confidence": "high"},
    }
    _, fused = _summary_from(
        bundle_extra=bundle, vocabulary=wall_objects,
        wall_height_ft=36.0, wall_height_source="plan",
    )
    comps = {c["name"]: c for c in fused["components"]}
    cmu = comps["CMU Wall"]
    assert cmu["quantity"] == round(61.0 * 36.0, 1)
    assert abs(cmu["quantity"] - 2204.0) / 2204.0 < 0.05     # within ±5% of golden


def test_cmu_never_binds_the_only_dominant_class():
    # Only the dominant perimeter class exists — a masonry object must NOT bind
    # to it (ambiguous → stays unclaimed / needs_review, never a giant CMU SF).
    mapping = map_wall_classes_from_library(
        {"TC1": 2972.0},
        {"TC1": 8.0},
        [{"name": "CMU Wall", "basis": "wall_area",
          "binding_hint": "masonry_wall", "thickness_in": "8"}],
    )
    assert "TC1" not in mapping


def test_tiltup_without_perimeter_falls_back_to_lf_and_flags():
    bundle = {
        "walls": [{"thickness_class": "TC1", "thickness_pt": 1.0, "length_pt": 300.0}],
        "wall_lf_by_class": {"TC1": 300.0}, "fpp": 1.0,   # no footprint / perimeter
    }
    vocab = [
        {"name": "Exterior Tilt Up Wall", "basis": "wall_area",
         "binding_hint": "exterior_wall", "variant": "exterior"},
    ]
    _, fused = _summary_from(
        bundle_extra=bundle, vocabulary=vocab,
        wall_height_ft=36.0, wall_height_source="plan",
    )
    ext = next(c for c in fused["components"] if c.get("candidate_id") == "WALL-TC1")
    assert ext["quantity"] == round(300.0 * 36.0, 1)   # class LF fallback
    assert ext["needs_review"] is True
    assert "perimeter" in ext["review_reason"]


# ── 7. unnamed-cluster collapse fix (no "Component" blob) ─────────────────────


def test_two_unnamed_clusters_stay_distinct_flagged_rows():
    groups = [
        {"candidate_id": "SYM-1", "count": 40,
         "representative_bbox_pt": (10.0, 10.0, 16.0, 16.0),
         "instance_bboxes_pt": [(10.0, 10.0, 16.0, 16.0)],
         "contained_texts": [], "confidence": "medium"},
        {"candidate_id": "SYM-2", "count": 12,
         "representative_bbox_pt": (50.0, 50.0, 56.0, 56.0),
         "instance_bboxes_pt": [(50.0, 50.0, 56.0, 56.0)],
         "contained_texts": [], "confidence": "medium"},
    ]
    # No vision labels, no naming library → both stay unnamed but DISTINCT.
    summary, _ = _summary_from(symbol_groups=groups, vocabulary=None)
    qtys = sorted(float(r["quantity"]) for r in summary if r.get("quantity"))
    assert 40.0 in qtys and 12.0 in qtys
    # They must NOT collapse into one "Component" bucket summing 52.
    assert _row(summary, "Component") is None
    flagged = [r for r in summary if r.get("needs_review")]
    assert len(flagged) >= 2


def test_normalize_item_name_generic_component_uses_description():
    n1, _ = normalize_item_name("SYM-1", "component", "EA")
    n2, _ = normalize_item_name("SYM-2", "component", "EA")
    assert n1 == "SYM-1" and n2 == "SYM-2"
    assert n1 != n2


# ── 8. merge: deterministic authoritative, naming fills binding fields ────────


def test_merge_naming_conventions_fills_binding_hint_on_deterministic():
    deterministic = [{"name": "Columns", "aliases": ["COLUMN"], "basis": "count",
                      "unit": "EA", "source": "keynote"}]
    conventions = [{"canonical_name": "Columns", "aliases": ["INTERIOR COLUMN"],
                    "basis": "count", "binding_hint": "structural_grid_symbol",
                    "variant": "", "thickness_in": "", "height_ft": "35"}]
    merged = merge_with_naming_conventions(deterministic, conventions)
    cols = next(e for e in merged if e["name"] == "Columns")
    assert cols["binding_hint"] == "structural_grid_symbol"
    assert cols["height_ft"] == "35"
    assert "INTERIOR COLUMN" in cols["aliases"]     # aliases unioned


def test_merge_naming_conventions_adds_new_object():
    conventions = [{"canonical_name": "Bollards", "aliases": [], "basis": "count",
                    "binding_hint": "perimeter_jamb_symbol", "variant": "",
                    "thickness_in": "", "height_ft": ""}]
    merged = merge_with_naming_conventions([], conventions)
    boll = next(e for e in merged if e["name"] == "Bollards")
    assert boll["binding_hint"] == "perimeter_jamb_symbol"
    assert boll["source"] == "naming_convention"


# ── 9. RESILIENCE: retry-on-invalid, tolerant extract, loud fallback ──────────
# The #1 generalization fix — Bob's returned invalid_json → no manifest → 8%.
# The reader pass must recover a valid manifest on ANY plan (no real API here;
# the analyzer is a stub returning the invalid_json shape analyze_drawing emits).


def _invalid_json_result(raw):
    """The exact error dict analyze_drawing returns on an unrecoverable parse."""
    return {"error": "invalid_json", "raw": raw, "_cost_usd": 0.01}


def test_extract_naming_conventions_retries_invalid_then_valid():
    """Invalid JSON once, valid next → a fresh retry yields the valid library."""
    calls = {"n": 0}

    def _flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _invalid_json_result("not json at all <<<")  # unrecoverable
        return _canned_library()

    objs = extract_naming_conventions(_flaky, "/tmp/p.png", "text")
    assert calls["n"] == 2, "second (fresh) attempt was not made"
    assert {o["canonical_name"] for o in objs} == {"Columns", "Exterior Tilt Up Wall"}


def test_extract_naming_conventions_always_invalid_falls_back_loudly(caplog):
    """Always-invalid → returns [] WITHOUT raising and logs a loud fallback."""
    def _always_invalid(*a, **k):
        return _invalid_json_result("garbage with no braces here")

    with caplog.at_level(logging.WARNING):
        objs = extract_naming_conventions(
            _always_invalid, "/tmp/p.png", "COLUMN BOLLARD S.C.C.P. notes"
        )
    assert objs == []
    assert "FELL BACK to the deterministic library" in caplog.text
    # The failing plan must be VISIBLE — the naming-text fingerprint is logged.
    assert "naming_text[:80]" in caplog.text


def test_extract_naming_conventions_recovers_prose_wrapped_json():
    """A prose/markdown-wrapped JSON blob → tolerant extract recovers it."""
    blob = (
        "Sure! Here is the naming manifest you asked for:\n\n```json\n"
        + json.dumps(_canned_library())
        + "\n```\n\nLet me know if you need anything else."
    )

    def _prose(*a, **k):
        return _invalid_json_result(blob)

    objs = extract_naming_conventions(_prose, "/tmp/p.png", "text")
    assert {o["canonical_name"] for o in objs} == {"Columns", "Exterior Tilt Up Wall"}


def test_tolerant_json_object_variants():
    payload = _canned_library()
    # bare object
    assert _tolerant_json_object(json.dumps(payload))["objects"][0]["canonical_name"] == "Columns"
    # fenced
    assert _tolerant_json_object("```json\n" + json.dumps(payload) + "\n```") is not None
    # prose-wrapped
    assert _tolerant_json_object("blah blah " + json.dumps(payload) + " thanks") is not None
    # unrecoverable
    assert _tolerant_json_object("no json here") is None
    assert _tolerant_json_object("") is None
    assert _tolerant_json_object(None) is None


def test_majority_keep_invalid_vote_is_non_vote():
    """An empty (failed) vote is a NON-VOTE — it must not dilute the majority."""
    valid = [{"canonical_name": "Columns", "binding_hint": "structural_grid_symbol",
              "basis": "count"}]
    # 1 real vote + 1 empty (failed) vote → Columns survives (empty excluded).
    kept = majority_keep_conventions([valid, []])
    assert {o["canonical_name"] for o in kept} == {"Columns"}
    # 2 real + 1 empty → still kept (n counts only the 2 real votes).
    kept2 = majority_keep_conventions([valid, valid, []])
    assert "Columns" in {o["canonical_name"] for o in kept2}


def test_extract_naming_conventions_retry_stops_on_first_success():
    """A valid first result short-circuits — no wasted retries."""
    calls = {"n": 0}

    def _ok(*a, **k):
        calls["n"] += 1
        return _canned_library()

    extract_naming_conventions(_ok, "/tmp/p.png", "text")
    assert calls["n"] == 1


# ── 10. DISTILLED naming text: LEAN, capped, covers all 4 real plans ─────────
# Guards the "works on Crow only" trap: the distilled prompt input for EVERY
# real plan must be non-empty, under the char cap, and carry that plan's own
# printed object nouns. Reading the real PDF text layer in-test is API-free.

_UPLOADS = Path(__file__).parent.parent / "uploads"
_FIXTURES = Path(__file__).parent / "fixtures"

# (label, plan-PDF path, printed object nouns that MUST survive distillation).
# Crow/Bob's have committed fixtures; Chelsea/Moxy read the large real uploads
# (skipped when absent so the suite stays green on a clean checkout).
_PLAN_DIGEST_CASES = [
    ("crow", _FIXTURES / "crow_cass" / "crow_cass_plans.pdf",
     ["column", "bollard", "s.c.c.p"]),
    ("bobs", _FIXTURES / "bobs_discount" / "bobs_discount_plans.pdf",
     ["cmu", "gas", "lintel", "eifs"]),
    ("chelsea", _UPLOADS / "Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf",
     ["column", "stair"]),
    ("moxy", _UPLOADS / "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
     ["column", "gas", "elevator"]),
]

_DISTILL_CAP = 15000


@pytest.mark.parametrize("label,path,nouns", _PLAN_DIGEST_CASES)
def test_distilled_naming_text_covers_all_four_plans(label, path, nouns):
    if not path.is_file():
        pytest.skip("{} plan PDF not present: {}".format(label, path))
    import fitz
    doc = fitz.open(str(path))
    pages = [{"full_page_text": doc[i].get_text() or ""} for i in range(doc.page_count)]
    doc.close()

    digest = distill_naming_text(pages)
    assert digest, "{}: distilled naming text is empty".format(label)
    assert len(digest) <= _DISTILL_CAP, \
        "{}: digest {} chars exceeds the {} cap".format(label, len(digest), _DISTILL_CAP)
    low = digest.lower()
    for noun in nouns:
        assert noun in low, \
            "{}: distilled digest is missing printed object noun {!r}".format(label, noun)


def test_distill_naming_text_empty_input_is_empty_string():
    assert distill_naming_text([]) == ""
    assert distill_naming_text([""]) == ""


def test_distill_naming_text_truncates_with_marker():
    # Many unique naming-signal lines → over a tiny cap → truncated with marker.
    body = "\n".join(
        "COLUMN wall bollard CMU detail line {} SCHEDULE".format(i)
        for i in range(2000)
    )
    digest = distill_naming_text([body], max_chars=1500)
    marker = "… [naming text truncated]"
    assert marker in digest
    assert len(digest) <= 1500 + len("\n" + marker)


def test_harvest_naming_signal_lines_keeps_only_naming_lines():
    text = (
        "COLUMN GRID LAYOUT\n"
        "THE QUICK BROWN FOX JUMPED\n"        # no naming signal → dropped
        "PROVIDE BOLLARDS AT ALL DOCK DOORS\n"
        "SEE ARCHITECT FOR COLORS\n"          # no naming signal → dropped
        "8\" CMU MASONRY WALL\n"
    )
    lines = harvest_naming_signal_lines(text)
    joined = " | ".join(lines).lower()
    assert "column" in joined and "bollard" in joined and "cmu" in joined
    assert "quick brown fox" not in joined
    assert "see architect for colors" not in joined


# ── 11. ESTIMATOR take-off name normalization (deterministic safety net) ──────
# The dominant remaining accuracy gap: quantities are correct but named with the
# plan's raw label (e.g. "S.C.C.P.") instead of the estimator take-off term
# ("Tilt Up Wall"), so the scorer can't match. This safety net maps the raw
# plan vocabulary to the standard take-off item name (general, not project-
# specific), preserving the plan term as an alias so binding is unaffected.


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("S.C.C.P.", "Tilt Up Wall"),
        ("site cast concrete panel", "Tilt Up Wall"),
        ("tilt wall", "Tilt Up Wall"),
        ("Exterior Tilt-Up Panel", "Tilt Up Wall"),
        ("metal roof deck", "Exposed Structure"),
        ("exposed roof structure", "Exposed Structure"),
        ("concrete slab on metal deck", "Exposed Structure"),
        ("roof assembly", "Exposed Structure"),
        ("polished slab on grade", "Sealed Concrete"),
        ("sealed concrete slab", "Sealed Concrete"),
        ('8" CMU wall', "CMU Wall"),
        ("concrete masonry unit", "CMU Wall"),
        ("hollow metal door", "Doors-HM"),
    ],
)
def test_normalize_estimator_name_maps_to_takeoff_terms(raw, expected):
    canonical, _ = normalize_estimator_name(raw)
    assert canonical == expected


@pytest.mark.parametrize(
    "gibberish",
    ["Zorpt角 widget", "Purple Nurple Assembly", "Ladder", "Columns", "Bollards"],
)
def test_normalize_estimator_name_leaves_unknown_unchanged(gibberish):
    # Unknown / already-good names must never be falsely remapped.
    canonical, aliases = normalize_estimator_name(gibberish)
    assert canonical == gibberish


def test_normalize_estimator_name_preserves_plan_term_as_alias():
    # The plan prints "S.C.C.P." next to the wall — after normalization the plan
    # term must remain an alias so a drawing-text lookup still resolves the wall.
    canonical, aliases = normalize_estimator_name("S.C.C.P.", ["site cast concrete panel"])
    assert canonical == "Tilt Up Wall"
    assert "S.C.C.P." in aliases                     # plan term retained
    assert "site cast concrete panel" in aliases     # existing alias kept


def test_normalize_estimator_name_via_alias_match():
    # A mislabelled canonical is rescued when a correct alias carries the signal.
    canonical, aliases = normalize_estimator_name("Wall Panel Type A", ["S.C.C.P."])
    assert canonical == "Tilt Up Wall"
    assert "Wall Panel Type A" in aliases


def test_apply_estimator_names_rewrites_library_entries():
    entries = [
        {"name": "S.C.C.P.", "aliases": [], "basis": "wall_area", "unit": "SF"},
        {"name": "METAL ROOF DECK", "aliases": [], "basis": "roof_area", "unit": "SF"},
        {"name": "Ladder", "aliases": [], "basis": "count", "unit": "EA"},
    ]
    out = apply_estimator_names(entries)
    by = {e["name"]: e for e in out}
    assert "Tilt Up Wall" in by
    assert "Exposed Structure" in by
    assert "Ladder" in by                            # unmatched name untouched
    # Plan term preserved as an alias for drawing-text binding.
    assert "S.C.C.P." in by["Tilt Up Wall"]["aliases"]
    # Basis (classified from the plan's own vocabulary) survives the rename.
    assert by["Tilt Up Wall"]["basis"] == "wall_area"


def test_merge_naming_conventions_emits_estimator_canonical_with_plan_alias():
    # A naming pass that (wrongly) returns the plan's raw label as canonical is
    # normalized to the estimator take-off term at the library level, with the
    # plan term preserved as an alias.
    conventions = [
        {"canonical_name": "S.C.C.P.", "aliases": ["TILT PANEL"], "basis": "wall_area",
         "binding_hint": "exterior_wall", "variant": "exterior",
         "thickness_in": "", "height_ft": "36"},
    ]
    merged = merge_with_naming_conventions([], conventions)
    entry = next(e for e in merged if e["name"] == "Tilt Up Wall")
    assert entry["binding_hint"] == "exterior_wall"      # binding field preserved
    assert entry["height_ft"] == "36"
    assert "S.C.C.P." in entry["aliases"]                # plan term retained
    assert not any(e["name"] == "S.C.C.P." for e in merged)


# ── 12. prompt: estimator-naming guidance + canonical-vs-alias rule ───────────


def test_naming_prompt_instructs_estimator_standard_canonical_names():
    text = NAMING_CONVENTION_INSTRUCTION.lower()
    # Canonical = the standard estimator take-off item name (not the raw label).
    assert "take-off item name" in text
    assert "not the plan's raw label" in text or "not the plan" in text
    # The canonical-vs-alias rule and a worked estimator mapping are present.
    assert "aliases" in text
    assert "tilt up wall" in text
    assert "exposed structure" in text
    # Semantic-only discipline is still asserted.
    assert "never invent a quantity" in text


# ── 13. precedence: a human learned correction OUTRANKS estimator normalization


class _StubLearned:
    """Minimal LearnedContext stand-in exposing lookup_name (human corrections)."""

    def __init__(self, mapping):
        self._map = {k.strip().lower(): v for k, v in mapping.items()}

    def lookup_name(self, raw):
        return self._map.get((raw or "").strip().lower())


_SCCP_DESC = "exterior site cast concrete panel"


def test_learned_correction_outranks_estimator_normalization():
    # The library resolves the site-cast-panel wall text to the estimator term
    # "Tilt Up Wall" (plan term preserved as an alias); a human previously
    # renamed that exact text to something else. The learned rename must win
    # (aggregator precedence: learned > library > static).
    library = [{"name": "Tilt Up Wall", "aliases": ["site cast concrete panel"],
                "basis": "wall_area", "unit": "SF"}]
    learned = _StubLearned({_SCCP_DESC: ("Internal Tilt up walls", "SF")})
    items = [{
        "description": _SCCP_DESC,
        "item_type": "wall",
        "calculated_quantity": 106997.0,
        "calculated_unit": "SF",
    }]
    summary = aggregate_takeoff(items, learned=learned, library=library)
    rows = [r for r in summary if r["item"] != "Mobilization"]
    assert len(rows) == 1
    assert rows[0]["item"] == "Internal Tilt up walls"   # human correction wins
    assert rows[0]["source"] == "learned"


def test_library_estimator_name_beats_raw_label_without_learning():
    # No learned correction → the library's estimator take-off name is used
    # (authoritative over the raw plan label the vision text carried).
    library = [{"name": "Tilt Up Wall", "aliases": ["site cast concrete panel"],
                "basis": "wall_area", "unit": "SF"}]
    items = [{
        "description": _SCCP_DESC,
        "item_type": "wall",
        "calculated_quantity": 106997.0,
        "calculated_unit": "SF",
    }]
    summary = aggregate_takeoff(items, library=library)
    rows = [r for r in summary if r["item"] != "Mobilization"]
    assert len(rows) == 1
    assert rows[0]["item"] == "Tilt Up Wall"
    assert rows[0]["source"] == "library"
