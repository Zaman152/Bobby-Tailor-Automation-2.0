"""Tests for shared deterministic plan-layer legend building."""
import json
from pathlib import Path

from plan_deterministic_legends import inject_project_legends, merge_page_pdfs


def test_inject_legends_prefers_floor_plan():
    legends = [{"name": "L", "rows": [{"ITEM": "X", "QTY": "1", "UNIT": "SF"}]}]
    extracted = [
        {"_sheet_type": "elevation", "_sheet_name": "A-201", "schedules": []},
        {"_sheet_type": "floor_plan", "_sheet_name": "A-101", "schedules": []},
    ]
    inject_project_legends(extracted, legends)
    assert extracted[0].get("_companion_legend_injected") is not True
    assert len(extracted[1]["schedules"]) == 1
    assert extracted[1]["_companion_legend_injected"] is True


def test_inject_legends_only_once():
    legends = [{"name": "L", "rows": [{"ITEM": "X", "QTY": "1", "UNIT": "SF"}]}]
    extracted = [
        {"_sheet_type": "floor_plan", "_sheet_name": "A-101", "schedules": []},
        {"_sheet_type": "floor_plan", "_sheet_name": "A-111", "schedules": []},
    ]
    inject_project_legends(extracted, legends)
    assert extracted[0]["_companion_legend_injected"] is True
    assert extracted[1].get("_companion_legend_injected") is not True


def test_merge_page_pdfs_single_copy(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4 minimal")  # not valid pdf but merge skips small
    out = tmp_path / "out.pdf"
    # Too small — merge_page_pdfs filters < 500 bytes
    assert merge_page_pdfs([src], out) is None
