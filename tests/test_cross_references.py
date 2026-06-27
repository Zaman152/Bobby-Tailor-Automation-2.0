"""Cross-reference resolution tests."""
from cross_references import find_detail_in_extraction, resolve_cross_references


def test_find_detail_in_schedule():
    ext = {
        "schedules": [{
            "name": "Details",
            "rows": [{"DETAIL": "17", "DESC": "Catch basin"}],
        }],
    }
    found = find_detail_in_extraction(ext, "17")
    assert "from_schedule" in found


def test_resolve_cross_reference_found():
    sheet_a = {
        "_source_sheet": "A-1",
        "cross_references": [{
            "ref_number": "17",
            "ref_sheet": "C-4",
            "item_described": "BB CI#2",
        }],
    }
    sheet_c = {
        "_source_sheet": "C-4",
        "sheet_title": "C-4 Civil",
        "schedules": [{"name": "D", "rows": [{"NO": "17", "TYPE": "CB"}]}],
        "cross_references": [],
    }
    resolved = resolve_cross_references([sheet_a, sheet_c])
    assert len(resolved) == 1
    assert resolved[0]["resolution_status"] == "resolved"
    assert resolved[0]["resolved_spec"] is not None


def test_resolve_target_missing():
    sheet_a = {
        "_source_sheet": "A-1",
        "cross_references": [{"ref_number": "9", "ref_sheet": "Z-9", "item_described": "x"}],
    }
    resolved = resolve_cross_references([sheet_a])
    assert resolved[0]["resolution_status"] == "target_sheet_not_found"
