"""
tests/test_sheet_pass_matrix.py — Unit tests for sheet_pass_matrix.py.

Tests cover:
  - PASS_MATRIX structure and coverage
  - plan_passes() routing (including title_sheet skip and unknown fallback)
  - classify_sheet_type_from_text() keyword heuristics
  - pick_model_for_pass() model selection priority
  - No PDF files or API keys required.
"""

import sys
import os
import importlib
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Module-level fixture: import with mocked config and claude_analyzer to
# ensure tests run without ANTHROPIC_API_KEY or installed dependencies.
# ---------------------------------------------------------------------------

# Provide minimal config stubs before importing the module under test
_CONFIG_MOCK = MagicMock()
_CONFIG_MOCK.CLAUDE_MODEL = "claude-haiku-4-5"
_CONFIG_MOCK.CLAUDE_MODEL_SCHEDULES = "claude-sonnet-4-5"

_CA_MOCK = MagicMock()
_CA_MOCK._pick_model.return_value = "claude-haiku-4-5"

# Patch at sys.modules level so the import inside sheet_pass_matrix resolves
sys.modules.setdefault("config", _CONFIG_MOCK)
sys.modules.setdefault("claude_analyzer", _CA_MOCK)

# Now import the module under test (after stubs are in place)
import importlib.util, pathlib

_MODULE_PATH = pathlib.Path(__file__).parent.parent / "sheet_pass_matrix.py"
_spec = importlib.util.spec_from_file_location("sheet_pass_matrix", _MODULE_PATH)
_spm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_spm)

PASS_MATRIX              = _spm.PASS_MATRIX
MODEL_ROUTING            = _spm.MODEL_ROUTING
classify_sheet_type_from_text = _spm.classify_sheet_type_from_text
plan_passes              = _spm.plan_passes
pick_model_for_pass      = _spm.pick_model_for_pass


# ---------------------------------------------------------------------------
# PASS_MATRIX structure
# ---------------------------------------------------------------------------

class TestPassMatrix:
    EXPECTED_SHEET_TYPES = {
        "floor_plan", "elevation", "civil_site", "schedule",
        "detail", "title_sheet", "roof_plan", "mep_plan",
    }

    def test_covers_all_eight_sheet_types(self):
        assert set(PASS_MATRIX.keys()) == self.EXPECTED_SHEET_TYPES

    def test_title_sheet_is_empty(self):
        assert PASS_MATRIX["title_sheet"] == [], (
            "title_sheet must have empty pass list (zero API cost)"
        )

    def test_civil_site_is_measure_only(self):
        assert PASS_MATRIX["civil_site"] == ["measure"]

    def test_schedule_is_schedule_only(self):
        assert PASS_MATRIX["schedule"] == ["schedule"]

    def test_floor_plan_has_count_measure_and_schedule(self):
        passes = PASS_MATRIX["floor_plan"]
        assert passes == ["count", "measure", "schedule"]

    def test_floor_plan_schedule_pass_without_title_block_keywords(self):
        passes = plan_passes("floor_plan", title_block_text="OVERALL FLOOR PLAN")
        assert passes == ["count", "measure", "schedule"]

    def test_elevation_has_count_and_measure(self):
        passes = PASS_MATRIX["elevation"]
        assert "count" in passes
        assert "measure" in passes

    def test_all_non_title_sheet_types_are_non_empty(self):
        for sheet_type, passes in PASS_MATRIX.items():
            if sheet_type == "title_sheet":
                continue
            assert passes, f"{sheet_type} must have at least one pass"


# ---------------------------------------------------------------------------
# plan_passes()
# ---------------------------------------------------------------------------

class TestPlanPasses:
    def test_title_sheet_returns_empty(self):
        result = plan_passes("title_sheet")
        assert result == []

    def test_elevation_returns_count_and_measure(self):
        result = plan_passes("elevation")
        assert "count" in result
        assert "measure" in result

    def test_civil_site_returns_measure_only(self):
        assert plan_passes("civil_site") == ["measure"]

    def test_schedule_returns_schedule_only(self):
        assert plan_passes("schedule") == ["schedule"]

    def test_roof_plan_returns_count_and_measure(self):
        result = plan_passes("roof_plan")
        assert "count" in result
        assert "measure" in result

    def test_mep_plan_returns_count_and_measure(self):
        result = plan_passes("mep_plan")
        assert "count" in result
        assert "measure" in result

    def test_unknown_sheet_type_falls_back_to_measure(self):
        result = plan_passes("unknown_custom_type")
        assert result == ["measure"], (
            "Unknown types must never be silently dropped"
        )

    def test_returns_copy_not_reference(self):
        """Mutating the returned list must not affect PASS_MATRIX."""
        result = plan_passes("floor_plan")
        result.clear()
        assert PASS_MATRIX["floor_plan"] != []


# ---------------------------------------------------------------------------
# classify_sheet_type_from_text()
# ---------------------------------------------------------------------------

class TestClassifySheetType:
    def test_overall_floor_plan(self):
        assert classify_sheet_type_from_text("OVERALL FLOOR PLAN") == "floor_plan"

    def test_level_1_floor_plan(self):
        assert classify_sheet_type_from_text("LEVEL 1 FLOOR PLAN") == "floor_plan"

    def test_roof_plan(self):
        assert classify_sheet_type_from_text("ROOF PLAN") == "roof_plan"

    def test_elevation(self):
        assert classify_sheet_type_from_text("NORTH ELEVATION") == "elevation"

    def test_elevations_plural(self):
        assert classify_sheet_type_from_text("EXTERIOR ELEVATIONS") == "elevation"

    def test_civil_site_plan(self):
        assert classify_sheet_type_from_text("OVERALL SITE PLAN") == "civil_site"

    def test_grading_plan(self):
        assert classify_sheet_type_from_text("GRADING AND DRAINAGE PLAN") == "civil_site"

    def test_schedule_keyword(self):
        assert classify_sheet_type_from_text("DOOR SCHEDULE") == "schedule"

    def test_panel_schedule(self):
        assert classify_sheet_type_from_text("PANEL SCHEDULE") == "schedule"

    def test_detail_keyword(self):
        assert classify_sheet_type_from_text("WALL DETAILS") == "detail"

    def test_section_keyword(self):
        assert classify_sheet_type_from_text("BUILDING SECTIONS") == "detail"

    def test_title_sheet_index(self):
        assert classify_sheet_type_from_text("SHEET INDEX") == "title_sheet"

    def test_title_sheet_cover(self):
        assert classify_sheet_type_from_text("COVER SHEET") == "title_sheet"

    def test_mep_prefix_with_plan(self):
        # MEP sheet: first token is M/P/E + digit, "PLAN" in title
        assert classify_sheet_type_from_text("M1 MECHANICAL PLAN") == "mep_plan"

    def test_mep_electrical_prefix(self):
        assert classify_sheet_type_from_text("E2 ELECTRICAL PLAN") == "mep_plan"

    def test_empty_title_falls_back_to_full_page(self):
        result = classify_sheet_type_from_text("", "DOOR SCHEDULE")
        assert result == "schedule"

    def test_empty_both_defaults_to_floor_plan(self):
        assert classify_sheet_type_from_text("") == "floor_plan"

    def test_roof_plan_wins_over_plain_plan(self):
        """ROOF PLAN must not be classified as floor_plan."""
        assert classify_sheet_type_from_text("ROOF PLAN AND EQUIPMENT LAYOUT") == "roof_plan"

    def test_title_sheet_wins_over_schedule(self):
        """'SHEET INDEX' (title) must not be mislabeled as 'schedule'."""
        result = classify_sheet_type_from_text("SHEET INDEX AND SCHEDULE")
        assert result == "title_sheet"

    def test_case_insensitive(self):
        assert classify_sheet_type_from_text("floor plan") == "floor_plan"
        assert classify_sheet_type_from_text("Roof Plan") == "roof_plan"


# ---------------------------------------------------------------------------
# pick_model_for_pass()
# ---------------------------------------------------------------------------

class TestPickModelForPass:
    # Read the model slugs straight from the module under test so the routing
    # invariants ("schedules model" vs "default model") hold regardless of
    # whether the mock or the real `config` won the import-order race. conftest
    # guarantees the two values are distinct (Sonnet vs Haiku).
    SONNET = _spm.CLAUDE_MODEL_SCHEDULES   # the "needs a stronger model" slug
    HAIKU  = _spm.CLAUDE_MODEL             # the default slug

    def test_elevation_measure_returns_sonnet(self):
        model = pick_model_for_pass("elevation", "measure")
        assert model == self.SONNET

    def test_detail_count_returns_sonnet(self):
        model = pick_model_for_pass("detail", "count")
        assert model == self.SONNET

    def test_detail_measure_returns_sonnet(self):
        model = pick_model_for_pass("detail", "measure")
        assert model == self.SONNET

    def test_schedule_schedule_returns_sonnet(self):
        model = pick_model_for_pass("schedule", "schedule")
        assert model == self.SONNET

    def test_roof_plan_measure_returns_sonnet(self):
        model = pick_model_for_pass("roof_plan", "measure")
        assert model == self.SONNET

    def test_mep_plan_measure_returns_sonnet(self):
        model = pick_model_for_pass("mep_plan", "measure")
        assert model == self.SONNET

    def test_floor_plan_count_uses_sonnet(self):
        """floor_plan count routes to Sonnet for grid/symbol accuracy."""
        model = pick_model_for_pass("floor_plan", "count")
        assert model == self.SONNET

    def test_floor_plan_measure_uses_sonnet(self):
        model = pick_model_for_pass("floor_plan", "measure")
        assert model == self.SONNET

    def test_elevation_count_returns_none(self):
        """elevation count is not in MODEL_ROUTING — should be None (Haiku)."""
        model = pick_model_for_pass("elevation", "count")
        assert model is None

    def test_sheet_name_fallback_when_no_routing(self):
        """When MODEL_ROUTING has no entry, _pick_model fallback is used."""
        # Make _ca_pick_model return Sonnet for this specific sheet name
        _CA_MOCK._pick_model.return_value = self.SONNET
        try:
            model = pick_model_for_pass("floor_plan", "count", sheet_name="E3.1")
            assert model == self.SONNET
        finally:
            _CA_MOCK._pick_model.return_value = self.HAIKU

    def test_floor_plan_count_routed_without_sheet_name(self):
        """MODEL_ROUTING applies even when sheet_name is empty."""
        model = pick_model_for_pass("floor_plan", "count", sheet_name="")
        assert model == self.SONNET
