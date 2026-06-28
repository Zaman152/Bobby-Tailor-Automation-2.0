"""Tests for HD screenshot → sheet matching."""
from pathlib import Path

from sheet_preview import _normalize_sheet_key, _match_png_to_page_id, find_screenshot_paths


def test_normalize_sheet_key():
    assert _normalize_sheet_key("  I-1.1  ") == "i-1.1"


def test_match_png_by_sheet_name(tmp_path):
    png = tmp_path / "003_I-2.1 - ELECTRICAL PLAN.png"
    png.write_bytes(b"\x89PNG\r\n")
    name_to_page = {_normalize_sheet_key("I-2.1 - ELECTRICAL PLAN"): 42}
    preview_map = {}
    _match_png_to_page_id(png, name_to_page, preview_map)
    assert preview_map[42] == png


def test_match_debug_page_id(tmp_path):
    png = tmp_path / "_debug_99.png"
    png.write_bytes(b"\x89PNG\r\n")
    _match_png_to_page_id(png, {}, preview_map := {})
    assert preview_map[99] == png


def test_find_screenshot_paths_project_prefix(tmp_path, monkeypatch):
    import sheet_preview as sp

    proj_dir = tmp_path / "My_Project_20260101_120000"
    proj_dir.mkdir()
    (proj_dir / "001_Sheet A.png").write_bytes(b"x")

    monkeypatch.setattr(sp, "SCREENSHOTS_DIR", str(tmp_path))
    plans = [{"page_id": 7, "sheet_name": "Sheet A"}]
    found = find_screenshot_paths(1, "My Project", plans)
    assert found[7] == proj_dir / "001_Sheet A.png"


def test_find_screenshot_paths_jpg_extension(tmp_path, monkeypatch):
    import sheet_preview as sp

    proj_dir = tmp_path / "My_Project_20260101_120000"
    proj_dir.mkdir()
    (proj_dir / "001_Sheet A.jpg").write_bytes(b"x")

    monkeypatch.setattr(sp, "SCREENSHOTS_DIR", str(tmp_path))
    plans = [{"page_id": 7, "sheet_name": "Sheet A"}]
    found = find_screenshot_paths(1, "My Project", plans)
    assert found[7] == proj_dir / "001_Sheet A.jpg"
