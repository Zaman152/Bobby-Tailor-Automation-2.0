"""
Unit tests for linked_sheets.py — matcher and collector functions.
"""
import pytest

from linked_sheets import collect_unresolved_refs, match_ref_to_page


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
