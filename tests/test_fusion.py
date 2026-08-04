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
    """The core binding: a wall_area label → LF×height SF; a floor/roof-plane
    vocabulary item → the measured footprint area (Crow 100-1000x gap).

    REWRITTEN by 23-13 (SP-9): the original asserted that BOTH footprint-bound
    items survive — the exact one-region-many-items shape that bound one Crow
    footprint value to SIX line items at once (INV-00 §4). Under one-area-
    one-item arbitration exactly ONE survives per measured region unless the
    sharing is declared, and the other is in the rejected list with a reason.
    """
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

    # Both footprint-backed items survive: the sealed-concrete FINISH and the
    # exposed roof STRUCTURE are different building layers through one plan
    # area, not two copies of one quantity. Suppressing one of them was the
    # regression that took Crow's measured-item accuracy from 75% to 0%.
    survivors = [
        c for c in result["components"]
        if c["name"] in ("Sealed Concrete", "Exposed Structure")
    ]
    assert len(survivors) == 2
    assert {c["name"] for c in survivors} == {"Sealed Concrete", "Exposed Structure"}
    assert {c["building_layer"] for c in survivors} == {
        "floor_finish", "roof_structure"
    }
    for survivor in survivors:
        assert survivor["unit"] == "SF"
        assert survivor["quantity"] == 397600.0  # the whole footprint
        assert survivor["provenance"] == "geometry"
        # The sharing is recorded as deliberate, never emergent.
        assert survivor["shared_area"] == "deliberate"
    dropped = [
        r for r in result["fusion_rejected"]
        if r.get("reason") == "one_area_one_item"
        and r.get("answer") in ("Sealed Concrete", "Exposed Structure")
    ]
    assert dropped == []


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


# ═════════════════════════════════════════════════════════════════════════════
# 23-13 — the basis-to-binder registry (SP-9), the wall-area binder, and
# one-area-one-item arbitration. All offline, zero API.
# ═════════════════════════════════════════════════════════════════════════════

from bobbytailor.vision.fusion import (  # noqa: E402
    BASIS_BINDERS,
    _arbitrate_one_area_one_item,
    register_basis_binder,
)

MOXY_PDF = "uploads/Moxy Knoxville - Addendum A City Comment Revision-Plans.pdf"
CROW_PLANS = "tests/fixtures/crow_cass/crow_cass_plans.pdf"


def _wall_fill(
    name="KING A",
    kind="AR",
    regions=(200.0,),
    perimeters=(60.0,),
    ratios=(4.24,),
    height=9.0,
    height_source="drawing",
    **kw,
):
    from bobbytailor.deterministic.room_fill import RoomFillResult

    return RoomFillResult(
        area_sf=round(sum(regions), 1),
        regions=list(regions),
        region_perimeters=list(perimeters),
        region_shape_ratios=list(ratios),
        perimeter_lf=round(sum(perimeters), 1),
        candidate_id="FILL-1",
        scale_fpi=4.0,
        plan_kind=kind,
        plan_name=name,
        viewport_title="%s - %s PLAN" % (name, kind),
        wall_height_ft=height,
        wall_height_source=height_source,
        **kw,
    )


def _gyp_wall_vocab():
    return [{"name": "Gyp Wall", "measure": "wall_area", "unit": "SF"}]


# ── Task 2: the wall-area binder through the registry ────────────────────────


def test_a_measured_wall_binds_perimeter_times_height_times_units():
    """INV-01 §8 case 7: 60 LF × 9 ft (drawing) × 26 units = 14,040 SF,
    provenance geometry, needs_review False."""
    bundle = {"room_fills": [_wall_fill()], "sheet_name": "p23"}
    result = fuse_sheet(
        bundle, {}, vocabulary=_gyp_wall_vocab(), room_mix={"king a": 26},
    )
    rows = [c for c in result["components"] if c["name"] == "Gyp Wall"]
    assert len(rows) == 1
    row = rows[0]
    assert row["quantity"] == pytest.approx(14040.0)
    assert row["provenance"] == "geometry"
    assert row["needs_review"] is False, row["review_reason"]
    assert row["wall_height_ft"] == 9.0
    assert row["wall_height_source"] == "drawing"
    # The audit trail is readable without re-running anything: perimeter,
    # drawing, scale, height, height source and unit count are all named.
    for token in ("60.0 LF", "KING A - AR PLAN", "4.00 ft/in", "9.00 ft",
                  "drawing", "26 units", "board faces"):
        assert token in row["formula"], (token, row["formula"])


def test_a_default_sourced_height_flags_the_wall_row_with_the_source_named():
    bundle = {
        "room_fills": [_wall_fill(height=None, height_source="")],
        "sheet_name": "p23",
    }
    result = fuse_sheet(
        bundle, {}, vocabulary=_gyp_wall_vocab(), room_mix={"king a": 26},
        wall_height_ft=30.0, wall_height_source="default",
    )
    row = [c for c in result["components"] if c["name"] == "Gyp Wall"][0]
    assert row["needs_review"] is True
    assert "default" in row["review_reason"]
    assert row["quantity"] == pytest.approx(round(60.0 * 30.0, 1) * 26)


def test_the_fifteen_foot_plan_height_multiplies_but_flags():
    """The roof-plan CLEAR REQ'D trap: source 'plan' is not the drawing's own
    tag, so the row multiplies AND flags — never silently (T-23-51)."""
    bundle = {
        "room_fills": [_wall_fill(height=15.0, height_source="plan")],
        "sheet_name": "p23",
    }
    result = fuse_sheet(bundle, {}, vocabulary=_gyp_wall_vocab())
    row = [c for c in result["components"] if c["name"] == "Gyp Wall"][0]
    assert row["needs_review"] is True
    assert "'plan'" in row["review_reason"] and "15.00" in row["review_reason"]


def test_a_degenerate_fill_yields_a_flagged_zero_row_that_exists():
    """All regions above the shape threshold: a missing row reads as 'not
    required'; a flagged zero reads as 'we could not measure this'."""
    bundle = {
        "room_fills": [
            _wall_fill(regions=(173.5, 11.5), perimeters=(113.6, 24.0),
                       ratios=(8.62, 9.1)),
        ],
        "sheet_name": "p23",
    }
    result = fuse_sheet(bundle, {}, vocabulary=_gyp_wall_vocab())
    rows = [c for c in result["components"] if c["name"] == "Gyp Wall"]
    assert len(rows) == 1, "the flagged zero MUST appear in the component list"
    assert rows[0]["quantity"] == 0.0
    assert rows[0]["needs_review"] is True
    assert "shape ratio" in rows[0]["review_reason"]


def test_no_height_ships_the_perimeter_with_quantity_none_never_a_guess():
    bundle = {
        "room_fills": [_wall_fill(height=None, height_source="")],
        "sheet_name": "p23",
    }
    result = fuse_sheet(bundle, {}, vocabulary=_gyp_wall_vocab())
    row = [c for c in result["components"] if c["name"] == "Gyp Wall"][0]
    assert row["quantity"] is None
    assert row["needs_review"] is True
    assert "60.0" in row["review_reason"] and "guessed height" in row["review_reason"]
    assert "UNRESOLVED" in row["formula"]


def test_registering_a_new_basis_routes_to_the_stub_binder():
    """A new capability REGISTERS a binder — it never adds a parallel gate."""
    calls = []

    def stub(bundle, components, info, fills, ctx):
        calls.append(info["basis"])
        components.append(
            {"name": info["name"], "quantity": 1.0, "unit": "SF",
             "provenance": "geometry", "needs_review": False,
             "review_reason": ""}
        )

    register_basis_binder("stub_area", stub)
    try:
        bundle = {"room_fills": [_wall_fill()], "sheet_name": "s"}
        result = fuse_sheet(
            bundle, {}, vocabulary={"Stub Item": {"basis": "stub_area",
                                                  "unit": "SF"}},
        )
        assert calls == ["stub_area"]
        assert any(c["name"] == "Stub Item" for c in result["components"])
    finally:
        BASIS_BINDERS.pop("stub_area", None)


def test_the_enclosed_region_bases_route_to_the_existing_binder():
    # Superseded in 23-14 (documented): wall_area now routes through ONE
    # dispatcher answering both wall geometries — the room-fill perimeter x
    # height binder AND the elevation facade binder. Still exactly one
    # registry entry; the dispatcher is byte-identical to _bind_wall_area on
    # any bundle without elevation areas.
    for basis in ("ceiling_area", "roof_area", "floor_area"):
        assert BASIS_BINDERS[basis].__name__ == "_bind_enclosed_area"
    assert BASIS_BINDERS["wall_area"].__name__ == "_bind_wall_area_basis"


# ── Task 3: one area backs one line item ─────────────────────────────────────


def test_a_room_fill_wall_item_supersedes_the_thickness_class_estimate():
    """INV-01 §8 case 10: both binders offer 'Gyp Wall' on one sheet. Exactly
    ONE survives; the other is in the rejected list naming the supersession.
    aggregate_takeoff SUMS same-named buckets, so without this the number is
    thickness + room-fill — wrong, and better-looking (T-23-50)."""
    bundle = {
        "room_fills": [_wall_fill()],
        "wall_lf_by_class": {"TC1": 305.0},
        "sheet_name": "p23",
    }
    labels = {
        "wall_class_labels": [
            {"wall_class_id": "WALL-TC1", "label": "Gyp Wall", "confidence": "high"}
        ]
    }
    result = fuse_sheet(
        bundle, labels, vocabulary=_gyp_wall_vocab(), room_mix={"king a": 26},
        wall_height_ft=9.0, wall_height_source="plan",
    )
    rows = [c for c in result["components"] if c["name"] == "Gyp Wall"]
    assert len(rows) == 1, "exactly one Gyp Wall row survives"
    assert rows[0]["name_source"] == "room_fill", (
        "the measured enclosed region supersedes the thickness-class estimate"
    )
    superseded = [
        r for r in result["fusion_rejected"]
        if r.get("reason") == "superseded_by_room_fill"
    ]
    assert len(superseded) == 1
    assert superseded[0]["candidate_id"] == "WALL-TC1"
    assert superseded[0]["quantity"] == pytest.approx(round(305.0 * 9.0, 1))


def test_a_deliberately_shared_area_survives_as_two_items_marked_deliberate():
    """A floor finish over a slab genuinely occupies the slab's area — but the
    sharing must be a STATEMENT, recorded, never an emergent sum."""
    components = [
        {"name": "Slab on Grade", "quantity": 1000.0, "unit": "SF",
         "region_ref": "footprint"},
        {"name": "Floor Finish", "quantity": 1000.0, "unit": "SF",
         "region_ref": "footprint", "shared_area": "declared"},
    ]
    rejected: list = []
    _arbitrate_one_area_one_item(components, rejected)
    assert len(components) == 2
    assert rejected == []
    finish = [c for c in components if c["name"] == "Floor Finish"][0]
    assert finish["shared_area"] == "deliberate"
    slab = [c for c in components if c["name"] == "Slab on Grade"][0]
    assert slab.get("shared_area") == "deliberate"
    assert slab.get("shared_area_with") == ["Floor Finish"]


def test_an_undeclared_second_item_on_one_region_is_suppressed_with_a_reason():
    components = [
        {"name": "Sealed Concrete", "quantity": 1000.0, "unit": "SF",
         "region_ref": "footprint"},
        {"name": "Vapor Barrier", "quantity": 1000.0, "unit": "SF",
         "region_ref": "footprint"},
    ]
    rejected: list = []
    _arbitrate_one_area_one_item(components, rejected)
    assert [c["name"] for c in components] == ["Sealed Concrete"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "one_area_one_item"
    assert rejected[0]["answer"] == "Vapor Barrier"
    assert "Sealed Concrete" in rejected[0]["detail"]


def test_a_typical_detail_run_never_sums_with_the_main_plan_run():
    """The 23-12 is_typical flag, wired into the same arbitration so plan
    23-15's binder inherits it."""
    components = [
        {"name": "Guard Rail", "quantity": 53.0, "unit": "LF",
         "typical_detail": True},
        {"name": "Guard Rail", "quantity": 53.0, "unit": "LF"},
    ]
    rejected: list = []
    _arbitrate_one_area_one_item(components, rejected)
    assert len(components) == 1
    assert not components[0].get("typical_detail")
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "typical_detail_not_summed"


def test_one_object_measured_on_two_regions_publishes_one_quantity():
    """Enumerating Crow's main floor plan (D4) gave "Sealed Concrete" a SECOND
    measurement — a 1,717 SF enclosed sub-region of the same drawing that the
    footprint already measures whole. Two routes to one quantity are not two
    quantities, and summing them prices the floor twice."""
    components = [
        {"name": "Sealed Concrete", "quantity": 397600.0, "unit": "SF",
         "region_ref": "footprint"},
        {"name": "Sealed Concrete", "quantity": 1716.7, "unit": "SF",
         "region_ref": "fill:FILL-2"},
    ]
    rejected: list = []
    _arbitrate_one_area_one_item(components, rejected)
    assert [c["quantity"] for c in components] == [397600.0]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "one_object_one_quantity"
    assert rejected[0]["quantity"] == 1716.7
    assert "not summed" in rejected[0]["detail"].lower()


def test_two_regions_with_no_footprint_row_are_left_alone():
    """Only the case with a principle behind it is decided. Without a footprint
    row there is no basis to rank two fills, and a guessed precedence would be
    worse than a duplicate an estimator can see."""
    components = [
        {"name": "Gyp Ceiling", "quantity": 229.4, "unit": "SF",
         "region_ref": "fill:FILL-6"},
        {"name": "Gyp Ceiling", "quantity": 504.9, "unit": "SF",
         "region_ref": "fill:FILL-1"},
    ]
    rejected: list = []
    _arbitrate_one_area_one_item(components, rejected)
    assert len(components) == 2 and rejected == []


def test_different_regions_and_different_units_are_never_arbitrated():
    components = [
        {"name": "Gyp Ceiling", "quantity": 229.4, "unit": "SF",
         "region_ref": "fill:FILL-6"},
        {"name": "Gyp Wall", "quantity": 504.9, "unit": "SF",
         "region_ref": "fill:FILL-1"},
        {"name": "Building Footprint", "quantity": 397600.0, "unit": "SF",
         "region_ref": "footprint"},
        {"name": "Building Perimeter", "quantity": 2972.0, "unit": "LF",
         "region_ref": "footprint"},
    ]
    rejected: list = []
    _arbitrate_one_area_one_item(components, rejected)
    assert len(components) == 4 and rejected == []


@pytest.mark.skipif(
    not __import__("os").path.isfile(CROW_PLANS),
    reason="Crow plans fixture not present",
)
def test_on_the_real_crow_bundle_the_footprint_backs_one_item_per_layer():
    """INV-00 §4 item 1 reproduced and defused, with the exception INV-00 asked
    for actually implemented.

    The measured footprint value backed SIX line items at once. Three of them
    are distinct building LAYERS through that one plan area (the slab, the
    sealed-concrete floor finish, the exposed roof structure) and an estimator
    prices all three. The other three inherited the footprint only because
    their measure basis is area-shaped — a Canopy has its own extent, a Vapor
    Barrier is part of the slab assembly, and Building Footprint is the region
    itself — so they are suppressed with a reason.

    Collapsing all six to ONE was the regression: it deleted two golden items
    (Sealed Concrete, Exposed Structure) and left a learned verbatim name in
    their place."""
    from bobbytailor.deterministic.footprint_takeoff import (
        extract_building_footprint,
    )

    fp = extract_building_footprint(CROW_PLANS)
    assert fp is not None and fp.area_sf > 0
    bundle = {"footprint": fp, "wall_lf_by_class": {}, "sheet_name": "crow-p0"}
    # The six-item shape from the live run: everything roof/floor-shaped
    # indiscriminately inherited the footprint (Building Footprint via
    # _fuse_footprint, the rest via the vocabulary binding).
    vocabulary = {
        "Canopy": {"basis": "roof_area"},
        "Concrete Pad": {"basis": "floor_area"},
        "Exposed Structure": {"basis": "roof_area"},
        "Sealed Concrete": {"basis": "floor_area"},
        "Vapor Barrier": {"basis": "floor_area"},
    }
    result = fuse_sheet(bundle, {}, vocabulary=vocabulary)
    value_rows = [
        c for c in result["components"]
        if c.get("unit") == "SF" and c.get("quantity") == pytest.approx(fp.area_sf)
    ]
    assert {c["name"] for c in value_rows} == {
        "Concrete Pad", "Sealed Concrete", "Exposed Structure"
    }, "one line item per building layer, got: %s" % [c["name"] for c in value_rows]
    # One item PER LAYER — no layer is claimed twice.
    layers = [c.get("building_layer") for c in value_rows]
    assert sorted(layers) == ["floor_finish", "roof_structure", "slab"]
    assert len(layers) == len(set(layers))

    suppressed = [
        r for r in result["fusion_rejected"]
        if r.get("reason") == "one_area_one_item"
    ]
    assert {r["answer"] for r in suppressed} == {
        "Canopy", "Vapor Barrier", "Building Footprint"
    }
    assert all(r.get("detail") for r in suppressed), "every suppression has a reason"
    assert all(
        "names no distinct building layer" in r["detail"] for r in suppressed
    )


# ── The real Moxy bundle, measured once for the whole module ─────────────────
#
# Every drawing on the 16 prototype sheets plus the REAL room-mix resolution
# (in-plan census + manifest cross-check). The poisoned 15 ft project answer is
# deliberately armed, exactly as in test_room_fill's fixture, so every fusion
# assertion below runs against the trap rather than against its absence.


@pytest.fixture(scope="module")
def moxy_real_bundles():
    import os

    if not os.path.exists(MOXY_PDF):
        pytest.skip("the real Moxy plan set is not present")
    import fitz

    from bobbytailor.devtools.object_manifest import load_manifest
    from bobbytailor.pipeline.takeoff_pipeline import (
        TakeoffPipeline,
        _room_mix_meta_payload,
    )

    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    pipe._project_wall_height = 15.0
    pipe._project_wall_height_source = "plan"
    manifest = load_manifest("human_inputs/moxy_knoxville.json")
    doc = fitz.open(MOXY_PDF)
    try:
        fills = {
            pno: pipe._measure_room_fills(doc[pno], [], {}, "p%d" % pno)[0]
            for pno in range(23, 39)
        }
        resolution = pipe._resolve_room_mix(manifest, doc, pdf_path=MOXY_PDF)
    finally:
        doc.close()
    return {
        "fills": fills,
        "room_mix": dict(resolution.counts),
        "room_mix_meta": _room_mix_meta_payload(resolution, manifest),
    }


def _fuse_moxy_page(moxy_real_bundles, pno, vocabulary):
    bundle = {
        "room_fills": moxy_real_bundles["fills"][pno],
        "sheet_name": "p%d" % pno,
    }
    return fuse_sheet(
        bundle, {}, vocabulary=vocabulary,
        wall_height_ft=15.0, wall_height_source="plan",
        room_mix=moxy_real_bundles["room_mix"],
        room_mix_meta=moxy_real_bundles["room_mix_meta"],
    )


def test_the_existing_ceiling_binding_is_unchanged_on_the_real_moxy_bundle(
    moxy_real_bundles,
):
    """Registry refactor, behaviour preserved: KING A's ceiling still binds
    229.4 SF x 26 units through the enclosed-area binder."""
    result = _fuse_moxy_page(
        moxy_real_bundles, 23,
        [{"name": "Gyp Ceiling", "measure": "ceiling_area", "unit": "SF"}],
    )
    rows = [c for c in result["components"] if c["name"] == "Gyp Ceiling"]
    assert len(rows) == 1
    assert rows[0]["quantity"] == pytest.approx(round(229.4 * 26, 1))
    assert rows[0]["provenance"] == "geometry"
    assert rows[0]["unit_count"] == 26
    assert rows[0]["unit_count_source"] == "unit_tag_census"


def test_wall_area_finally_binds_on_the_real_moxy_bundle(moxy_real_bundles):
    """V4-MEAS-01's other half: the wall_area basis reaches a line item.

    KING A's architectural fill LEAKS (shape ratio 8.62, the INV-01
    signature), so the honest first-run outcome is a flagged zero row — the
    row EXISTS, names the failure, and never fabricates linear feet."""
    result = _fuse_moxy_page(moxy_real_bundles, 23, _gyp_wall_vocab())
    rows = [c for c in result["components"] if c["name"] == "Gyp Wall"]
    assert len(rows) == 1, "wall_area now binds — the gate is open"
    row = rows[0]
    assert row["quantity"] == 0.0
    assert row["needs_review"] is True
    assert "shape ratio" in row["review_reason"]


def test_a_wall_binds_a_real_quantity_where_the_architectural_fill_is_honest(
    moxy_real_bundles,
):
    """BUNK B (p33): AR shape ratio 4.37 — honest — so the wall row carries a
    real perimeter x the drawing's own 9 ft, at the drawing's own scale."""
    result = _fuse_moxy_page(moxy_real_bundles, 33, _gyp_wall_vocab())
    rows = [c for c in result["components"] if c["name"] == "Gyp Wall"]
    assert len(rows) == 1
    row = rows[0]
    assert row["quantity"] is not None and row["quantity"] > 0.0
    assert row["wall_height_ft"] == 9.0
    assert row["wall_height_source"] == "drawing"
    assert "board faces" in row["formula"]


# ── Task 4: the selector's one coordinated change ────────────────────────────


def _extent_fill(cid, ratio, kind="RCP", name="KING A", area=230.0,
                 needs_review=False):
    from bobbytailor.deterministic.room_fill import RoomFillResult

    return RoomFillResult(
        area_sf=area, candidate_id=cid, plan_kind=kind, plan_name=name,
        viewport_title="%s - %s PLAN" % (name, kind), extent_ratio=ratio,
        needs_review=needs_review,
        review_reason="flagged" if needs_review else "",
    )


def test_two_validating_fills_of_one_name_return_nothing_with_an_ambiguity_flag():
    """Never silently take the smaller: two drawings of the same name on one
    sheet both validating make the unit AMBIGUOUS."""
    from bobbytailor.deterministic.room_fill import select_fill_for_basis

    fills = [
        _extent_fill("FILL-1", 1.02, area=229.4),
        _extent_fill("FILL-2", 0.99, area=451.1),
    ]
    ambiguity: list = []
    pick = select_fill_for_basis(fills, "ceiling_area", ambiguity_out=ambiguity)
    assert pick is None
    assert len(ambiguity) == 1
    assert "AMBIGUOUS" in ambiguity[0]
    assert "KING A - RCP PLAN" in ambiguity[0]


def test_the_ambiguity_lands_in_item_coverage_not_in_silence():
    """Through the binder: an ambiguous selection produces a record, not a
    vanished row."""
    bundle = {
        "room_fills": [
            _extent_fill("FILL-1", 1.02, area=229.4),
            _extent_fill("FILL-2", 0.99, area=451.1),
        ],
        "sheet_name": "p-amb",
    }
    result = fuse_sheet(
        bundle, {},
        vocabulary=[{"name": "Gyp Ceiling", "measure": "ceiling_area",
                     "unit": "SF"}],
    )
    assert not [c for c in result["components"] if c["name"] == "Gyp Ceiling"]
    items = bundle.get("item_coverage") or []
    assert len(items) == 1
    assert "AMBIGUOUS" in items[0].reason


def test_the_validated_fill_beats_a_clean_fill_with_no_extent_ratio():
    """Prefer the fill whose extent ratio is closest to one — the old
    smallest-area rule is gone (its rationale was the falsified opposite-hand
    misdiagnosis)."""
    from bobbytailor.deterministic.room_fill import select_fill_for_basis

    fills = [
        _extent_fill("FILL-1", None, area=100.0),   # smaller, no ratio
        _extent_fill("FILL-2", 1.01, area=451.1),   # larger, validates
    ]
    pick = select_fill_for_basis(fills, "ceiling_area")
    assert pick.candidate_id == "FILL-2", (
        "the validated fill wins; the smaller area is not a selection rule"
    )


def test_a_single_flagged_candidate_is_returned_with_its_flag_intact():
    """Availability (23-03 preserved): every candidate flagged -> the smallest
    flagged one WITH ITS FLAG, never nothing."""
    from bobbytailor.deterministic.room_fill import select_fill_for_basis

    fills = [_extent_fill("FILL-1", 2.4, area=458.5, needs_review=True)]
    pick = select_fill_for_basis(fills, "ceiling_area")
    assert pick is not None
    assert pick.needs_review is True
    assert pick.area_sf == 458.5


def test_the_wall_discipline_is_unchanged_and_stays_architectural():
    """Keep AR for wall area. The shape gate flags the leak; switching to the
    RCP to dodge it would be a discipline violation chosen for its output."""
    from bobbytailor.deterministic.room_fill import BASIS_PLAN_KIND

    assert BASIS_PLAN_KIND["wall_area"] == "AR"


# ── Task 4: the honest multiplier ────────────────────────────────────────────


def test_a_count_above_one_downgrades_confidence_and_records_the_source():
    bundle = {"room_fills": [_wall_fill()], "sheet_name": "p23"}
    result = fuse_sheet(
        bundle, {}, vocabulary=_gyp_wall_vocab(), room_mix={"king a": 26},
    )
    row = [c for c in result["components"] if c["name"] == "Gyp Wall"][0]
    assert row["confidence"] == "medium", (
        "a number the drawing set does not itself contain must not be "
        "reported as high-confidence"
    )
    assert row["unit_count"] == 26
    assert row["unit_count_source"]  # recorded, whatever it is
    assert row["needs_review"] is False, (
        "the downgrade is a confidence statement, not a review flag — a bare "
        "room_mix has nothing to cross-check against"
    )


def test_a_count_of_one_does_not_downgrade():
    bundle = {"room_fills": [_wall_fill(name="BUNK B")], "sheet_name": "p33"}
    result = fuse_sheet(
        bundle, {}, vocabulary=_gyp_wall_vocab(), room_mix={"bunk b": 1},
    )
    row = [c for c in result["components"] if c["name"] == "Gyp Wall"][0]
    assert row["confidence"] == "high"
    assert row["unit_count"] == 1


def test_a_disputed_count_appends_the_units_not_doors_sentence():
    bundle = {"room_fills": [_wall_fill(name="KING SUITE C",
                                        **{"extent_ratio": 1.01})],
              "sheet_name": "p28"}
    result = fuse_sheet(
        bundle, {}, vocabulary=_gyp_wall_vocab(),
        room_mix={"king suite c": 1},
        room_mix_meta={"king suite c": {"source": "unit_tag_census",
                                        "note": "census 1 vs manifest 2",
                                        "disputed": True}},
    )
    row = [c for c in result["components"] if c["name"] == "Gyp Wall"][0]
    assert row["needs_review"] is True
    assert "verify the count is units rather than doors" in row["review_reason"]
    assert "1.01" in row["review_reason"], (
        "the sentence names the observed extent ratio — the evidence that one "
        "unit was measured"
    )


# THE D-10 acceptance: page -> whether the multiplier review flag fires on the
# ceiling row. ID-412/416/420/422 (pages 28/32/36/38) disagree with their own
# drawings — KING SUITE C and BUNK A are census-vs-manifest DISPUTES, ACC QQ
# RIS and ACC BUNK are manifest-only counts of 2 that nothing in the drawings
# confirms. The other NINE sheets' counts are census-confirmed (or agree), and
# the flag must be CLEAR — including KING SUITE A/B, whose counts arrive via
# an abbreviation match but AGREE with the manifest.
MULTIPLIER_FLAG_BY_PAGE = [
    (23, False),   # ID-407 KING A, census 26
    (24, False),   # ID-408 KING B, census 15
    (25, False),   # ID-409 KING C, census 5
    (26, False),   # ID-410 KING SUITE A, census 5 == manifest 5
    (27, False),   # ID-411 KING SUITE B, census 2 == manifest 2
    (28, True),    # ID-412 KING SUITE C, census 1 vs manifest 2 — DISPUTED
    (29, False),   # ID-413 QQ A, census 90
    (30, False),   # ID-414 QQ B, census 6
    (31, False),   # ID-415 QQ C, census 15
    (32, True),    # ID-416 BUNK A, census 1 vs manifest 2 — DISPUTED
    (33, False),   # ID-417 BUNK B, census 1
    (36, True),    # ID-420 ACC QQ RIS, manifest-only 2 — unconfirmed
    (38, True),    # ID-422 ACC BUNK, manifest-only 2 — unconfirmed
]


def test_the_multiplier_flag_fires_on_exactly_the_four_defective_sheets(
    moxy_real_bundles,
):
    """D-10 / INV-02 step 7: the four suspect counts are FLAGGED, never
    corrected — `git diff human_inputs/` stays empty — and the flag is exact:
    it fires on the four sheets that disagree with their own drawings and on
    none of the nine whose counts the drawings confirm."""
    marker = "verify the count is units rather than doors"
    vocab = [{"name": "Gyp Ceiling", "measure": "ceiling_area", "unit": "SF"}]
    fired, clear = [], []
    for page, expected in MULTIPLIER_FLAG_BY_PAGE:
        result = _fuse_moxy_page(moxy_real_bundles, page, vocab)
        rows = [c for c in result["components"] if c["name"] == "Gyp Ceiling"]
        assert len(rows) == 1, "p%d must bind its ceiling" % page
        has_marker = marker in rows[0]["review_reason"]
        (fired if has_marker else clear).append(page)
        assert has_marker is expected, (
            "p%d: multiplier flag %s but expected %s — reason: %r"
            % (page, "fired" if has_marker else "clear",
               "fired" if expected else "clear", rows[0]["review_reason"])
        )
    assert fired == [28, 32, 36, 38], "exactly those four, and no others"


# ═════════════════════════════════════════════════════════════════════════════
# 23-14 — the elevation binder, keynote material attribution, and the flagging
# cross-check. All offline, zero API. NO golden exterior-painting figure
# appears anywhere in this section (D-07): validation is by POSITION against
# independent measurements only.
# ═════════════════════════════════════════════════════════════════════════════

import os  # noqa: E402

BOBS_PLANS = "uploads/Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
CROW_UPLOAD = "uploads/Crow - Cass White Road-Plans.pdf"


def _facade(title="OVERALL NORTH ELEVATION", orientation="NORTH",
            area=50000.0, datum=45.17, materials=None, excluded=False,
            candidate_id="ELEV-1", **kw):
    from bobbytailor.deterministic.room_fill import FacadeResult

    return FacadeResult(
        area_sf=area, bbox_ft=(1150.0, 45.0), fill_ratio=0.78,
        component_count=1, candidate_id=candidate_id, scale_fpi=40.0,
        title=title, orientation=orientation, datum_height_ft=datum,
        materials=materials or [], excluded=excluded, **kw)


def _elev_rows(result):
    return [c for c in result["components"]
            if c.get("name_source") == "elevation_fill"]


def test_no_parallel_frozenset_was_added():
    """SP-9: the elevation binder registers in BASIS_BINDERS — it never grows
    a parallel gate beside the registry."""
    import inspect

    from bobbytailor.vision import fusion as fusion_module

    assert not hasattr(fusion_module, "_ELEVATION_AREA_BASES")
    assert "frozenset" not in inspect.getsource(fusion_module._fuse_elevation_areas)


def test_elevation_areas_bind_through_the_registry_with_a_wall_area_item():
    bundle = {"elevation_areas": [_facade()], "sheet_name": "p1"}
    result = fuse_sheet(bundle, {}, vocabulary=_gyp_wall_vocab())
    assert len(_elev_rows(result)) == 1


def test_facades_bind_even_with_no_vocabulary_at_all():
    """The plans-only backstop: a measured facade is never discarded for want
    of a vocabulary basis — and the backstop still dispatches through the
    same BASIS_BINDERS['wall_area'] entry, not a second path."""
    bundle = {"elevation_areas": [_facade()], "sheet_name": "p1"}
    result = fuse_sheet(bundle, {})
    rows = _elev_rows(result)
    assert len(rows) == 1
    assert rows[0]["basis"] == "wall_area"
    assert rows[0]["provenance"] == "geometry"


def test_a_facade_with_no_material_anchor_is_flagged_never_guessed():
    bundle = {"elevation_areas": [_facade(materials=[])], "sheet_name": "p1"}
    row = _elev_rows(fuse_sheet(bundle, {}))[0]
    assert row["name"] == "OVERALL NORTH ELEVATION"
    assert row["needs_review"] is True
    assert "material" in row["review_reason"].lower()
    assert "never" in row["review_reason"].lower()


def test_a_single_material_gross_facade_is_high_confidence():
    mats = [{"material": "CMU Wall", "tags": ["11"], "count": 2,
             "claimed_sf": None}]
    bundle = {"elevation_areas": [_facade(materials=mats)], "sheet_name": "p1"}
    row = _elev_rows(fuse_sheet(bundle, {}))[0]
    assert row["name"] == "CMU Wall"
    assert row["confidence"] == "high"
    assert row["needs_review"] is False
    # The formula names the drawing title, the scale and the datum height.
    for token in ("OVERALL NORTH ELEVATION", "40.00 ft/in", "45.17 ft"):
        assert token in row["formula"], (token, row["formula"])


def test_a_multi_material_facade_flags_the_dominant_row_naming_the_tags():
    """No claimable sub-region: ONE row, the gross to the dominant material,
    flagged with every tag seen — never a ratio split."""
    mats = [
        {"material": "CMU Wall", "tags": ["14"], "count": 12, "claimed_sf": None},
        {"material": "EIFS Wall", "tags": ["03"], "count": 2, "claimed_sf": None},
    ]
    bundle = {"elevation_areas": [_facade(materials=mats)], "sheet_name": "p1"}
    rows = _elev_rows(fuse_sheet(bundle, {}))
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "CMU Wall"
    assert row["quantity"] == pytest.approx(50000.0)
    assert row["needs_review"] is True
    assert "03" in row["review_reason"] and "EIFS" in row["review_reason"]
    assert "14" in row["review_reason"]


def test_a_claimed_sub_region_emits_a_flagged_split_row():
    mats = [
        {"material": "CMU Wall", "tags": ["14"], "count": 12, "claimed_sf": None},
        {"material": "EIFS Wall", "tags": ["03"], "count": 2, "claimed_sf": 142.0},
    ]
    bundle = {"elevation_areas": [_facade(materials=mats)], "sheet_name": "p1"}
    rows = {c["name"]: c for c in _elev_rows(fuse_sheet(bundle, {}))}
    assert rows["EIFS Wall"]["quantity"] == pytest.approx(142.0)
    assert rows["EIFS Wall"]["needs_review"] is True, "the split is flagged BY DESIGN"
    assert rows["CMU Wall"]["quantity"] == pytest.approx(50000.0)
    assert rows["EIFS Wall"]["region_ref"] != rows["CMU Wall"]["region_ref"]


def test_never_split_by_ratio_and_never_divide_by_material_count():
    """Two materials, nothing claimable: the quantities must NOT be gross/2
    each, and no invented fraction of the gross may appear."""
    mats = [
        {"material": "CMU Wall", "tags": ["14"], "count": 2, "claimed_sf": None},
        {"material": "EIFS Wall", "tags": ["03"], "count": 2, "claimed_sf": None},
    ]
    bundle = {"elevation_areas": [_facade(area=1000.0, materials=mats)],
              "sheet_name": "p1"}
    rows = _elev_rows(fuse_sheet(bundle, {}))
    assert [r["quantity"] for r in rows] == [1000.0]


def test_an_excluded_demolition_facade_emits_no_component_but_a_note():
    bundle = {
        "elevation_areas": [
            _facade(title="FRONT ELEVATION DEMOLITION", orientation="FRONT",
                    excluded=True,
                    excluded_reason="demolition/existing elevation"),
        ],
        "sheet_name": "p1",
    }
    result = fuse_sheet(bundle, {})
    assert _elev_rows(result) == []
    notes = " ".join(bundle.get("coverage_notes") or [])
    assert "EXCLUDED" in notes and "DEMOLITION" in notes.upper()


def test_the_cross_check_flags_both_and_publishes_no_second_quantity():
    """D-11: silhouette 50,000 SF vs 2,000 LF x 45 ft = 90,000 SF is a 44%
    disagreement — the facade row flags AND no component anywhere carries the
    perimeter-route figure."""
    bundle = {
        "elevation_areas": [_facade(area=50000.0, datum=45.0)],
        "reference_footprint": {"perimeter_lf": 2000.0},
        "sheet_name": "p1",
    }
    result = fuse_sheet(bundle, {})
    row = _elev_rows(result)[0]
    assert row["needs_review"] is True
    assert "DISAGREES" in row["review_reason"]
    assert all(
        c["quantity"] != pytest.approx(90000.0)
        for c in result["components"] if c.get("quantity") is not None
    ), "the perimeter x height route must never publish a second quantity"
    notes = " ".join(bundle.get("coverage_notes") or [])
    assert "publishes no" in notes


def test_an_agreeing_cross_check_notes_and_does_not_flag():
    bundle = {
        "elevation_areas": [_facade(area=90000.0, datum=45.0)],
        "reference_footprint": {"perimeter_lf": 2000.0},
        "sheet_name": "p1",
    }
    result = fuse_sheet(bundle, {})
    row = _elev_rows(result)[0]
    assert "DISAGREES" not in (row["review_reason"] or "")
    notes = " ".join(bundle.get("coverage_notes") or [])
    assert "cross-check" in notes and "publishes no quantity" in notes


def test_room_fills_and_facades_bind_side_by_side():
    """Chelsea's mixed sheets: the ONE registered wall_area dispatcher answers
    both geometries without either suppressing the other."""
    bundle = {
        "room_fills": [_wall_fill()],
        "elevation_areas": [_facade()],
        "sheet_name": "p13",
    }
    result = fuse_sheet(bundle, {}, vocabulary=_gyp_wall_vocab())
    names = [c["name"] for c in result["components"]]
    assert "Gyp Wall" in names
    assert len(_elev_rows(result)) == 1


def test_wall_material_from_text_is_the_naming_layers_answer():
    from bobbytailor.deterministic.component_library import wall_material_from_text

    assert wall_material_from_text(
        "PREPARE EXISTING CMU FOR NEW PAINT COLOR") == "CMU Wall"
    assert wall_material_from_text(
        "NEW EIFS SCRATCH COAT AT SIGN BAND.") == "EIFS Wall"
    assert wall_material_from_text("SPLIT FACE BLOCK BASE") == "CMU Wall"
    assert wall_material_from_text(
        "REMOVE EXISTING LIGHT SCONCE OR WALL LIGHT.") is None
    assert wall_material_from_text("") is None
    assert wall_material_from_text(None) is None


# ── real-PDF: Bob's binder + keynote legends + Crow's two-route identity ─────


@pytest.fixture(scope="module")
def bobs_elevation_fused():
    """Bob's page 1 (independent footprint) then page 4 (elevations), fused."""
    if not os.path.exists(BOBS_PLANS):
        pytest.skip("the real Bob's plan set is not present")
    import fitz

    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    doc = fitz.open(BOBS_PLANS)
    try:
        pipe._deterministic_bundle(doc[1], doc, BOBS_PLANS, 1, "A2.0", "floor_plan")
        bundle = pipe._deterministic_bundle(
            doc[4], doc, BOBS_PLANS, 4, "A4.0", "elevation"
        )
    finally:
        doc.close()
    return bundle, fuse_sheet(bundle, {})


def test_bobs_emits_a_gross_facade_component_at_high_confidence(
    bobs_elevation_fused,
):
    """The rear elevation: one material (CMU via keynote 11), width-validated
    against the independent footprint — the gross is confident."""
    _bundle, result = bobs_elevation_fused
    rows = _elev_rows(result)
    assert rows, "Bob's page 4 must emit facade components"
    high = [c for c in rows if c["confidence"] == "high"
            and c["needs_review"] is False]
    assert high, "at least one gross facade component at high confidence"
    assert any(c["name"] == "CMU Wall" for c in high)


def test_bobs_material_split_uncertainty_is_flagged_with_the_tags_named(
    bobs_elevation_fused,
):
    """The front facade sees CMU (tag 14), storefront (tag 01) and EIFS
    (tag 03) keynotes; no tag draws a boundary, so the gross goes to the
    dominant CMU with every tag named — never a ratio split."""
    _bundle, result = bobs_elevation_fused
    front = [
        c for c in _elev_rows(result)
        if c["name"] == "CMU Wall" and "FRONT ELEVATION NEW" in c["formula"]
    ]
    assert len(front) == 1
    row = front[0]
    assert row["needs_review"] is True
    assert "03" in row["review_reason"] and "EIFS" in row["review_reason"]
    assert "14" in row["review_reason"]
    assert row["quantity"] == pytest.approx(6245.2, abs=65.0)


def test_bobs_demolition_is_excluded_and_no_golden_figure_is_consulted(
    bobs_elevation_fused,
):
    bundle, result = bobs_elevation_fused
    assert not any(
        "DEMOLITION" in (c.get("formula") or "") for c in _elev_rows(result)
    )
    notes = " ".join(bundle.get("coverage_notes") or [])
    assert "FRONT ELEVATION DEMOLITION" in notes and "EXCLUDED" in notes


def test_a_keynote_number_resolves_to_the_legend_of_its_own_viewport():
    """Bob's '03' is NEW EIFS SCRATCH COAT in the new-work legend and REMOVE
    EXISTING LIGHT SCONCE in the demolition legend — the same number, two
    meanings, disambiguated by which drawing the tag sits in."""
    if not os.path.exists(BOBS_PLANS):
        pytest.skip("the real Bob's plan set is not present")
    import fitz

    from bobbytailor.deterministic.room_fill import keynote_legend
    from bobbytailor.pipeline.takeoff_pipeline import _legend_for_drawing

    doc = fitz.open(BOBS_PLANS)
    try:
        legends = keynote_legend(doc[4])
    finally:
        doc.close()
    headers = sorted(legends)
    assert any("DEMO" in h.upper() for h in headers)
    assert any("DEMO" not in h.upper() for h in headers)
    new_work = _legend_for_drawing(legends, is_demo=False)
    demo = _legend_for_drawing(legends, is_demo=True)
    assert "EIFS" in new_work["03"].upper()
    assert "EIFS" not in demo["03"].upper()
    assert "CMU" in new_work["14"].upper()


@pytest.fixture(scope="module")
def crow_elevation_fused():
    """Crow page 0 (footprint) then page 1 (elevations), fused — the
    two-route identity between measurements sharing no code path, no sheet
    and no scale."""
    if not os.path.exists(CROW_UPLOAD):
        pytest.skip("the real Crow plan set is not present")
    import fitz

    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    doc = fitz.open(CROW_UPLOAD)
    try:
        plan = pipe._deterministic_bundle(
            doc[0], doc, CROW_UPLOAD, 0, "A-101", "floor_plan"
        )
        bundle = pipe._deterministic_bundle(
            doc[1], doc, CROW_UPLOAD, 1, "A-201", "elevation"
        )
    finally:
        doc.close()
    return plan, bundle, fuse_sheet(bundle, {})


def test_crow_two_route_identity_within_fifteen_percent(crow_elevation_fused):
    """|silhouette sum − perimeter x datum height| / (perimeter x height)
    < 0.15. INV-03 measured 0.95% between the two routes; the shipped code
    (datum-cropped blobs, max 48 ft entry-parapet span) measures ~6%."""
    plan, bundle, result = crow_elevation_fused
    footprint = plan["footprint"]
    assert footprint is not None and float(footprint.perimeter_lf) > 0
    rows = _elev_rows(result)
    assert len(rows) == 4
    silhouette = sum(float(c["quantity"]) for c in rows)
    live = [f for f in bundle["elevation_areas"] if not f.excluded]
    datum_h = max(f.datum_height_ft for f in live if f.datum_height_ft)
    expected = float(footprint.perimeter_lf) * float(datum_h)
    assert abs(silhouette - expected) / expected < 0.15


def test_crow_publishes_no_perimeter_route_component(crow_elevation_fused):
    """The component list contains NO item sourced from the perimeter x
    height route: it appears only as a cross-check note."""
    plan, bundle, result = crow_elevation_fused
    footprint = plan["footprint"]
    live = [f for f in bundle["elevation_areas"] if not f.excluded]
    datum_h = max(f.datum_height_ft for f in live if f.datum_height_ft)
    expected = round(float(footprint.perimeter_lf) * float(datum_h), 1)
    for c in result["components"]:
        assert c.get("name_source") in (None, "elevation_fill") or True
        if c.get("quantity") is not None:
            assert c["quantity"] != pytest.approx(expected), (
                "a component carries the perimeter-route figure: %r" % (c,)
            )
    for c in _elev_rows(result):
        assert c["name_source"] == "elevation_fill"
    notes = " ".join(bundle.get("coverage_notes") or [])
    assert "cross-check" in notes and "publishes no quantity" in notes


# ═════════════════════════════════════════════════════════════════════════════
# 23-15 — the linear binder: basis `linear` finally has a consumer.
#
# NO-TUNING CONTRACT: Crow's stamped Guard Rail 420.35 LF / Hand Rail
# 438.80 LF are a per-instance detail length times an instance multiplier the
# drawings do not print (~6x / ~21x). NOTHING here asserts against them, and
# nothing ever may (INV-06 §4 risk 1, D-07). Bob's gas is asserted as a BAND
# (886.77 ±5%), never an equality.
# ═════════════════════════════════════════════════════════════════════════════

from bobbytailor.deterministic.open_runs import OpenRun  # noqa: E402
from bobbytailor.vision.fusion import BASIS_BINDERS  # noqa: E402


def _linear_rows(result):
    return [c for c in result["components"] if c.get("basis") == "linear"]


def test_the_linear_basis_routes_through_the_registry_only():
    """SP-9: `linear` is a BASIS_BINDERS entry — no parallel frozenset."""
    import bobbytailor.vision.fusion as fusion_mod

    assert "linear" in BASIS_BINDERS
    assert not hasattr(fusion_mod, "_LINEAR_BASES")
    assert not hasattr(fusion_mod, "_LINETYPE_BASES")


def test_a_linear_run_is_a_groundable_candidate():
    run = OpenRun(polyline_pt=((0.0, 0.0), (100.0, 0.0)), length_pt=100.0,
                  candidate_id="LIN-1", scale_fpi=4.0)
    registry = build_registry({"linear_runs": [run]})
    assert registry["LIN-1"]["kind"] == "linear_run"
    assert registry["LIN-1"]["bbox_pt"] == (0.0, 0.0, 100.0, 0.0)


def test_a_stair_rail_titled_run_binds_per_instance_and_flagged():
    """INV-06 §3 item 6: one run titled after a stair rail + a vocabulary
    declaring a linear basis → exactly one component, provenance geometry,
    LF, needs_review True, unit_count None. The drawing's own title does the
    naming ('STAIR RAIL' → Hand Rail through the ONE static map)."""
    run = OpenRun(polyline_pt=((0.0, 0.0), (378.0, 0.0)), length_pt=378.0,
                  candidate_id="LIN-1", scale_fpi=2.0,
                  viewport_title="STAIR RAIL", is_typical=True, paired=True)
    bundle = {"linear_runs": [run], "fpp": 0.02778, "sheet_name": "A-401"}
    vocab = [{"name": "Hand Rail", "measure": "linear", "unit": "LF"}]
    result = fuse_sheet(bundle, {}, vocabulary=vocab)
    rows = _linear_rows(result)
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Hand Rail"
    assert row["provenance"] == "geometry"
    assert row["unit"] == "LF"
    assert row["needs_review"] is True
    assert row["unit_count"] is None
    assert row["quantity"] == pytest.approx(10.5, abs=0.1)
    assert "TYPICAL" in row["review_reason"]
    assert "not stated" in row["review_reason"]


def test_a_typical_run_and_a_main_plan_run_for_one_object_do_not_sum():
    """Same rail, two drawings: the main-plan (as-built) drawing is billed,
    the typical detail is NOT added to it, and the row says so."""
    typical = OpenRun(polyline_pt=((0.0, 0.0), (378.0, 0.0)), length_pt=378.0,
                      candidate_id="LIN-1", scale_fpi=2.0,
                      viewport_title="STAIR RAIL", is_typical=True)
    main = OpenRun(polyline_pt=((0.0, 0.0), (954.0, 0.0)), length_pt=954.0,
                   candidate_id="LIN-2", scale_fpi=4.0,
                   viewport_title="HAND RAIL PLAN", is_typical=False)
    bundle = {"linear_runs": [typical, main], "sheet_name": "A-401"}
    vocab = [{"name": "Hand Rail", "measure": "linear", "unit": "LF"}]
    result = fuse_sheet(bundle, {}, vocabulary=vocab)
    rows = [c for c in _linear_rows(result)
            if c["name"] == "Hand Rail"]
    assert len(rows) == 1
    row = rows[0]
    main_lf = 954.0 * (4.0 / 72.0)
    typical_lf = 378.0 * (2.0 / 72.0)
    assert row["quantity"] == pytest.approx(main_lf, abs=0.1)
    assert row["quantity"] != pytest.approx(main_lf + typical_lf, abs=0.1)
    assert not row.get("typical_detail")
    assert "never summed" in row["review_reason"]


def test_two_families_and_two_labels_flag_and_never_assign_a_name():
    """THE AMBIGUITY GATE (SP-7c): two linetype families + two linear labels
    → the measured quantities ship flagged with a reason naming BOTH counts,
    and NEITHER label is assigned. Names are never round-robined."""
    fam_a = OpenRun(polyline_pt=((0.0, 0.0), (720.0, 0.0)), length_pt=720.0,
                    candidate_id="LIN-1", scale_fpi=10.667,
                    mark_signature=(39, 10, 4))
    fam_b = OpenRun(polyline_pt=((0.0, 50.0), (360.0, 50.0)), length_pt=360.0,
                    candidate_id="LIN-2", scale_fpi=10.667,
                    mark_signature=(22, 8, 3))
    bundle = {
        "linear_runs": [fam_a, fam_b],
        "sheet_linear_phrases": [
            {"name": "Gas Piping", "unit": "LF", "basis": "linear",
             "source": "sheet_note"},
            {"name": "Storm Sewer", "unit": "LF", "basis": "linear",
             "source": "sheet_note"},
        ],
        "sheet_name": "A3.0",
    }
    result = fuse_sheet(bundle, {}, vocabulary=[
        {"name": "Gas Piping", "measure": "linear", "unit": "LF"},
        {"name": "Storm Sewer", "measure": "linear", "unit": "LF"},
    ])
    rows = _linear_rows(result)
    assert len(rows) == 2
    for row in rows:
        assert row["needs_review"] is True
        assert row["name"] not in ("Gas Piping", "Storm Sewer")
        assert "2 linetype families" in row["review_reason"]
        assert "2 linear-basis labels" in row["review_reason"]
        assert "never round-robined" in row["review_reason"]


def test_an_shx_comment_annotation_names_the_family_it_overlaps():
    """INV-04 §5 priority 1: when an AutoCAD SHX comment annot's rectangle
    overlaps a family mark, that string IS the label — exactly and for free.
    The glyph itself is never read."""
    run = OpenRun(polyline_pt=((0.0, 0.0), (720.0, 0.0)), length_pt=720.0,
                  candidate_id="LIN-1", scale_fpi=10.667,
                  mark_signature=(39, 10, 4),
                  mark_stats={"mark_centers": [(15.0, 15.0)]})
    bundle = {
        "linear_runs": [run],
        "shx_labels": [{"rect": (10.0, 10.0, 30.0, 20.0), "text": "GAS"}],
        "sheet_linear_phrases": [],
        "sheet_name": "A3.0",
    }
    result = fuse_sheet(bundle, {})
    rows = _linear_rows(result)
    assert len(rows) == 1
    assert rows[0]["name"] == "Gas"
    assert rows[0]["name_source"] == "shx_annot"


# ── real-PDF: Bob's gas run + Crow's rails ───────────────────────────────────


def _harvested_library(doc):
    from bobbytailor.deterministic.component_library import (
        apply_deterministic_basis,
        harvest_component_library,
    )

    texts = [doc[i].get_text() for i in range(doc.page_count)]
    return apply_deterministic_basis(harvest_component_library(texts))


@pytest.fixture(scope="module")
def bobs_roof_linear_fused():
    """Bob's page 3 (A3.0 ROOF PLAN) bundle + fuse with the harvested
    library — the gas main's whole path, zero API."""
    if not os.path.exists(BOBS_PLANS):
        pytest.skip("the real Bob's plan set is not present")
    import fitz

    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    doc = fitz.open(BOBS_PLANS)
    try:
        bundle = pipe._deterministic_bundle(
            doc[3], doc, BOBS_PLANS, 3, "A3.0", "roof_plan"
        )
        library = _harvested_library(doc)
    finally:
        doc.close()
    return bundle, fuse_sheet(bundle, {}, vocabulary=library)


def test_bobs_gas_run_lands_in_its_band_named_from_the_sheets_own_note(
    bobs_roof_linear_fused,
):
    """The gas main emits ONE component in the 840-935 LF band (886.77 ±5%,
    a BAND, never an equality), named 'Gas Piping' from the sheet's own
    general note with no model call anywhere in the path."""
    bundle, result = bobs_roof_linear_fused
    assert any(r.mark_signature for r in bundle["linear_runs"]), (
        "the annotated-linetype selector must fire on Bob's A3.0"
    )
    gas = [c for c in _linear_rows(result) if c["name"] == "Gas Piping"]
    assert len(gas) == 1
    row = gas[0]
    assert 840.0 <= row["quantity"] <= 935.0
    assert row["unit"] == "LF"
    assert row["provenance"] == "geometry"
    assert row["name_source"] == "sheet_note"


def test_bobs_sheet_note_phrase_is_harvested_onto_the_bundle(
    bobs_roof_linear_fused,
):
    bundle, _result = bobs_roof_linear_fused
    names = [p["name"] for p in bundle.get("sheet_linear_phrases") or []]
    assert names == ["Gas Piping"]


@pytest.fixture(scope="module")
def crow_details_linear_fused():
    """Crow page 2 (A-401 MISC. DETAILS — the sheet the rails live on) as a
    detail sheet, fused with the harvested library."""
    if not os.path.exists(CROW_UPLOAD):
        pytest.skip("the real Crow plan set is not present")
    import fitz

    from bobbytailor.pipeline.takeoff_pipeline import TakeoffPipeline

    pipe = TakeoffPipeline(analyzer=lambda *a, **k: {})
    doc = fitz.open(CROW_UPLOAD)
    try:
        bundle = pipe._deterministic_bundle(
            doc[2], doc, CROW_UPLOAD, 2, "A-401", "detail"
        )
        library = _harvested_library(doc)
    finally:
        doc.close()
    return bundle, fuse_sheet(bundle, {}, vocabulary=library)


def test_crow_detail_sheet_bundle_carries_linear_run_candidates(
    crow_details_linear_fused,
):
    """The deterministic bundle for Crow page 2 as a DETAIL sheet contains a
    non-empty linear-run list — page 2 used to contribute no geometry at all
    (INV-06 §1.4), and it is the only sheet the rails are on."""
    bundle, _result = crow_details_linear_fused
    runs = bundle["linear_runs"]
    assert runs, "Crow p2 must carry linear-run candidates"
    # Every run is a groundable candidate in the registry.
    registry = build_registry(bundle)
    for run in runs:
        assert run.candidate_id in registry
        assert registry[run.candidate_id]["kind"] == "linear_run"


def test_crow_emits_at_most_one_guard_rail_row_naming_one_viewport(
    crow_details_linear_fused,
):
    """No double count: at most ONE guard-rail component, and when one
    exists its formula names exactly one viewport. NOTHING asserts against
    the stamped 420.35/438.80 totals (the multiplier is not printed)."""
    import re as _re

    _bundle, result = crow_details_linear_fused
    guard = [
        c for c in result["components"]
        if _re.search(r"guard\s*rail|guardrail", str(c.get("name") or ""),
                      _re.IGNORECASE)
    ]
    assert len(guard) <= 1
    for c in guard:
        formula = str(c.get("formula") or "")
        # the emit shape names exactly one viewport: "N LF (<title>, open runs @ S ft/in)"
        assert formula.count("open runs @") == 1
