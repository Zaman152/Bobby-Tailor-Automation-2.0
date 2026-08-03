"""Layer-3 fusion tests (21-12, V3-ACC-01) — all offline, zero API calls.

Pins the fusion protocol contract:
- merge precedence follows PROVENANCE_RANK across all 5 provenances;
- the hard no-overwrite guard (historical CMU 17-vs-2,204 SF regression);
- fuse_sheet ID grounding (labels attach to deterministic quantities only,
  out-of-registry IDs rejected + audited);
- the ReplayAnalyzer record/replay harness and its TakeoffPipeline seam.
"""
from __future__ import annotations

import itertools
import json

import pytest

from bobbytailor.vision.fusion import (
    DEFAULT_PROVENANCE,
    DETERMINISTIC_PROVENANCES,
    PROVENANCE_RANK,
    build_registry,
    fuse_sheet,
    merge_with_provenance,
)
from tests.replay_analyzer import REPLAY_RECORD_ENV, ReplayAnalyzer


def _component(name, quantity, unit="SF", provenance=None, confidence="high", **extra):
    comp = {"name": name, "quantity": quantity, "unit": unit, "confidence": confidence}
    if provenance is not None:
        comp["provenance"] = provenance
    comp.update(extra)
    return comp


# ── PROVENANCE_RANK shape ─────────────────────────────────────────────────────


def test_provenance_rank_exactly_five_keys_geometry_highest():
    assert set(PROVENANCE_RANK) == {
        "geometry",
        "text_layer",
        "schedule_table",
        "learned",
        "vision_ensemble",
    }
    assert PROVENANCE_RANK["geometry"] == max(PROVENANCE_RANK.values())
    assert (
        PROVENANCE_RANK["geometry"]
        > PROVENANCE_RANK["text_layer"]
        > PROVENANCE_RANK["schedule_table"]
        > PROVENANCE_RANK["learned"]
        > PROVENANCE_RANK["vision_ensemble"]
    )
    assert DEFAULT_PROVENANCE == "vision_ensemble"
    assert DETERMINISTIC_PROVENANCES == {"geometry", "text_layer", "schedule_table"}


# ── Merge precedence matrix (all 5 ranks, both merge orders) ─────────────────


@pytest.mark.parametrize(
    "high_prov,low_prov",
    list(itertools.combinations(sorted(PROVENANCE_RANK, key=PROVENANCE_RANK.get, reverse=True), 2)),
)
def test_merge_precedence_matrix(high_prov, low_prov):
    """For every provenance pair, the higher rank wins in either merge order."""
    high = {"components": [_component("Slab", 1000, provenance=high_prov)]}
    low = {"components": [_component("Slab", 7, provenance=low_prov)]}

    for order in ((high, low), (low, high)):
        merged = merge_with_provenance(list(order))
        assert len(merged["components"]) == 1
        winner = merged["components"][0]
        assert winner["quantity"] == 1000, (high_prov, low_prov, order is (low, high))
        assert winner["provenance"] == high_prov


def test_cmu_17_vs_2204_regression():
    """Historical failure: vision said CMU=17 SF, geometry measured 2,204 SF.

    The merged result must carry the geometry quantity, and the discarded
    vision claim must land in the fusion_rejected audit list.
    """
    vision = {
        "components": [
            _component("CMU Wall", 17, provenance="vision_ensemble", confidence="high")
        ]
    }
    geometry = {
        "components": [
            _component("cmu wall", 2204, provenance="geometry", confidence="high")
        ]
    }
    for order in ((vision, geometry), (geometry, vision)):
        merged = merge_with_provenance(list(order))
        assert len(merged["components"]) == 1
        cmu = merged["components"][0]
        assert cmu["quantity"] == 2204
        assert cmu["unit"] == "SF"
        assert cmu["provenance"] == "geometry"
        rejections = merged["fusion_rejected"]
        assert len(rejections) == 1
        assert rejections[0]["quantity"] == 17
        assert rejections[0]["provenance"] == "vision_ensemble"
        assert rejections[0]["rejected_by"] == "geometry"
        assert rejections[0]["reason"] == "vision_quantity_blocked"


def test_vision_cannot_fill_null_deterministic_quantity():
    """The old merge_passes count-pass upgrade path is structurally closed:
    even a high-confidence vision number may not fill a deterministic None."""
    geometry = {
        "components": [
            _component("Bollard", None, unit="EA", provenance="geometry", confidence="medium")
        ]
    }
    vision = {
        "components": [
            _component("bollard", 17, unit="EA", provenance="vision_ensemble", confidence="high")
        ]
    }
    merged = merge_with_provenance([geometry, vision])
    assert merged["components"][0]["quantity"] is None
    assert merged["components"][0]["provenance"] == "geometry"
    assert any(r["reason"] == "vision_quantity_blocked" for r in merged["fusion_rejected"])


def test_equal_rank_higher_confidence_wins_then_first_seen():
    low_conf = {"components": [_component("Door", 3, unit="EA", provenance="schedule_table", confidence="medium")]}
    high_conf = {"components": [_component("Door", 5, unit="EA", provenance="schedule_table", confidence="high")]}
    merged = merge_with_provenance([low_conf, high_conf])
    assert merged["components"][0]["quantity"] == 5
    assert merged["components"][0]["confidence"] == "high"

    # Equal rank AND equal confidence → first-seen wins.
    first = {"components": [_component("Window", 4, unit="EA", provenance="schedule_table", confidence="high")]}
    second = {"components": [_component("window", 9, unit="EA", provenance="schedule_table", confidence="high")]}
    merged = merge_with_provenance([first, second])
    assert merged["components"][0]["quantity"] == 4


def test_missing_provenance_defaults_to_vision_ensemble():
    unmarked = {"components": [_component("Stair", 16, unit="EA")]}  # no provenance
    geometry = {"components": [_component("stair", 10, unit="EA", provenance="geometry")]}
    merged = merge_with_provenance([unmarked, geometry])
    winner = merged["components"][0]
    assert winner["quantity"] == 10
    assert winner["provenance"] == "geometry"
    # And a lone unmarked component surfaces with the default floor applied.
    solo = merge_with_provenance([unmarked])
    assert solo["components"][0]["provenance"] == "vision_ensemble"


def test_loser_semantic_fields_absorbed_without_touching_quantity():
    geometry = {
        "components": [
            _component("cmu wall", 2204, provenance="geometry", confidence="high")
        ]
    }
    vision = {
        "components": [
            _component(
                "CMU Wall",
                17,
                provenance="vision_ensemble",
                confidence="high",
                notes="8-inch block per wall legend",
            )
        ]
    }
    merged = merge_with_provenance([geometry, vision])
    winner = merged["components"][0]
    assert winner["quantity"] == 2204 and winner["unit"] == "SF"
    assert winner["notes"] == "8-inch block per wall legend"  # semantic field absorbed
    assert winner["name"] == "CMU Wall"  # better casing adopted
    assert winner["provenance"] == "geometry"


def test_merge_keeps_needs_review_and_vote_metadata():
    ensemble = {
        "components": [
            _component(
                "Sprinkler Head",
                240,
                unit="EA",
                provenance="vision_ensemble",
                confidence="medium",
                needs_review=True,
                votes=[236, 240, 244],
            )
        ]
    }
    merged = merge_with_provenance([ensemble])
    comp = merged["components"][0]
    assert comp["needs_review"] is True
    assert comp["votes"] == [236, 240, 244]
    assert comp["provenance"] == "vision_ensemble"


def test_merge_carries_metadata_schedules_and_input_rejections():
    first = {
        "components": [],
        "_source_sheet": "A2.1",
        "schedules": [{"name": "Door Schedule"}],
        "fusion_rejected": [{"candidate_id": "SYM-999", "reason": "unknown_candidate_id"}],
    }
    second = {"components": [], "schedules": [{"name": "Room Areas"}]}
    merged = merge_with_provenance([first, second])
    assert merged["_source_sheet"] == "A2.1"
    assert [s["name"] for s in merged["schedules"]] == ["Door Schedule", "Room Areas"]
    assert merged["fusion_rejected"][0]["candidate_id"] == "SYM-999"


# ── fuse_sheet ────────────────────────────────────────────────────────────────

_FPP = 20.0 / 72.0  # 1" = 20' → feet per PDF point


def _bundle():
    return {
        "sheet_name": "A2.1",
        "fpp": _FPP,
        "symbol_groups": [
            {
                "candidate_id": "SYM-1",
                "count": 136,
                "representative_bbox_pt": (100.0, 100.0, 140.0, 140.0),
                "instance_bboxes_pt": [(100.0, 100.0, 140.0, 140.0)],
                "contained_texts": [],
                "confidence": "high",
                "needs_review": False,
            },
            {
                "candidate_id": "SYM-2",
                "count": 28,
                "representative_bbox_pt": (200.0, 200.0, 220.0, 220.0),
                "instance_bboxes_pt": [(200.0, 200.0, 220.0, 220.0)],
                "contained_texts": [],
                "confidence": "high",
                "needs_review": False,
            },
        ],
        "walls": [
            {
                "candidate_id": "WALL-TC1",
                "thickness_class": "TC1",
                "centerline_pt": ((0.0, 0.0), (300.0, 0.0)),
            },
            {
                "candidate_id": "WALL-TC2",
                "thickness_class": "TC2",
                "centerline_pt": ((0.0, 50.0), (120.0, 50.0)),
            },
        ],
        "wall_lf_by_class": {"TC1": 2204.4, "TC2": 310.0},
        "rooms": [
            {
                "candidate_id": "ROOM-1",
                "label": "WAREHOUSE",
                "label_source": "text_in_polygon",
                "area_pt2": 1000.0,
                "confidence": "high",
                "polygon_wkt": "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))",
            },
            {
                "candidate_id": "ROOM-2",
                "label": "",
                "label_source": "none",
                "area_pt2": 500.0,
                "confidence": "medium",
                "polygon_wkt": "POLYGON ((20 0, 30 0, 30 10, 20 10, 20 0))",
            },
        ],
        "viewports": [{"region_id": "R1", "bbox_pt": (0.0, 0.0, 3024.0, 2160.0)}],
        "schedules": [
            {
                "kind": "door",
                "confidence": "high",
                "rows": [
                    {"MARK": "101", "TYPE": "HM Door"},
                    {"MARK": "102", "TYPE": "HM Door"},
                    {"MARK": "103", "TYPE": "Storefront Door"},
                ],
            }
        ],
        "footprint": {
            "area_sf": 397600.0,
            "perimeter_lf": 2972.0,
            "confidence": "high",
            "needs_review": False,
            "review_reason": "",
        },
    }


def _labels():
    return {
        "matches": [
            {"symbol_id": "SYM-1", "label": "Column", "confidence": "high"},
            {"symbol_id": "SYM-999", "label": "Ghost Symbol", "confidence": "high"},
            {"symbol_id": "SYM-2", "label": "unknown", "confidence": "low"},
        ],
        "wall_class_labels": [
            {"wall_class_id": "WALL-TC1", "label": "CMU Wall", "confidence": "high"}
        ],
        "room_labels": [
            {"room_id": "ROOM-2", "label": "OFFICE", "confidence": "medium"},
        ],
        "main_plan_region": "R1",
        "_cost_usd": 0.0123,
    }


def _fused():
    bundle = _bundle()
    return fuse_sheet(bundle, _labels(), build_registry(bundle))


def _by_candidate(result):
    return {c["candidate_id"]: c for c in result["components"] if c.get("candidate_id")}


def test_fuse_symbol_quantity_equals_group_count_exactly():
    by_id = _by_candidate(_fused())
    col = by_id["SYM-1"]
    assert col["name"] == "Column"
    assert col["quantity"] == 136  # pinned: EXACTLY SymbolGroup.count
    assert col["unit"] == "EA"
    assert col["provenance"] == "geometry"
    assert col["needs_review"] is False


def test_fuse_unknown_label_keeps_deterministic_count_flagged():
    by_id = _by_candidate(_fused())
    unknown = by_id["SYM-2"]
    assert unknown["quantity"] == 28  # deterministic count preserved
    assert unknown["needs_review"] is True
    assert unknown["provenance"] == "geometry"
    assert unknown["confidence"] == "low"


def test_fuse_out_of_registry_id_rejected():
    result = _fused()
    by_id = _by_candidate(result)
    assert "SYM-999" not in by_id
    assert not any(c["name"] == "Ghost Symbol" for c in result["components"])
    rejection = [r for r in result["fusion_rejected"] if r.get("candidate_id") == "SYM-999"]
    assert len(rejection) == 1
    assert rejection[0]["reason"] == "unknown_candidate_id"
    assert rejection[0]["source"] == "matches"


def test_fuse_wall_classes_labeled_and_unlabeled():
    by_id = _by_candidate(_fused())
    cmu = by_id["WALL-TC1"]
    assert cmu["name"] == "CMU Wall"
    assert cmu["quantity"] == 2204.4  # LF from geometry, never from vision
    assert cmu["unit"] == "LF"
    assert cmu["provenance"] == "geometry"
    unlabeled = by_id["WALL-TC2"]
    assert unlabeled["name"] == "WALL-TC2"  # class id as name
    assert unlabeled["quantity"] == 310.0
    assert unlabeled["needs_review"] is True


def test_fuse_rooms_vision_fallback_only_for_unlabeled():
    by_id = _by_candidate(_fused())
    # Text-bound room: label kept; vision may not override it.
    warehouse = by_id["ROOM-1"]
    assert warehouse["name"] == "WAREHOUSE"
    assert warehouse["label_source"] == "text_in_polygon"
    # label_source == 'none' room: vision label applied as the fallback.
    office = by_id["ROOM-2"]
    assert office["name"] == "OFFICE"
    assert office["label_source"] == "vision"
    # SF from the polygon regardless of who supplied the label.
    assert warehouse["quantity"] == round(1000.0 * _FPP * _FPP, 1)
    assert office["quantity"] == round(500.0 * _FPP * _FPP, 1)
    assert warehouse["provenance"] == office["provenance"] == "geometry"


def test_fuse_rooms_vision_override_of_text_label_is_audited():
    bundle = _bundle()
    labels = _labels()
    labels["room_labels"].append(
        {"room_id": "ROOM-1", "label": "STORAGE", "confidence": "high"}
    )
    result = fuse_sheet(bundle, labels, build_registry(bundle))
    by_id = _by_candidate(result)
    assert by_id["ROOM-1"]["name"] == "WAREHOUSE"  # text binding wins
    blocked = [r for r in result["fusion_rejected"] if r.get("reason") == "label_override_blocked"]
    assert len(blocked) == 1
    assert blocked[0]["candidate_id"] == "ROOM-1"
    assert blocked[0]["answer"] == "STORAGE"


def test_fuse_schedule_rows_and_footprint_provenance():
    result = _fused()
    doors = [c for c in result["components"] if c.get("schedule_kind") == "door"]
    assert {(c["name"], c["quantity"]) for c in doors} == {
        ("HM Door", 2),
        ("Storefront Door", 1),
    }
    assert all(c["provenance"] == "schedule_table" for c in doors)

    footprint = [c for c in result["components"] if c["name"] == "Building Footprint"]
    assert len(footprint) == 1
    assert footprint[0]["quantity"] == 397600.0
    assert footprint[0]["provenance"] == "text_layer"
    perimeter = [c for c in result["components"] if c["name"] == "Building Perimeter"]
    assert perimeter[0]["quantity"] == 2972.0
    assert perimeter[0]["provenance"] == "text_layer"


def test_fuse_output_mirrors_analyze_drawing_shape():
    result = _fused()
    assert result["_pass_type"] == "fusion"
    assert result["_source_sheet"] == "A2.1"
    assert result["_cost_usd"] == 0.0123
    assert "_tokens_in" in result and "_tokens_out" in result and "_model_used" in result
    assert result["main_plan_region"] == "R1"
    # V3-ACC-01 protocol: nothing vision-side carries a number.
    assert all(
        c["provenance"] in DETERMINISTIC_PROVENANCES for c in result["components"]
    )


def test_fuse_room_without_scale_flags_instead_of_guessing():
    bundle = _bundle()
    bundle["fpp"] = 0.0  # no scale bound
    result = fuse_sheet(bundle, _labels(), build_registry(bundle))
    rooms = [c for c in result["components"] if str(c.get("candidate_id", "")).startswith("ROOM-")]
    assert rooms
    for room in rooms:
        assert room["quantity"] is None  # flag-don't-guess
        assert room["needs_review"] is True


def test_fused_output_feeds_merge_with_provenance():
    """fuse_sheet output merges with a vision result; geometry rows survive."""
    fused = _fused()
    vision_pass = {
        "components": [
            {"name": "Column", "quantity": 90, "unit": "EA", "confidence": "high"},  # no provenance
        ]
    }
    merged = merge_with_provenance([fused, vision_pass])
    columns = [c for c in merged["components"] if c["name"] == "Column"]
    assert len(columns) == 1
    assert columns[0]["quantity"] == 136  # geometry count survives the 90-guess
    assert columns[0]["provenance"] == "geometry"
    assert any(r["reason"] == "vision_quantity_blocked" for r in merged["fusion_rejected"])
    # Input fusion_rejected entries (SYM-999) carried through the merge.
    assert any(r.get("candidate_id") == "SYM-999" for r in merged["fusion_rejected"])


# ── Vocabulary measure-basis binding (wall_area → SF, floor/roof → footprint) ─


def test_fuse_binds_wall_area_and_floor_roof_from_vocabulary():
    """The core binding: a wall_area label → LF×height SF; floor/roof-plane
    vocabulary items → the measured footprint area (Crow 100-1000x gap)."""
    bundle = {
        "sheet_name": "A2.1",
        "wall_lf_by_class": {"TC1": 1714.0},
        "footprint": {"area_sf": 397600.0, "confidence": "high", "needs_review": False},
    }
    vocabulary = {
        "CMU Wall": {"basis": "wall_area"},
        "Sealed Concrete": {"basis": "floor_area"},
        "Exposed Structure": {"basis": "roof_area"},
    }
    labels = {
        "wall_class_labels": [
            {"wall_class_id": "WALL-TC1", "label": "CMU Wall", "confidence": "high"}
        ]
    }
    result = fuse_sheet(
        bundle, labels, vocabulary=vocabulary, wall_height_ft=35.0,
        wall_height_source="plan",
    )
    comps = {c["name"]: c for c in result["components"]}

    cmu = comps["CMU Wall"]
    assert cmu["unit"] == "SF"
    assert cmu["quantity"] == round(1714.0 * 35.0, 1)  # LF × height, not LF
    assert cmu["provenance"] == "geometry"
    assert cmu["wall_height_ft"] == 35.0
    assert cmu["wall_height_source"] == "plan"
    assert cmu["needs_review"] is False  # plan-sourced height → not flagged

    for name in ("Sealed Concrete", "Exposed Structure"):
        item = comps[name]
        assert item["unit"] == "SF"
        assert item["quantity"] == 397600.0  # the whole footprint, not a sliver
        assert item["provenance"] == "geometry"


def test_fuse_wall_area_default_height_is_flagged():
    bundle = {"wall_lf_by_class": {"TC1": 1000.0}}
    vocabulary = [
        {"name": "CMU Wall", "measure": "wall_area", "unit": "SF", "aliases": ["CMU"]}
    ]
    # Alias label resolves too (case/alias-insensitive), and a default-sourced
    # height flags the derived wall-area item for review.
    labels = {"wall_class_labels": [{"wall_class_id": "WALL-TC1", "label": "CMU"}]}
    result = fuse_sheet(
        bundle, labels, vocabulary=vocabulary, wall_height_ft=30.0,
        wall_height_source="default",
    )
    cmu = [c for c in result["components"] if c["candidate_id"] == "WALL-TC1"][0]
    assert cmu["unit"] == "SF"
    assert cmu["quantity"] == 30000.0
    assert cmu["needs_review"] is True
    assert "default" in cmu["review_reason"]


def test_fuse_no_vocabulary_no_footprint_keeps_lf_and_invents_nothing():
    """Regression guard: absent vocabulary/footprint/height, walls stay LF and
    no floor/roof items are invented (additive-only)."""
    bundle = {"wall_lf_by_class": {"TC1": 1714.0}}
    labels = {
        "wall_class_labels": [
            {"wall_class_id": "WALL-TC1", "label": "CMU Wall", "confidence": "high"}
        ]
    }
    result = fuse_sheet(bundle, labels)  # no vocabulary, no height, no footprint
    wall = [c for c in result["components"] if c.get("candidate_id") == "WALL-TC1"][0]
    assert wall["unit"] == "LF"  # unchanged prior behavior
    assert wall["quantity"] == 1714.0
    assert all(
        c.get("basis") not in ("floor_area", "roof_area") for c in result["components"]
    )


def test_fuse_floor_area_needs_footprint_with_positive_area():
    """floor/roof binding is geometry-gated: no footprint → no invented item."""
    bundle = {"wall_lf_by_class": {}}  # no footprint at all
    vocabulary = {"Sealed Concrete": {"basis": "floor_area"}}
    result = fuse_sheet(bundle, {}, vocabulary=vocabulary, wall_height_ft=30.0)
    assert not any(c["name"] == "Sealed Concrete" for c in result["components"])

    # Present but zero-area footprint is equally non-binding.
    bundle2 = {"wall_lf_by_class": {}, "footprint": {"area_sf": 0.0}}
    result2 = fuse_sheet(bundle2, {}, vocabulary=vocabulary)
    assert not any(c["name"] == "Sealed Concrete" for c in result2["components"])


# ── ID-grounding round-trip (registry → overlay marker → answer → component) ──


def test_id_grounding_round_trip_through_overlay():
    fitz = pytest.importorskip("fitz")
    from bobbytailor.vision.overlay import render_overlay

    bundle = _bundle()
    registry = build_registry(bundle)
    bbox_pt = registry["SYM-1"]["bbox_pt"]
    assert bbox_pt == (100.0, 100.0, 140.0, 140.0)

    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        overlay = render_overlay(page, {"SYM-1": bbox_pt})
        # Single image (≤40 markers) carrying the candidate subset + grounding info.
        assert overlay.info["overlay_ids"] == ["SYM-1"]
        zoom = overlay.info["zoom"]
        marker_px = overlay.info["marker_boxes_px"]["SYM-1"]
        # Pixel marker maps back to the registry PDF-point bbox exactly (±1px).
        for px, pt in zip(marker_px, bbox_pt):
            assert abs(px / zoom - pt) <= 1.0 / zoom
    finally:
        doc.close()

    # Canned answer for the marker ID → fused component references the SAME id.
    labels = {"matches": [{"symbol_id": "SYM-1", "label": "Column", "confidence": "high"}]}
    result = fuse_sheet(bundle, labels, registry)
    column = [c for c in result["components"] if c["name"] == "Column"][0]
    assert column["candidate_id"] == "SYM-1"
    assert column["quantity"] == 136


# ── ReplayAnalyzer harness ────────────────────────────────────────────────────


def test_replay_analyzer_unknown_hash_raises_keyerror(tmp_path, monkeypatch):
    monkeypatch.delenv(REPLAY_RECORD_ENV, raising=False)
    analyzer = ReplayAnalyzer(tmp_path / "replay")
    assert analyzer.record is False
    with pytest.raises(KeyError):
        analyzer("sheet.png", sheet_name="A2.1", pass_type="semantic")


def test_replay_analyzer_canned_fixture_resolves(tmp_path, monkeypatch):
    monkeypatch.delenv(REPLAY_RECORD_ENV, raising=False)
    fixture_dir = tmp_path / "replay"
    fixture_dir.mkdir()
    analyzer = ReplayAnalyzer(fixture_dir)
    canned = {"matches": [{"symbol_id": "SYM-1", "label": "Column", "confidence": "high"}]}
    key = analyzer.key_for(sheet_name="A2.1", pass_type="symbol_gallery", model_override="m-test")
    (fixture_dir / ("%s.json" % key)).write_text(
        json.dumps({"request": {"pass_type": "symbol_gallery"}, "response": canned})
    )
    result = analyzer(
        "sheet.png", sheet_name="A2.1", pass_type="symbol_gallery", model_override="m-test"
    )
    assert result == canned


def test_replay_analyzer_record_then_replay_round_trip(tmp_path, monkeypatch):
    monkeypatch.delenv(REPLAY_RECORD_ENV, raising=False)
    fixture_dir = tmp_path / "replay"
    recorded_response = {"components": [], "_pass_type": "semantic", "_cost_usd": 0.01}

    calls = []

    def fake_real_analyzer(screenshot_path, **kwargs):
        calls.append((screenshot_path, kwargs))
        return recorded_response

    recorder = ReplayAnalyzer(fixture_dir, record=True, real_analyzer=fake_real_analyzer)
    assert recorder.record is True
    first = recorder("sheet.png", sheet_name="A2.1", pass_type="semantic", model_override="m-x")
    assert first == recorded_response
    assert len(calls) == 1
    fixtures = list(fixture_dir.glob("*.json"))
    assert len(fixtures) == 1  # SHA256-keyed fixture written

    # Fresh replay-mode instance resolves the SAME request offline.
    replayer = ReplayAnalyzer(fixture_dir)
    replayed = replayer("sheet.png", sheet_name="A2.1", pass_type="semantic", model_override="m-x")
    assert replayed == recorded_response
    assert len(calls) == 1  # real analyzer NOT called again

    # A different prompt still raises (determinism: no fuzzy fallback).
    with pytest.raises(KeyError):
        replayer("sheet.png", sheet_name="OTHER", pass_type="semantic", model_override="m-x")


def test_replay_analyzer_env_var_activates_record_mode(tmp_path, monkeypatch):
    monkeypatch.setenv(REPLAY_RECORD_ENV, "1")
    analyzer = ReplayAnalyzer(tmp_path, real_analyzer=lambda *a, **k: {"ok": True})
    assert analyzer.record is True
    monkeypatch.setenv(REPLAY_RECORD_ENV, "0")
    assert ReplayAnalyzer(tmp_path).record is False


def test_replay_analyzer_injectable_into_takeoff_pipeline(tmp_path, monkeypatch):
    monkeypatch.delenv(REPLAY_RECORD_ENV, raising=False)
    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    analyzer = ReplayAnalyzer(tmp_path / "replay")
    pipeline = TakeoffPipeline(analyzer=analyzer)
    assert pipeline._analyzer is analyzer  # the 20-00 injection seam, preserved


# ── Bollard 2×-dedup + noise-cluster filter (offline) ────────────────────────


def _sym_group(cid, count, boxes, texts=None, rep=None):
    return {
        "candidate_id": cid,
        "count": count,
        "instance_bboxes_pt": boxes,
        "representative_bbox_pt": rep or (boxes[0] if boxes else (0.0, 0.0, 6.0, 6.0)),
        "contained_texts": texts or [],
        "confidence": "medium",
    }


def _concentric_pairs(n_locations, step=25.0, origin=(100.0, 100.0)):
    """Each physical object drawn as TWO concentric marks (pipe + cap)."""
    ox, oy = origin
    boxes = []
    for i in range(n_locations):
        cx, cy = ox + i * step, oy
        boxes.append((cx - 2.0, cy - 2.0, cx + 2.0, cy + 2.0))   # pipe
        boxes.append((cx - 3.0, cy - 3.0, cx + 3.0, cy + 3.0))   # cap
    return boxes


def _grid(cols, rows, step=30.0, size=6.0, origin=(500.0, 500.0)):
    ox, oy = origin
    return [
        (ox + c * step, oy + r * step, ox + c * step + size, oy + r * step + size)
        for r in range(rows) for c in range(cols)
    ]


def test_bollard_concentric_pairs_dedup_56_to_28():
    boxes = _concentric_pairs(28)          # 56 marks, 28 physical bollards
    group = _sym_group("SYM-1", 56, boxes)
    bundle = {"symbol_groups": [group], "sheet_name": "S1"}
    labels = {"matches": [{"symbol_id": "SYM-1", "label": "Bollards", "confidence": "high"}]}
    result = fuse_sheet(bundle, labels)
    boll = [c for c in result["components"] if c["name"] == "Bollards"][0]
    assert boll["quantity"] == 28
    assert boll["unit"] == "EA"


def test_column_grid_not_deduped():
    boxes = _grid(12, 11)                   # 132 columns on a regular grid
    group = _sym_group("SYM-1", 132, boxes)
    bundle = {"symbol_groups": [group], "sheet_name": "S1"}
    labels = {"matches": [{"symbol_id": "SYM-1", "label": "Columns", "confidence": "high"}]}
    result = fuse_sheet(bundle, labels)
    cols = [c for c in result["components"] if c["name"] == "Columns"][0]
    assert cols["quantity"] == 132          # dedup applies only to bollard bindings


def _collinear_strip(n, step=14.0, origin=(500.0, 1863.0), size=1.3):
    """n identical marks on a SINGLE horizontal line — a dimension-tick strip
    (Crow ground truth §10: the 136 marks all at Y=1863.2 that coincidentally
    equalled the column count)."""
    ox, oy = origin
    return [(ox + i * step, oy, ox + i * step + size, oy + size) for i in range(n)]


def test_collinear_strip_labeled_columns_is_flagged_not_trusted():
    # A columns label on a collinear tick strip is a coincidence — keep the
    # count but force review + low confidence (flag-don't-guess §10).
    group = _sym_group("SYM-1", 136, _collinear_strip(136))
    bundle = {"symbol_groups": [group], "sheet_name": "S1"}
    labels = {"matches": [{"symbol_id": "SYM-1", "label": "Columns", "confidence": "high"}]}
    result = fuse_sheet(bundle, labels)
    col = [c for c in result["components"] if c["name"] == "Columns"][0]
    assert col["quantity"] == 136           # count preserved, never silently dropped
    assert col["needs_review"] is True      # but never presented as trusted
    assert col["confidence"] == "low"
    assert "collinear" in col["review_reason"].lower()


def test_real_2d_column_grid_stays_trusted():
    # The guard must NOT touch a genuine 2-D column grid.
    group = _sym_group("SYM-1", 132, _grid(12, 11))
    bundle = {"symbol_groups": [group], "sheet_name": "S1"}
    labels = {"matches": [{"symbol_id": "SYM-1", "label": "Columns", "confidence": "high"}]}
    result = fuse_sheet(bundle, labels)
    col = [c for c in result["components"] if c["name"] == "Columns"][0]
    assert col["quantity"] == 132
    assert col["needs_review"] is False


def test_structural_grid_hint_does_not_bind_collinear_strip():
    # The naming-library structural_grid_symbol hint must not name a collinear
    # dimension-tick strip "Columns" just because it is the largest marker
    # cluster — a column grid is inherently 2-D (§10).
    group = _sym_group("SYM-1", 136, _collinear_strip(136))
    bundle = {"symbol_groups": [group], "sheet_name": "S1"}
    vocabulary = [
        {"name": "Columns", "binding_hint": "structural_grid_symbol", "basis": "count"}
    ]
    result = fuse_sheet(bundle, {"matches": []}, vocabulary=vocabulary)
    names = {c["name"] for c in result["components"]}
    assert "Columns" not in names           # no coincidental columns binding


def test_structural_grid_hint_binds_real_2d_grid():
    # The same hint SHOULD still bind a genuine 2-D grid.
    group = _sym_group("SYM-1", 132, _grid(12, 11))
    bundle = {"symbol_groups": [group], "sheet_name": "S1"}
    vocabulary = [
        {"name": "Columns", "binding_hint": "structural_grid_symbol", "basis": "count"}
    ]
    result = fuse_sheet(bundle, {"matches": []}, vocabulary=vocabulary)
    cols = [c for c in result["components"] if c["name"] == "Columns"]
    assert cols and cols[0]["quantity"] == 132


def test_noise_clusters_excluded_from_takeoff():
    noise = [
        _sym_group("SYM-1", 6, _grid(3, 2), texts=["1", "2", "3", "4"]),
        _sym_group("SYM-2", 4, _grid(2, 2, origin=(50.0, 50.0)), texts=["0\" - 60'"]),
        _sym_group("SYM-3", 5, _grid(1, 5, origin=(80.0, 80.0)), texts=["TYP."]),
        _sym_group("SYM-4", 3, _grid(1, 3, origin=(120.0, 10.0)), texts=["SS"]),
        _sym_group("SYM-5", 4, _grid(2, 2, origin=(300.0, 5.0)), texts=["A-101"]),
    ]
    bundle = {"symbol_groups": noise, "sheet_name": "S1"}
    result = fuse_sheet(bundle, {"matches": []})
    names = {c["name"] for c in result["components"]}
    # None of the drafting-noise clusters became a take-off line item.
    assert not any(n in names for n in ("1 / 2 / 3 / 4", "0\" - 60'", "TYP.", "SS", "A-101"))
    assert result["components"] == []


def test_real_object_cluster_with_text_is_retained():
    # A genuine object whose nearby text is a real word is NOT noise → kept flagged.
    group = _sym_group("SYM-1", 4, _grid(2, 2), texts=["PUMP"])
    result = fuse_sheet({"symbol_groups": [group], "sheet_name": "S1"}, {"matches": []})
    names = {c["name"] for c in result["components"]}
    assert "PUMP" in names


def test_noise_and_real_clusters_coexist():
    groups = [
        _sym_group("SYM-1", 6, _grid(3, 2, origin=(0.0, 0.0)), texts=["1", "2", "3"]),
        _sym_group("SYM-2", 132, _grid(12, 11)),   # columns (labeled below)
        _sym_group("SYM-3", 56, _concentric_pairs(28, origin=(2000.0, 2000.0))),  # bollards
    ]
    bundle = {"symbol_groups": groups, "sheet_name": "S1"}
    labels = {"matches": [
        {"symbol_id": "SYM-2", "label": "Columns", "confidence": "high"},
        {"symbol_id": "SYM-3", "label": "Bollards", "confidence": "high"},
    ]}
    result = fuse_sheet(bundle, labels)
    by_name = {c["name"]: c for c in result["components"]}
    assert "Columns" in by_name and "Bollards" in by_name
    assert by_name["Columns"]["quantity"] == 132
    assert by_name["Bollards"]["quantity"] == 28
    assert "1 / 2 / 3" not in by_name       # gridline-bubble noise dropped


# ---------------------------------------------------------------------------
# 23-03 — _fuse_room_fills stops discarding measured areas in silence.
#
# INV-08 §2 row S8: three early exits could each throw away a SUCCESSFULLY
# MEASURED enclosed area with no trace. The one at `if not wanted` is the
# plans-only failure mode: with no manifest the vocabulary frequently carries
# no `basis`, so every area the engine just computed is dropped.
# ---------------------------------------------------------------------------


def _room_fill(kind, area, name="KING A", needs_review=False):
    from bobbytailor.deterministic.room_fill import RoomFillResult
    return RoomFillResult(
        area_sf=area, candidate_id="FILL-1", scale_fpi=4.0,
        plan_kind=kind, plan_name=name, viewport_title="%s - %s PLAN" % (name, kind),
        needs_review=needs_review,
        review_reason="exceeds the plausible single-unit maximum" if needs_review else "",
    )


def _ceiling_vocab(name="Gyp Ceiling"):
    return [{"name": name, "basis": "ceiling_area", "unit": "SF"}]


def test_measured_fills_with_no_area_basis_leave_a_coverage_note():
    """THE plans-only failure mode. 1,452 SF measured, zero line items, and
    until now zero indication that anything had been measured at all."""
    bundle = {
        "room_fills": [_room_fill("RCP", 341.7), _room_fill("AR", 369.9)],
        "sheet_name": "page27",
    }
    result = fuse_sheet(bundle, {"matches": []})       # no vocabulary at all
    assert not [c for c in result["components"] if c.get("name_source") == "room_fill"]

    notes = bundle.get("coverage_notes") or []
    assert len(notes) == 1
    note = notes[0]
    assert "711.6 SF" in note, "the note must state the total that was discarded"
    assert "no vocabulary or manifest item carries an area basis" in note
    assert "DISCARDED" in note
    assert "KING A - RCP PLAN" in note, "and name the drawings it came from"


def test_a_sheet_with_no_measurable_drawing_says_so():
    bundle = {"room_fills": [], "sheet_name": "page0"}
    fuse_sheet(bundle, {"matches": []}, vocabulary=_ceiling_vocab())
    notes = bundle.get("coverage_notes") or []
    assert len(notes) == 1
    assert "no measurable plan drawing on this sheet" in notes[0]
    assert "NOT the same as measuring zero" in notes[0]


def test_no_drawing_of_the_right_discipline_emits_a_not_measured_item():
    """S9: the selector finds nothing, and the caller used to `continue`.

    Substituting the architectural plan's area for a ceiling would be a guess,
    so the honest outcome is an explicit blank — never no row at all.
    """
    bundle = {"room_fills": [_room_fill("AR", 369.9)], "sheet_name": "page27"}
    result = fuse_sheet(bundle, {"matches": []}, vocabulary=_ceiling_vocab())

    assert not [c for c in result["components"] if c["name"] == "Gyp Ceiling"]
    items = bundle.get("item_coverage") or []
    assert len(items) == 1
    item = items[0]
    assert item.name == "Gyp Ceiling"
    assert item.quantity is None, "a blank is None, never 0.0"
    assert item.status == "NOT MEASURED"
    assert item.basis == "ceiling_area"
    assert item.source_sheets == ["page27"]
    assert "RCP" in item.reason and "would be a guess" in item.reason


def test_a_flagged_fill_now_produces_a_flagged_row_instead_of_nothing():
    """The end-to-end shape of the S8/S9 repair: the ONLY RCP drawing on the
    sheet is flagged (Moxy's ACC BUNK ~2x clip defect). The row must exist,
    carry the measured number, and be flagged — not vanish."""
    bundle = {
        "room_fills": [_room_fill("RCP", 458.5, name="ACC BUNK", needs_review=True)],
        "sheet_name": "page38",
    }
    result = fuse_sheet(bundle, {"matches": []}, vocabulary=_ceiling_vocab())
    rows = [c for c in result["components"] if c["name"] == "Gyp Ceiling"]
    assert len(rows) == 1
    assert rows[0]["quantity"] == pytest.approx(458.5)
    assert rows[0]["needs_review"] is True
    assert "plausible single-unit maximum" in rows[0]["review_reason"]
    assert not (bundle.get("item_coverage") or []), (
        "a measured-but-flagged item is NOT a not-measured item"
    )


def test_a_clean_binding_writes_no_notes_and_no_item_coverage():
    """Silence is correct when nothing was lost — the record must not cry wolf."""
    bundle = {"room_fills": [_room_fill("RCP", 341.7)], "sheet_name": "page27"}
    result = fuse_sheet(bundle, {"matches": []}, vocabulary=_ceiling_vocab())
    rows = [c for c in result["components"] if c["name"] == "Gyp Ceiling"]
    assert len(rows) == 1 and rows[0]["quantity"] == pytest.approx(341.7)
    assert not (bundle.get("coverage_notes") or [])
    assert not (bundle.get("item_coverage") or [])


# ---------------------------------------------------------------------------
# 23-08 — a finish code the drawing calls out gets a NAMED, FLAGGED, ZERO row.
#
# Moxy's WC-1..WC-10 (7,432 SF of golden quantity) live on interior-elevation
# sheets and the pipeline emits NOTHING for them today. Silence is
# indistinguishable from zero, and it is the worst of the three states.
#
# The area is NOT recoverable and must never be invented: INV-05 §3 seeded a
# flood fill at every WC tag and every one leaked to the clip edge at 4-10x the
# estimator's own figure. The row therefore carries quantity ZERO and the tag
# positions the human workspace uses to pre-place the shapes.
# ---------------------------------------------------------------------------

from bobbytailor.vision.fusion import (          # noqa: E402
    MaterialTagLedger,
    _fuse_material_tags,
)


def _material_tag(code, bbox, page_index=18):
    from bobbytailor.deterministic.finish_tags import MaterialTag
    prefix, number = code.split("-")
    return MaterialTag(code=code, prefix=prefix, number=number.zfill(2),
                       bbox_pt=bbox, page_index=page_index, text_dir=(1, 0))


def _elevation_bundle(codes_and_boxes, sheet_name="ID-203"):
    return {
        "sheet_name": sheet_name,
        "material_tags": [_material_tag(c, b) for c, b in codes_and_boxes],
    }


def test_a_called_out_finish_code_becomes_a_named_flagged_zero_row():
    bundle = _elevation_bundle([
        ("WC-6", (908.4, 217.4, 943.6, 228.8)),
        ("WC-7", (1208.4, 517.4, 1243.6, 528.8)),
    ])
    result = fuse_sheet(bundle, {"matches": []})
    rows = {c["name"]: c for c in result["components"]
            if c.get("name_source") == "material_tag"}

    assert set(rows) == {"WC-6", "WC-7"}
    for code, row in rows.items():
        assert row["quantity"] == 0, "no area may be synthesized for a finish"
        assert row["unit"] == "SF"
        assert row["needs_review"] is True
        assert row["provenance"] == "text_layer", "the code is printed, not guessed"
        assert row["confidence"] == "low"
        assert row["candidate_id"] == "FINISH-%s" % code
        assert code in row["review_reason"]
        assert "not a closed region" in row["review_reason"]


def test_the_row_carries_the_tag_positions_the_workspace_pre_places():
    """This is the point of the row: an absent item is invisible, a flagged
    named item seeded with its positions is a task closed in seconds."""
    boxes = [(908.4, 217.4, 943.6, 228.8), (1108.4, 917.4, 1143.6, 928.8)]
    bundle = _elevation_bundle([("WC-7", boxes[0]), ("WC-7", boxes[1])])
    result = fuse_sheet(bundle, {"matches": []})
    rows = [c for c in result["components"] if c.get("name_source") == "material_tag"]

    assert len(rows) == 1, "one component per DISTINCT code on the sheet"
    assert rows[0]["tag_count"] == 2
    assert rows[0]["tag_positions_pt"] == [list(boxes[0]), list(boxes[1])]


def test_no_finish_row_ever_carries_a_quantity_above_zero():
    bundle = _elevation_bundle([("WC-%d" % n, (100.0 * n, 200.0, 100.0 * n + 30, 212.0))
                                for n in range(1, 11)])
    result = fuse_sheet(bundle, {"matches": []})
    rows = [c for c in result["components"] if c.get("name_source") == "material_tag"]
    assert len(rows) == 10
    assert all(r["quantity"] == 0 for r in rows), (
        "only a human /measurements POST may give a finish code a quantity"
    )


def test_a_sheet_with_no_material_tags_emits_nothing_and_says_nothing():
    result = fuse_sheet({"sheet_name": "A1.0", "material_tags": []}, {"matches": []})
    assert not [c for c in result["components"] if c.get("name_source") == "material_tag"]


def test_two_sheets_sharing_a_code_group_under_one_ledger_entry():
    """Grouping is by CODE across sheets — that is what the cap counts.

    Each sheet still emits its own row, because the workspace needs THAT
    sheet's positions to place THAT sheet's shapes; what is bounded is how many
    distinct codes may ever open a review row (T-23-31).
    """
    ledger = MaterialTagLedger(cap=1)
    first, second = [], []
    _fuse_material_tags(
        _elevation_bundle([("WC-1", (10, 20, 40, 32))], sheet_name="ID-200"),
        first, ledger,
    )
    bundle2 = _elevation_bundle(
        [("WC-1", (50, 60, 80, 72)), ("WC-2", (90, 60, 120, 72))],
        sheet_name="ID-201",
    )
    _fuse_material_tags(bundle2, second, ledger)

    assert ledger.sheets_by_code == {"WC-1": ["ID-200", "ID-201"]}, (
        "one entry for the code, naming both sheets"
    )
    assert [c["name"] for c in first] == ["WC-1"]
    assert [c["name"] for c in second] == ["WC-1"], "WC-2 is over the cap"
    assert ledger.suppressed == {"WC-2": 1}


def test_a_suppressed_code_is_recorded_as_unmeasured_and_not_as_zero():
    ledger = MaterialTagLedger(cap=0)
    components = []
    bundle = _elevation_bundle([("WC-1", (10, 20, 40, 32))], sheet_name="ID-200")
    _fuse_material_tags(bundle, components, ledger)
    assert components == []
    notes = bundle.get("coverage_notes") or []
    assert len(notes) == 1
    assert "WC-1" in notes[0] and "unmeasured, not zero" in notes[0]


def test_the_emitted_order_follows_the_sheet_and_is_deterministic():
    boxes = [("WC-7", (900.0, 200.0, 930.0, 212.0)),
             ("WC-6", (100.0, 200.0, 130.0, 212.0)),
             ("WC-7", (500.0, 400.0, 530.0, 412.0))]
    rows = []
    _fuse_material_tags(_elevation_bundle(boxes), rows, MaterialTagLedger())
    assert [r["name"] for r in rows] == ["WC-7", "WC-6"]


# ── The real elevation sheet ────────────────────────────────────────────────


def test_moxy_elevation_sheet_emits_one_flagged_row_per_wall_covering_code():
    """Real PDF, real masks, zero API. INV-05 §2 Key A records the estimator's
    own Legend box for page index 18 as exactly {WC-6, WC-7}."""
    import os

    import fitz

    from bobbytailor.deterministic.finish_tags import extract_material_tags
    from bobbytailor.deterministic.tag_pairing import sheet_mask_rects

    moxy = os.path.join(
        os.path.dirname(__file__), os.pardir, "uploads",
        "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
    )
    if not os.path.exists(moxy):
        pytest.skip("Moxy plans PDF not present")

    doc = fitz.open(moxy)
    try:
        page = doc[18]
        tags = extract_material_tags(page, sheet_mask_rects(page), 18)
        page_rect = tuple(page.rect)
    finally:
        doc.close()

    assert tags, "the bundle's material-tag list must not be empty on ID-203"
    bundle = {"sheet_name": "ID-203", "material_tags": tags}
    result = fuse_sheet(bundle, {"matches": []})
    rows = {c["name"]: c for c in result["components"]
            if c.get("name_source") == "material_tag"}

    wc_rows = {name: row for name, row in rows.items() if name.startswith("WC-")}
    assert set(wc_rows) == {"WC-6", "WC-7"}, "the estimator's own legend set"
    for row in wc_rows.values():
        assert row["quantity"] == 0 and row["needs_review"] is True
        assert row["tag_positions_pt"], "the workspace needs somewhere to start"
        for x0, y0, x1, y1 in row["tag_positions_pt"]:
            assert page_rect[0] <= x0 < x1 <= page_rect[2]
            assert page_rect[1] <= y0 < y1 <= page_rect[3]


def test_a_tag_inside_a_schedule_or_legend_mask_never_becomes_a_row():
    """T-23-30: a door-schedule tag column looks exactly like a plan callout.

    A false positive costs a review; the masks keep it from costing even that.
    """
    from bobbytailor.deterministic.finish_tags import extract_material_tags

    class _Page:
        number = 18

        def get_text(self, kind):
            assert kind == "dict"
            lines = [
                # The MEASURED Moxy p18 tag geometry, inside a schedule table.
                {"bbox": (908.4, 217.4, 923.7, 228.8), "dir": (1, 0),
                 "spans": [{"text": "WC"}]},
                {"bbox": (934.2, 217.4, 943.6, 228.8), "dir": (1, 0),
                 "spans": [{"text": "07"}]},
            ]
            return {"blocks": [{"lines": lines}]}

    page = _Page()
    schedule_bbox = (800.0, 180.0, 1200.0, 300.0)
    assert extract_material_tags(page, (), 18), "unmasked, the tag reads"

    bundle = {"sheet_name": "A7-01",
              "material_tags": extract_material_tags(page, [schedule_bbox], 18)}
    result = fuse_sheet(bundle, {"matches": []})
    assert not [c for c in result["components"]
                if c.get("name_source") == "material_tag"]


# ---------------------------------------------------------------------------
# 23-08 — a finish-schedule row is a TYPE DECLARATION, not one each.
#
# INV-05 §4 row 5: every schedule row emitted `quantity = 1.0, unit = "EA"`, so
# even if a finish schedule parsed, WC-1 would land as "1 EA" — a fabricated
# unit on a fabricated number, rendered as a completed line item. The finish
# kind now takes the same shape the material-tag path emits (D-03).
# ---------------------------------------------------------------------------


def _schedule(kind, rows, confidence="high"):
    return {"kind": kind, "confidence": confidence, "rows": rows,
            "bbox_pt": (0, 0, 100, 100)}


def test_a_finish_schedule_row_never_reports_one_each():
    bundle = {"sheet_name": "CS-03", "schedules": [
        _schedule("finish", [{"TAG": "204", "ITEM": "WC-1", "FINISH": "WALLCOVERING"}])
    ]}
    result = fuse_sheet(bundle, {"matches": []})
    rows = [c for c in result["components"] if c.get("schedule_kind") == "finish"]

    assert len(rows) == 1
    row = rows[0]
    assert row["quantity"] == 0, "a type declaration is not an installed quantity"
    assert row["unit"] == "SF", "and it is certainly not one EACH"
    assert row["needs_review"] is True
    assert "204" in row["review_reason"], "the room tag must be in the reason"
    assert "NOT measured" in row["review_reason"]


def test_the_two_finish_paths_emit_one_contract():
    """D-03: the same idea must not produce two different flag shapes."""
    sched_bundle = {"sheet_name": "CS-03", "schedules": [
        _schedule("finish", [{"TAG": "204", "ITEM": "WC-1"}])
    ]}
    tag_bundle = _elevation_bundle([("WC-1", (10, 20, 40, 32))])

    from_schedule = [c for c in fuse_sheet(sched_bundle, {"matches": []})["components"]
                     if c.get("schedule_kind") == "finish"][0]
    from_tag = [c for c in fuse_sheet(tag_bundle, {"matches": []})["components"]
                if c.get("name_source") == "material_tag"][0]

    for field in ("quantity", "unit", "needs_review", "confidence"):
        assert from_schedule[field] == from_tag[field], field
    assert from_schedule["candidate_id"].startswith("FINISH-")
    assert from_tag["candidate_id"].startswith("FINISH-")
    assert "tag_positions_pt" in from_schedule and "tag_positions_pt" in from_tag


def test_a_door_kind_and_a_keynote_kind_are_untouched():
    """The change is scoped to the finish kind — a door row IS one opening."""
    bundle = {"sheet_name": "A7-01", "schedules": [
        _schedule("door", [{"TYPE": "WD-1", "QTY": "3"}, {"TYPE": "HM-2"}]),
        _schedule("keynote", [{"ITEM": "Note 1"}]),
    ]}
    rows = {c["name"]: c for c in fuse_sheet(bundle, {"matches": []})["components"]}

    assert rows["WD-1"]["quantity"] == 3 and rows["WD-1"]["unit"] == "EA"
    assert rows["HM-2"]["quantity"] == 1 and rows["HM-2"]["unit"] == "EA"
    assert rows["WD-1"]["needs_review"] is False
    assert rows["Note 1"]["quantity"] == 1 and rows["Note 1"]["unit"] == "EA"
    assert rows["Note 1"]["confidence"] == "high", "table confidence is preserved"


def test_a_finish_row_with_no_room_tag_still_flags_without_inventing_one():
    bundle = {"sheet_name": "CS-03", "schedules": [
        _schedule("finish", [{"ITEM": "WC-1"}])
    ]}
    row = [c for c in fuse_sheet(bundle, {"matches": []})["components"]
           if c.get("schedule_kind") == "finish"][0]
    assert row["quantity"] == 0 and row["needs_review"] is True
    assert " to " not in row["review_reason"]


def test_no_real_plan_set_produces_a_finish_schedule():
    """INV-05 §6 item 1, the regression guard for this change, on all four sets.

    `kind="finish"` has never fired on a real input: Moxy's CS-03 is indexed on
    page 1 and is not in the PDF. Keeping the vocabulary is right; pretending it
    is exercised would not be. The day it fires, this test says so.
    """
    import os

    import fitz

    from bobbytailor.deterministic.tables import extract_schedules

    uploads = os.path.join(os.path.dirname(__file__), os.pardir, "uploads")
    names = [
        "Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf",
        "Crow - Cass White Road-Plans.pdf",
        "Bob's Discount Furniture - Kennesaw, GA-plans.pdf",
        "Invitation to Bid - 25-382 AL, Chelsea, Bear Creek Rd-Plans.pdf",
    ]
    paths = [os.path.join(uploads, n) for n in names]
    missing = [n for n, p in zip(names, paths) if not os.path.exists(p)]
    if missing:
        pytest.skip("plan set(s) not present: %s" % ", ".join(missing))

    for name, path in zip(names, paths):
        doc = fitz.open(path)
        try:
            kinds = [t.kind for t in extract_schedules(doc)]
        finally:
            doc.close()
        assert "finish" not in kinds, "%s now yields a finish schedule: %s" % (
            name, kinds,
        )
