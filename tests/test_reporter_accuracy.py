"""Reporter wiring for Phase 16 outputs."""
import json
import tempfile
from pathlib import Path

from reporter import generate_report


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
        import config
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
        import config
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
