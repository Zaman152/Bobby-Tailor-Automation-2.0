"""Reporter wiring for Phase 16 outputs + 21-13 provenance/scale surfacing."""
import json
import tempfile
from contextlib import contextmanager
from pathlib import Path

from bobbytailor.pipeline.reporter import generate_report


@contextmanager
def _isolated_output_dir():
    with tempfile.TemporaryDirectory() as tmp:
        from bobbytailor import config
        old = config.OUTPUT_DIR
        config.OUTPUT_DIR = tmp
        try:
            yield tmp
        finally:
            config.OUTPUT_DIR = old


def _fused_extracted() -> list:
    """A stub 21-13 vector-sheet extraction (fuse_sheet output shape)."""
    return [{
        "_source_sheet": "A-101.png",
        "_sheet_name": "A-101",
        "_sheet_type": "floor_plan",
        "_tokens_in": 100,
        "_tokens_out": 50,
        "_cost_usd": 0.01,
        "_model_used": "claude-sonnet-5",
        "measurement_mode": "vector",
        "main_plan_region": "R1",
        "scale_confidence": [{
            "region_id": "R1", "kind": "main_plan", "is_main": True,
            "fpp": 0.5555, "fpi": 40.0, "confidence": "high",
            "n_inliers": 30, "inlier_share": 0.887,
            "printed_agreement": True, "door_check": None,
            "method": "ransac_consensus",
        }],
        "fusion_rejected": [{
            "name": "CMU Wall", "quantity": 17, "unit": "SF",
            "provenance": "vision_ensemble", "confidence": "low",
            "rejected_by": "geometry", "reason": "vision_quantity_blocked",
        }],
        "_budget": {"cap_usd": 10.0, "spent_usd": 0.01, "exhausted": False},
        "components": [
            {"name": "CMU Wall", "quantity": 2204.0, "unit": "LF",
             "provenance": "geometry", "confidence": "high",
             "candidate_id": "WALL-TC1", "needs_review": False},
            {"name": "Building Footprint", "quantity": 397600, "unit": "SF",
             "provenance": "text_layer", "confidence": "high"},
            {"name": "Door 101", "quantity": 1, "unit": "EA",
             "provenance": "schedule_table", "confidence": "medium"},
        ],
        "measurements": [],
    }]


# ── 21-13: provenance / scale-confidence / budget surfacing ─────────────────

def test_takeoff_json_carries_measurement_mode_scale_confidence_provenance():
    with _isolated_output_dir():
        report = generate_report("Fused Proj", _fused_extracted(), [])
        run_dir = Path(report["_files"]["run_folder"])
        with open(run_dir / "takeoff.json") as f:
            data = json.load(f)

        # Per-sheet surfacing in sheet_log.
        entry = data["sheet_log"][0]
        assert entry["measurement_mode"] == "vector"
        assert entry["main_plan_region"] == "R1"
        sc = entry["scale_confidence"]
        assert sc and sc[0]["fpi"] == 40.0
        assert sc[0]["n_inliers"] == 30
        assert sc[0]["inlier_share"] == 0.887
        assert sc[0]["printed_agreement"] is True

        # Per-item provenance on raw component rows.
        comps = [i for i in data["raw_line_items"] if i["category"] == "component"]
        provs = {c["description"]: c["provenance"] for c in comps}
        assert provs["CMU Wall"] == "geometry"
        assert provs["Building Footprint"] == "text_layer"
        assert provs["Door 101"] == "schedule_table"

        # Run-level budget block + fusion_rejected audit list.
        assert data["budget"] == {"cap_usd": 10.0, "spent_usd": 0.01, "exhausted": False}
        assert data["fusion_rejected"][0]["reason"] == "vision_quantity_blocked"
        assert data["fusion_rejected"][0]["sheet"] == "A-101"


def test_summary_txt_has_scale_confidence_and_provenance_sections():
    with _isolated_output_dir():
        report = generate_report("Fused Proj", _fused_extracted(), [])
        text = Path(report["_files"]["summary_txt"]).read_text()
        assert "SCALE CONFIDENCE" in text
        assert "PROVENANCE BREAKDOWN" in text
        # Main-plan solve line: fpi, confidence, method.
        assert '1" = 40\'' in text
        assert "conf=high" in text
        assert "ransac_consensus" in text
        # Provenance counts + the deterministic share the gate asserts on.
        assert "geometry" in text
        assert "Geometry/text-derived quantities: 3/3 (100.0%" in text
        # Budget accounting under API USAGE.
        assert "Budget:" in text
        assert "$10.00 cap" in text


def test_pre21_report_renders_without_new_fields():
    """Regression: pre-21 extraction dicts (no measurement_mode /
    scale_confidence / provenance / _budget) must render without KeyError,
    and the new sections degrade gracefully."""
    extracted = [{
        "_source_sheet": "A1",
        "_tokens_in": 0,
        "_tokens_out": 0,
        "_cost_usd": 0,
        "components": [{"name": "Door", "quantity": 4, "unit": "ea"}],
    }]
    with _isolated_output_dir():
        report = generate_report("Old Shape", extracted, [])
        run_dir = Path(report["_files"]["run_folder"])
        with open(run_dir / "takeoff.json") as f:
            data = json.load(f)
        assert data["budget"] is None
        assert data["fusion_rejected"] == []
        assert data["sheet_log"][0]["measurement_mode"] is None
        assert data["sheet_log"][0]["scale_confidence"] is None
        text = Path(report["_files"]["summary_txt"]).read_text()
        assert "SCALE CONFIDENCE" in text
        assert "(no per-viewport scale data recorded)" in text
        assert "(no provenance-tagged items recorded)" in text
        assert "Budget:" not in text  # no guard recorded on pre-21 runs


def test_generate_report_includes_takeoff_summary_and_cross_refs():
    extracted = [{
        "_source_sheet": "A1",
        "_tokens_in": 0,
        "_tokens_out": 0,
        "_cost_usd": 0,
        "schedules": [{
            "name": "Spec Table",
            "table_purpose": "specification_reference",
            "lookup_key": "SIZE",
            "rows": [{"SIZE": "12"}],
        }],
    }]
    estimates = [{
        "item_type": "flooring",
        "description": "room floor",
        "quantity": 100,
        "unit": "sq_ft",
        "formula": "100 × 1.1",
        "source_sheet": "A1",
        "table_used": "flooring",
    }]
    cross_refs = [{"from_sheet": "A1", "resolution_status": "target_sheet_not_found"}]

    with tempfile.TemporaryDirectory() as tmp:
        from bobbytailor import config
        old = config.OUTPUT_DIR
        config.OUTPUT_DIR = tmp
        try:
            report = generate_report("Test Proj", extracted, estimates, cross_references=cross_refs)
            run_dir = Path(report["_files"]["run_folder"])
            assert (run_dir / "takeoff_summary.csv").exists()
            with open(run_dir / "takeoff.json") as f:
                data = json.load(f)
            assert "takeoff_summary" in data
            assert len(data["takeoff_summary"]) >= 1
            assert data["cross_references"] == cross_refs
            assert len(data["specification_tables"]) == 1
        finally:
            config.OUTPUT_DIR = old


def test_summary_txt_includes_linkage_sections():
    extracted = [{
        "_source_sheet": "A-1",
        "_tokens_in": 0,
        "_tokens_out": 0,
        "_cost_usd": 0,
    }]
    cross_refs = [{
        "from_sheet": "A-1",
        "ref_sheet": "C-4",
        "ref_number": "17",
        "item_described": "BB CI#2",
        "resolution_status": "resolved",
        "resolved_spec": {"schedule_name": "Details"},
    }]
    linked_added = [{
        "page_id": 101,
        "sheet_name": "C-4 - CIVIL SITE PLAN",
        "ref_from": "A-1",
    }]

    with tempfile.TemporaryDirectory() as tmp:
        from bobbytailor import config
        old = config.OUTPUT_DIR
        config.OUTPUT_DIR = tmp
        try:
            report = generate_report(
                "Test Proj",
                extracted,
                [],
                cross_references=cross_refs,
                linked_sheets=linked_added,
            )
            summary_path = Path(report["_files"]["summary_txt"])
            text = summary_path.read_text()
            assert "LINKED SHEETS & CROSS-REFERENCES" in text
            assert "Auto-included linked detail sheets: 1" in text
            assert "C-4 - CIVIL SITE PLAN" in text
            assert "Drawing cross-references: 1 total, 1 resolved" in text
            assert "detail 17 on C-4" in text
            assert "[RESOLVED]" in text
        finally:
            config.OUTPUT_DIR = old
