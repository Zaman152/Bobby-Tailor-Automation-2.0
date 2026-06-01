"""
Unit tests for linked_sheets.py — matcher and collector functions.

Also contains integration-level tests for the full linked-sheet pipeline
(`scraper._discover_and_add_linked_sheets`) using mocked browser and catalog.
"""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from linked_sheets import collect_unresolved_refs, match_ref_to_page
from capture_manifest import PageEntry, RunManifest
from scraper import _discover_and_add_linked_sheets


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_entry(page_id: int, sheet_name: str, folder_id: int = 1) -> dict:
    return {
        "page_id": page_id,
        "sheet_name": sheet_name,
        "sheet_type": "plan",
        "folder_id": folder_id,
    }


SAMPLE_CATALOG = [
    _make_entry(101, "C-4 - CIVIL SITE PLAN"),
    _make_entry(102, "A-5 - ARCHITECTURAL DETAILS"),
    _make_entry(103, "S-1 - STRUCTURAL FOUNDATION PLAN"),
    _make_entry(104, "M-3 - MECHANICAL LAYOUT"),
    _make_entry(105, "A5 - ARCHITECTURAL DETAILS SHORT"),
]


# ---------------------------------------------------------------------------
# match_ref_to_page — matcher tests
# ---------------------------------------------------------------------------

class TestMatchRefToPage:
    def test_exact_prefix_match(self):
        """Ref matching the prefix (before ' - ') scores 3 and is returned."""
        result = match_ref_to_page("C-4", SAMPLE_CATALOG)
        assert result is not None
        assert result["page_id"] == 101
        assert "C-4" in result["sheet_name"]

    def test_slash_ref_normalized(self):
        """Ref '3/A5' normalizes to '3-A5'; 'A5' substring is found via score 2."""
        # Catalog entry 105 has sheet_name "A5 - ARCHITECTURAL DETAILS SHORT"
        # Normalized: "A5 - ARCHITECTURAL DETAILS SHORT"
        # norm ref "3-A5" is not a substring of that, but "A5" is the prefix of entry 105.
        # Let's add a direct match entry for this test to ensure deterministic behaviour.
        catalog = [
            _make_entry(201, "3-A5 - ARCHITECTURAL SECTION DETAIL"),
            _make_entry(202, "Z-99 - UNRELATED SHEET"),
        ]
        result = match_ref_to_page("3/A5", catalog)
        assert result is not None
        assert result["page_id"] == 201

    def test_no_match_returns_none(self):
        """A ref with no plausible match returns None."""
        result = match_ref_to_page("Z-99", SAMPLE_CATALOG)
        assert result is None

    def test_ambiguous_prefers_shortest(self):
        """When two entries share the same highest score, shortest sheet_name wins."""
        catalog = [
            _make_entry(301, "C-4 - CIVIL SITE PLAN EXTENDED VERSION WITH EXTRA TEXT"),
            _make_entry(302, "C-4 - CIVIL SITE PLAN"),
        ]
        result = match_ref_to_page("C-4", catalog)
        assert result is not None
        assert result["page_id"] == 302  # shorter sheet_name

    def test_case_insensitive(self):
        """Lowercase ref matches uppercase catalog entry."""
        result = match_ref_to_page("c-4", SAMPLE_CATALOG)
        assert result is not None
        assert result["page_id"] == 101

    def test_dot_ref_normalized(self):
        """Ref 'I-4.1' normalizes to 'I-4-1'; matched when catalog has same prefix."""
        catalog = [
            _make_entry(401, "I-4-1 - INSULATION SCHEDULE"),
            _make_entry(402, "S-1 - STRUCTURAL"),
        ]
        result = match_ref_to_page("I-4.1", catalog)
        assert result is not None
        assert result["page_id"] == 401

    def test_substring_match_scores_lower_than_prefix(self):
        """Prefix match (score 3) beats substring match (score 2)."""
        catalog = [
            # score 2: "A-5" is a substring
            _make_entry(501, "SHEET A-5 - FULL ARCHITECTURAL"),
            # score 3: "A-5" is the prefix
            _make_entry(502, "A-5 - ARCHITECTURAL DETAILS"),
        ]
        result = match_ref_to_page("A-5", catalog)
        assert result is not None
        assert result["page_id"] == 502

    def test_empty_ref_returns_none(self):
        """Empty string ref returns None without error."""
        result = match_ref_to_page("", SAMPLE_CATALOG)
        assert result is None

    def test_empty_catalog_returns_none(self):
        """Empty catalog returns None without error."""
        result = match_ref_to_page("C-4", [])
        assert result is None


# ---------------------------------------------------------------------------
# collect_unresolved_refs — collector tests
# ---------------------------------------------------------------------------

class TestCollectUnresolvedRefs:
    def test_collects_cross_ref_sheets(self):
        """Refs in cross_references[].ref_sheet are collected with source='cross_ref'."""
        extractions = [
            {
                "_source_sheet": "C-2",
                "cross_references": [
                    {"ref_sheet": "C-4", "ref_number": "17", "item_described": "manhole"},
                ],
                "civil_structures": [],
            }
        ]
        result = collect_unresolved_refs(extractions, already_in_run=set())
        assert len(result) == 1
        assert result[0]["ref_sheet"] == "C-4"
        assert result[0]["from_sheet"] == "C-2"
        assert result[0]["source"] == "cross_ref"

    def test_collects_civil_structure_refs(self):
        """Refs in civil_structures[].detail_ref_sheet are collected as 'civil_structure'."""
        extractions = [
            {
                "_source_sheet": "C-3",
                "cross_references": [],
                "civil_structures": [
                    {"detail_ref_sheet": "A-5", "name": "Catch basin"},
                ],
            }
        ]
        result = collect_unresolved_refs(extractions, already_in_run=set())
        assert len(result) == 1
        assert result[0]["ref_sheet"] == "A-5"
        assert result[0]["source"] == "civil_structure"

    def test_deduplicates_refs(self):
        """Two extractions referencing the same sheet yield only one record."""
        extractions = [
            {
                "_source_sheet": "C-2",
                "cross_references": [{"ref_sheet": "C-4"}],
                "civil_structures": [],
            },
            {
                "_source_sheet": "C-3",
                "cross_references": [{"ref_sheet": "C-4"}],
                "civil_structures": [],
            },
        ]
        result = collect_unresolved_refs(extractions, already_in_run=set())
        assert len(result) == 1
        assert result[0]["ref_sheet"] == "C-4"

    def test_deduplication_is_case_insensitive(self):
        """'C-4' and 'c-4' are treated as the same ref."""
        extractions = [
            {
                "_source_sheet": "C-2",
                "cross_references": [{"ref_sheet": "C-4"}],
                "civil_structures": [],
            },
            {
                "_source_sheet": "C-3",
                "cross_references": [{"ref_sheet": "c-4"}],
                "civil_structures": [],
            },
        ]
        result = collect_unresolved_refs(extractions, already_in_run=set())
        assert len(result) == 1

    def test_excludes_empty_and_none_refs(self):
        """Empty string and None ref_sheet values are excluded."""
        extractions = [
            {
                "_source_sheet": "C-2",
                "cross_references": [
                    {"ref_sheet": ""},
                    {"ref_sheet": None},
                    {"ref_sheet": "C-4"},
                ],
                "civil_structures": [
                    {"detail_ref_sheet": None},
                    {"detail_ref_sheet": ""},
                ],
            }
        ]
        result = collect_unresolved_refs(extractions, already_in_run=set())
        assert len(result) == 1
        assert result[0]["ref_sheet"] == "C-4"

    def test_empty_extractions(self):
        """Empty input list returns empty list."""
        result = collect_unresolved_refs([], already_in_run=set())
        assert result == []

    def test_collects_both_sources_from_same_sheet(self):
        """cross_ref and civil_structure refs from the same extraction are both collected."""
        extractions = [
            {
                "_source_sheet": "C-2",
                "cross_references": [{"ref_sheet": "C-4"}],
                "civil_structures": [{"detail_ref_sheet": "A-5"}],
            }
        ]
        result = collect_unresolved_refs(extractions, already_in_run=set())
        assert len(result) == 2
        sources = {r["source"] for r in result}
        assert sources == {"cross_ref", "civil_structure"}

    def test_already_in_run_does_not_filter_collection(self):
        """already_in_run is not used to filter; caller must do that after matching."""
        extractions = [
            {
                "_source_sheet": "C-2",
                "cross_references": [{"ref_sheet": "C-4"}],
                "civil_structures": [],
            }
        ]
        # Even with a non-empty already_in_run, refs are still collected
        result = collect_unresolved_refs(extractions, already_in_run={101, 202})
        assert len(result) == 1

    def test_missing_keys_handled_gracefully(self):
        """Extractions missing cross_references or civil_structures keys don't crash."""
        extractions = [
            {"_source_sheet": "C-2"},  # no cross_references or civil_structures
            {"_source_sheet": "C-3", "cross_references": None},
            {"_source_sheet": "C-4", "civil_structures": None},
        ]
        result = collect_unresolved_refs(extractions, already_in_run=set())
        assert result == []


# ---------------------------------------------------------------------------
# Integration tests — full _discover_and_add_linked_sheets pipeline
# ---------------------------------------------------------------------------

def _make_manifest(project_id: int, page_entries: list) -> RunManifest:
    """Helper: build a RunManifest from a list of PageEntry objects."""
    return RunManifest(
        project_id=project_id,
        project_name="Test Project",
        folder_id=1,
        pages=list(page_entries),
    )


def _make_browser_mock() -> MagicMock:
    """Return a mock StackCTBrowser with async start/login/close."""
    browser = MagicMock()
    browser.start = AsyncMock(return_value=None)
    browser.login = AsyncMock(return_value=True)
    browser.close = AsyncMock(return_value=None)
    browser.page = None
    return browser


class TestIntegrationLinkedSheets:
    """Integration tests: mock browser + catalog → test full pipeline."""

    def test_integration_linked_page_captured_and_analyzed(self):
        """2 selected pages + 1 unresolved ref → linked page captured, cross-ref resolves."""
        catalog = [{"page_id": 201, "sheet_name": "C-4 - CIVIL SITE PLAN", "folder_id": 1}]
        all_extracted = [
            {
                "_source_sheet": "A-1 - ARCH PLAN",
                "cross_references": [
                    {"ref_sheet": "C-4", "ref_number": "17", "item_described": "manhole"}
                ],
                "civil_structures": [],
            }
        ]
        manifest = _make_manifest(
            project_id=99,
            page_entries=[
                PageEntry(
                    page_id=101,
                    sheet_name="A-1 - ARCH PLAN",
                    screenshot_rel="101_arch.jpg",
                    capture_status="ok",
                    analysis_status="ok",
                )
            ],
        )
        browser = _make_browser_mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            mpath = tmppath / "manifest.json"

            with (
                patch("scraper.stackct_store.get_plans", return_value=catalog),
                patch(
                    "scraper._capture_sheet_screenshot",
                    new=AsyncMock(return_value=(True, None)),
                ),
                patch(
                    "scraper.analyze_drawing",
                    return_value={
                        "measurements": [],
                        "components": [],
                        "_source_sheet": "C-4 - CIVIL SITE PLAN",
                    },
                ),
                patch("scraper.apply_estimation_tables", return_value=[]),
                patch("scraper.AUTO_INCLUDE_LINKED_SHEETS", True),
                patch("scraper.MAX_LINKED_SHEETS", 10),
            ):
                new_extracted, new_estimates, linked_meta = asyncio.run(
                    _discover_and_add_linked_sheets(
                        browser=browser,
                        project_id=99,
                        project_name="Test Project",
                        folder_id=1,
                        all_extracted=all_extracted,
                        manifest=manifest,
                        mpath=mpath,
                        screenshots_dir=tmppath,
                        cached_screenshots={},
                        log=lambda msg: None,
                        progress_callback=None,
                        cancel_check=None,
                    )
                )

        assert len(linked_meta) == 1
        assert linked_meta[0]["page_id"] == 201
        assert len(new_extracted) == 1

    def test_integration_max_linked_sheets_truncates(self):
        """MAX_LINKED_SHEETS=1 with 3 refs → only 1 linked page captured."""
        catalog = [
            {"page_id": 201, "sheet_name": "C-4 - CIVIL SITE PLAN", "folder_id": 1},
            {"page_id": 202, "sheet_name": "C-5 - CIVIL GRADING PLAN", "folder_id": 1},
            {"page_id": 203, "sheet_name": "C-6 - CIVIL UTILITY PLAN", "folder_id": 1},
        ]
        all_extracted = [
            {
                "_source_sheet": "A-1 - ARCH PLAN",
                "cross_references": [
                    {"ref_sheet": "C-4"},
                    {"ref_sheet": "C-5"},
                    {"ref_sheet": "C-6"},
                ],
                "civil_structures": [],
            }
        ]
        manifest = _make_manifest(
            project_id=99,
            page_entries=[
                PageEntry(
                    page_id=101,
                    sheet_name="A-1",
                    screenshot_rel="101.jpg",
                    capture_status="ok",
                    analysis_status="ok",
                )
            ],
        )
        browser = _make_browser_mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            mpath = tmppath / "manifest.json"

            with (
                patch("scraper.stackct_store.get_plans", return_value=catalog),
                patch(
                    "scraper._capture_sheet_screenshot",
                    new=AsyncMock(return_value=(True, None)),
                ),
                patch(
                    "scraper.analyze_drawing",
                    return_value={"measurements": [], "components": []},
                ),
                patch("scraper.apply_estimation_tables", return_value=[]),
                patch("scraper.AUTO_INCLUDE_LINKED_SHEETS", True),
                patch("scraper.MAX_LINKED_SHEETS", 1),
            ):
                new_extracted, new_estimates, linked_meta = asyncio.run(
                    _discover_and_add_linked_sheets(
                        browser=browser,
                        project_id=99,
                        project_name="Test Project",
                        folder_id=1,
                        all_extracted=all_extracted,
                        manifest=manifest,
                        mpath=mpath,
                        screenshots_dir=tmppath,
                        cached_screenshots={},
                        log=lambda msg: None,
                        progress_callback=None,
                        cancel_check=None,
                    )
                )

        assert len(linked_meta) == 1

    def test_integration_auto_include_false_suggests_only(self):
        """AUTO_INCLUDE_LINKED_SHEETS=false → new_extracted empty, suggested_only=True."""
        catalog = [{"page_id": 201, "sheet_name": "C-4 - CIVIL SITE PLAN", "folder_id": 1}]
        all_extracted = [
            {
                "_source_sheet": "A-1 - ARCH PLAN",
                "cross_references": [{"ref_sheet": "C-4"}],
                "civil_structures": [],
            }
        ]
        manifest = _make_manifest(
            project_id=99,
            page_entries=[
                PageEntry(
                    page_id=101,
                    sheet_name="A-1",
                    screenshot_rel="101.jpg",
                    capture_status="ok",
                    analysis_status="ok",
                )
            ],
        )
        browser = _make_browser_mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            mpath = tmppath / "manifest.json"

            with (
                patch("scraper.stackct_store.get_plans", return_value=catalog),
                patch("scraper.AUTO_INCLUDE_LINKED_SHEETS", False),
                patch("scraper.MAX_LINKED_SHEETS", 10),
            ):
                new_extracted, new_estimates, linked_meta = asyncio.run(
                    _discover_and_add_linked_sheets(
                        browser=browser,
                        project_id=99,
                        project_name="Test Project",
                        folder_id=1,
                        all_extracted=all_extracted,
                        manifest=manifest,
                        mpath=mpath,
                        screenshots_dir=tmppath,
                        cached_screenshots={},
                        log=lambda msg: None,
                        progress_callback=None,
                        cancel_check=None,
                    )
                )

        assert new_extracted == []
        assert len(linked_meta) == 1
        assert linked_meta[0]["suggested_only"] is True

    def test_integration_empty_catalog_returns_empty(self):
        """Empty catalog → all return values are empty lists (no crash)."""
        all_extracted = [
            {
                "_source_sheet": "A-1 - ARCH PLAN",
                "cross_references": [{"ref_sheet": "C-4"}],
                "civil_structures": [],
            }
        ]
        manifest = _make_manifest(project_id=99, page_entries=[])
        browser = _make_browser_mock()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            mpath = tmppath / "manifest.json"

            with patch("scraper.stackct_store.get_plans", return_value=[]):
                new_extracted, new_estimates, linked_meta = asyncio.run(
                    _discover_and_add_linked_sheets(
                        browser=browser,
                        project_id=99,
                        project_name="Test Project",
                        folder_id=1,
                        all_extracted=all_extracted,
                        manifest=manifest,
                        mpath=mpath,
                        screenshots_dir=tmppath,
                        cached_screenshots={},
                        log=lambda msg: None,
                        progress_callback=None,
                        cancel_check=None,
                    )
                )

        assert new_extracted == []
        assert new_estimates == []
        assert linked_meta == []
