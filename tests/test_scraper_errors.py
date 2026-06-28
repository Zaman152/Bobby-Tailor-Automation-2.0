"""Tests for scraper filename sanitization and error helpers."""
from scraper import _safe_sheet_filename, ERROR_ALL_SHEETS_FAILED


def test_safe_sheet_filename_replaces_slash():
    assert _safe_sheet_filename("I-4.1 - ELECTRICAL/ COMMUNICATION PLAN") == (
        "I-4.1 - ELECTRICAL- COMMUNICATION PLAN"
    )


def test_safe_sheet_filename_replaces_backslash():
    assert "/" not in _safe_sheet_filename("A\\B")
    assert "\\" not in _safe_sheet_filename("A\\B")


def test_safe_sheet_filename_empty_fallback():
    assert _safe_sheet_filename("   ") == "sheet"


def test_error_constants():
    assert ERROR_ALL_SHEETS_FAILED == "all_sheets_failed"
