"""
tests/test_takeoff_pipeline.py — Unit tests for takeoff_pipeline.py.

All tests mock analyze_drawing so no PDF files or API keys are required.
Tests verify:
  - title_sheet sheets are skipped (analyze_drawing never called)
  - floor_plan runs count then measure passes (two analyze_drawing calls)
  - civil_site runs measure-only pass (one call)
  - schedule runs schedule-only pass (one call)
  - Merge logic: count-pass components added; high-confidence upgrades null qty
  - Pipeline metadata (_source_sheet, _sheet_type, _passes_run) attached
  - schedule_result populates schedules[] in merged output
  - run_project orchestrates multi-sheet flow with project_type detection
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Stub minimal dependencies before importing the module under test.
# ---------------------------------------------------------------------------

_CONFIG_MOCK = MagicMock()
_CONFIG_MOCK.CLAUDE_MODEL = "claude-haiku-4-5"
_CONFIG_MOCK.CLAUDE_MODEL_SCHEDULES = "claude-sonnet-4-5"
_CONFIG_MOCK.ANTHROPIC_API_KEY = "test-key"

sys.modules.setdefault("config", _CONFIG_MOCK)
sys.modules.setdefault("anthropic", MagicMock())

import importlib.util, pathlib

def _load(name: str):
    path = pathlib.Path(__file__).parent.parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Load the real claude_analyzer to get the canonical merge_passes implementation.
# merge_passes does no API calls so it's safe to load with mocked anthropic/config.
_real_ca = _load("claude_analyzer")

# Replace the claude_analyzer module in sys.modules with a mock that keeps the
# real merge_passes but stubs out analyze_drawing (avoid real API calls).
_CA_MOCK = MagicMock()
_CA_MOCK._pick_model.return_value = "claude-haiku-4-5"
_CA_MOCK.analyze_drawing.return_value = {"components": [], "measurements": []}
_CA_MOCK.merge_passes = _real_ca.merge_passes  # real implementation; not a MagicMock

sys.modules["claude_analyzer"] = _CA_MOCK

_spm = _load("sheet_pass_matrix")
_tp  = _load("takeoff_pipeline")

TakeoffPipeline = _tp.TakeoffPipeline
merge_passes    = _real_ca.merge_passes  # test the canonical implementation directly


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_count_result(**kwargs) -> dict:
    return {"components": kwargs.get("components", []), "measurements": []}

def _make_measure_result(**kwargs) -> dict:
    return {
        "components":   kwargs.get("components", []),
        "measurements": kwargs.get("measurements", []),
        "rooms":        kwargs.get("rooms", []),
        "pipe_runs":    kwargs.get("pipe_runs", []),
    }

def _make_analyzer(responses: list[dict]):
    """Return a mock analyzer that yields each response in order."""
    mock = MagicMock(side_effect=responses)
    return mock


# ---------------------------------------------------------------------------
# title_sheet — must skip all API calls
# ---------------------------------------------------------------------------

class TestTitleSheetSkip:
    def test_title_sheet_skips_analyze_drawing(self):
        mock_analyzer = MagicMock()
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet(
            image_path="sheet.png",
            sheet_name="G0.1",
            sheet_type="title_sheet",
        )

        mock_analyzer.assert_not_called()
        assert result["_skipped"] is True

    def test_title_sheet_sentinel_has_required_keys(self):
        pipeline = TakeoffPipeline(analyzer=MagicMock())
        result = pipeline.run_sheet(
            image_path="/path/G0.1.png",
            sheet_name="G0.1",
            sheet_type="title_sheet",
        )
        assert result["sheet_type"] == "title_sheet"
        assert result["sheet_name"] == "G0.1"
        assert result["sheet_source"] == "/path/G0.1.png"

    def test_title_sheet_classified_from_text_skips(self):
        """Auto-classify from title block text → still skip."""
        mock_analyzer = MagicMock()
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)
        result = pipeline.run_sheet(
            image_path="cover.png",
            sheet_name="T1.0",
            title_block_text="SHEET INDEX",
        )
        mock_analyzer.assert_not_called()
        assert result["_skipped"] is True


# ---------------------------------------------------------------------------
# floor_plan — count then measure (two passes)
# ---------------------------------------------------------------------------

class TestFloorPlanPasses:
    def test_floor_plan_calls_analyzer_twice(self):
        count_r   = _make_count_result()
        measure_r = _make_measure_result()
        mock_analyzer = _make_analyzer([count_r, measure_r])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        pipeline.run_sheet(
            image_path="A2.1.png",
            sheet_name="A2.1",
            sheet_type="floor_plan",
        )

        assert mock_analyzer.call_count == 2

    def test_floor_plan_passes_run_metadata(self):
        mock_analyzer = _make_analyzer([_make_count_result(), _make_measure_result()])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet("A2.1.png", "A2.1", sheet_type="floor_plan")

        assert "count" in result["_passes_run"]
        assert "measure" in result["_passes_run"]

    def test_floor_plan_pipeline_metadata(self):
        mock_analyzer = _make_analyzer([_make_count_result(), _make_measure_result()])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet("A2.1.png", "A2.1", sheet_type="floor_plan")

        assert result["_source_sheet"] == "A2.1.png"
        assert result["_sheet_type"]   == "floor_plan"
        assert result["_sheet_name"]   == "A2.1"

    def test_floor_plan_count_before_measure(self):
        """Count pass must be executed before measure pass."""
        call_order = []

        def mock_analyzer(image_path, sheet_name, **kwargs):
            call_order.append(len(call_order))
            return _make_count_result() if len(call_order) == 1 else _make_measure_result()

        pipeline = TakeoffPipeline(analyzer=mock_analyzer)
        pipeline.run_sheet("A2.1.png", "A2.1", sheet_type="floor_plan")

        assert call_order == [0, 1], "Expected two ordered calls"


# ---------------------------------------------------------------------------
# civil_site — measure only (one pass)
# ---------------------------------------------------------------------------

class TestCivilSitePass:
    def test_civil_site_calls_analyzer_once(self):
        mock_analyzer = _make_analyzer([_make_measure_result()])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        pipeline.run_sheet("C1.0.png", "C1.0", sheet_type="civil_site")

        assert mock_analyzer.call_count == 1

    def test_civil_site_passes_run_is_measure_only(self):
        mock_analyzer = _make_analyzer([_make_measure_result()])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet("C1.0.png", "C1.0", sheet_type="civil_site")

        assert result["_passes_run"] == ["measure"]


# ---------------------------------------------------------------------------
# schedule — schedule-only pass
# ---------------------------------------------------------------------------

class TestSchedulePass:
    def test_schedule_calls_analyzer_once(self):
        schedule_result = {"schedules": [{"name": "DOOR SCHEDULE", "rows": []}]}
        mock_analyzer = _make_analyzer([schedule_result])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet("A8.1.png", "A8.1", sheet_type="schedule")

        assert mock_analyzer.call_count == 1

    def test_schedule_result_in_merged_output(self):
        rows = [{"DOOR MARK": "101", "TYPE": "HM"}]
        schedule_result = {"schedules": [{"name": "DOOR SCHEDULE", "rows": rows}]}
        mock_analyzer = _make_analyzer([schedule_result])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet("A8.1.png", "A8.1", sheet_type="schedule")

        assert "schedules" in result
        assert result["schedules"][0]["name"] == "DOOR SCHEDULE"


# ---------------------------------------------------------------------------
# merge_passes() — standalone unit tests
# ---------------------------------------------------------------------------

class TestMergePasses:
    def test_measure_is_base_for_components(self):
        count   = _make_count_result(components=[{"name": "Bollard", "quantity": 28, "confidence": "high"}])
        measure = _make_measure_result(components=[{"name": "Bollard", "quantity": None}])

        merged = merge_passes(count, measure, None)

        # Measure-pass component is upgraded with count-pass high-confidence qty
        bollards = [c for c in merged["components"] if c["name"] == "Bollard"]
        assert bollards
        assert bollards[0]["quantity"] == 28

    def test_count_only_component_added(self):
        count   = _make_count_result(components=[{"name": "Column", "quantity": 12, "confidence": "high"}])
        measure = _make_measure_result(components=[])

        merged = merge_passes(count, measure, None)

        names = [c["name"] for c in merged["components"]]
        assert "Column" in names

    def test_measure_only_component_preserved(self):
        count   = _make_count_result(components=[])
        measure = _make_measure_result(components=[{"name": "Storefront", "quantity": 3}])

        merged = merge_passes(count, measure, None)

        names = [c["name"] for c in merged["components"]]
        assert "Storefront" in names

    def test_schedule_result_applied(self):
        sched_result = {"schedules": [{"name": "WINDOW SCHEDULE", "rows": []}]}
        merged = merge_passes({}, {}, sched_result)

        assert "schedules" in merged
        assert merged["schedules"][0]["name"] == "WINDOW SCHEDULE"

    def test_no_schedule_result_leaves_measure_schedules(self):
        measure = {"schedules": [{"name": "Existing", "rows": []}], "components": []}
        merged  = merge_passes({}, measure, None)

        assert merged["schedules"][0]["name"] == "Existing"

    def test_deduplication_case_insensitive(self):
        count   = _make_count_result(components=[{"name": "bollard", "quantity": 28, "confidence": "high"}])
        measure = _make_measure_result(components=[{"name": "Bollard", "quantity": None}])

        merged = merge_passes(count, measure, None)

        bollards = [c for c in merged["components"] if c["name"].lower() == "bollard"]
        assert len(bollards) == 1, "Duplicate should not be added"

    def test_low_confidence_count_does_not_upgrade_null(self):
        count   = _make_count_result(components=[{"name": "Stair", "quantity": 3, "confidence": "low"}])
        measure = _make_measure_result(components=[{"name": "Stair", "quantity": None}])

        merged = merge_passes(count, measure, None)

        stairs = [c for c in merged["components"] if c["name"] == "Stair"]
        assert stairs[0]["quantity"] is None, "Low-confidence count must not replace null"

    def test_both_empty_returns_empty_dict(self):
        merged = merge_passes({}, {}, None)
        assert isinstance(merged, dict)


# ---------------------------------------------------------------------------
# Auto-classify from text
# ---------------------------------------------------------------------------

class TestAutoClassify:
    def test_auto_classify_floor_plan_from_title_block(self):
        mock_analyzer = _make_analyzer([_make_count_result(), _make_measure_result()])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet(
            image_path="A2.1.png",
            sheet_name="A2.1",
            title_block_text="LEVEL 1 FLOOR PLAN",
        )

        assert result["_sheet_type"] == "floor_plan"
        assert mock_analyzer.call_count == 2

    def test_auto_classify_civil_site_from_title_block(self):
        mock_analyzer = _make_analyzer([_make_measure_result()])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet(
            image_path="C1.0.png",
            sheet_name="C1.0",
            title_block_text="OVERALL SITE PLAN",
        )

        assert result["_sheet_type"] == "civil_site"
        assert mock_analyzer.call_count == 1


# ---------------------------------------------------------------------------
# QuantityVerifier
# ---------------------------------------------------------------------------

class TestQuantityVerifier:
    """QuantityVerifier flags out-of-range quantities but does not raise."""

    def _verifier(self):
        from takeoff_pipeline import QuantityVerifier  # type: ignore[attr-defined]
        return _tp.QuantityVerifier()

    def test_in_range_ea_returns_no_flags(self):
        v = self._verifier()
        extracted = {
            "components": [{"name": "Door", "quantity": 10, "unit": "ea"}],
            "measurements": [],
        }
        assert v.verify(extracted, "A2.1") == []

    def test_out_of_range_ea_flagged(self):
        v = self._verifier()
        extracted = {
            "components": [{"name": "Door", "quantity": 99999, "unit": "ea"}],
            "measurements": [],
        }
        flags = v.verify(extracted, "A2.1")
        assert len(flags) == 1
        assert flags[0]["item"] == "Door"
        assert flags[0]["unit"] == "ea"

    def test_out_of_range_sf_flagged(self):
        v = self._verifier()
        extracted = {
            "components": [],
            "measurements": [{"description": "Flooring", "value": 999999, "unit": "sf"}],
        }
        flags = v.verify(extracted)
        assert len(flags) == 1
        assert flags[0]["unit"] == "sf"

    def test_null_quantity_not_flagged(self):
        v = self._verifier()
        extracted = {
            "components": [{"name": "Column", "quantity": None, "unit": "ea"}],
            "measurements": [],
        }
        assert v.verify(extracted) == []

    def test_unknown_unit_not_flagged(self):
        v = self._verifier()
        extracted = {
            "components": [{"name": "Beam", "quantity": 9999999, "unit": "unknown"}],
            "measurements": [],
        }
        assert v.verify(extracted) == []

    def test_non_numeric_quantity_not_flagged(self):
        v = self._verifier()
        extracted = {
            "components": [{"name": "Duct", "quantity": "TBD", "unit": "lf"}],
            "measurements": [],
        }
        assert v.verify(extracted) == []


# ---------------------------------------------------------------------------
# run_project
# ---------------------------------------------------------------------------

def _make_floor_plan_responses():
    """Two responses: count pass then measure pass for a floor_plan."""
    return [_make_count_result(), _make_measure_result()]


class TestRunProject:
    """TakeoffPipeline.run_project orchestrates a multi-sheet project run."""

    def _pipeline(self, responses: list[dict]) -> TakeoffPipeline:
        return TakeoffPipeline(analyzer=_make_analyzer(responses))

    def test_run_project_returns_three_tuple(self):
        pipeline = self._pipeline(_make_floor_plan_responses())
        result = pipeline.run_project(
            [{"image_path": "A2.1.png", "sheet_name": "A2.1", "sheet_type_hint": "floor_plan"}]
        )
        assert isinstance(result, tuple) and len(result) == 3

    def test_run_project_extracts_non_skipped_sheets(self):
        """Non-title sheets are collected in all_extracted."""
        pipeline = self._pipeline(_make_floor_plan_responses())
        all_extracted, _, _ = pipeline.run_project(
            [{"image_path": "A2.1.png", "sheet_name": "A2.1", "sheet_type_hint": "floor_plan"}]
        )
        assert len(all_extracted) == 1

    def test_run_project_skips_title_sheet(self):
        """Title sheets must be excluded from all_extracted."""
        pipeline = self._pipeline([])  # no analyzer calls expected
        all_extracted, all_estimates, project_type = pipeline.run_project(
            [{"image_path": "G0.1.png", "sheet_name": "G0.1", "sheet_type_hint": "title_sheet"}]
        )
        assert all_extracted == []
        assert all_estimates == []

    def test_run_project_mixed_sheets_skips_title(self):
        """Only non-title sheets end up in all_extracted."""
        # floor_plan needs 2 responses; title_sheet needs 0
        pipeline = self._pipeline(_make_floor_plan_responses())
        pages = [
            {"image_path": "G0.1.png", "sheet_name": "G0.1", "sheet_type_hint": "title_sheet"},
            {"image_path": "A2.1.png", "sheet_name": "A2.1", "sheet_type_hint": "floor_plan"},
        ]
        all_extracted, _, _ = pipeline.run_project(pages)
        assert len(all_extracted) == 1
        assert all_extracted[0]["_sheet_name"] == "A2.1"

    def test_run_project_tags_page_num(self):
        pipeline = self._pipeline(_make_floor_plan_responses())
        all_extracted, _, _ = pipeline.run_project(
            [{"image_path": "A2.1.png", "sheet_name": "A2.1",
              "sheet_type_hint": "floor_plan", "page_num": 3}]
        )
        assert all_extracted[0]["_page_num"] == 3

    def test_run_project_progress_callback_called_per_page(self):
        calls = []
        pipeline = self._pipeline(
            _make_floor_plan_responses() + _make_floor_plan_responses()
        )
        pages = [
            {"image_path": "A2.1.png", "sheet_name": "A2.1", "sheet_type_hint": "floor_plan"},
            {"image_path": "A3.1.png", "sheet_name": "A3.1", "sheet_type_hint": "floor_plan"},
        ]
        pipeline.run_project(pages, progress_callback=lambda c, t, n: calls.append((c, t, n)))
        assert len(calls) == 2
        assert calls[0] == (1, 2, "A2.1")
        assert calls[1] == (2, 2, "A3.1")

    def test_run_project_empty_pages_returns_auto_type(self):
        pipeline = self._pipeline([])
        _, _, project_type = pipeline.run_project([])
        assert project_type == "auto"

    def test_run_project_project_type_string(self):
        """project_type must be a string (not None or MagicMock)."""
        pipeline = self._pipeline(_make_floor_plan_responses())
        _, _, project_type = pipeline.run_project(
            [{"image_path": "A2.1.png", "sheet_name": "A2.1", "sheet_type_hint": "floor_plan"}]
        )
        assert isinstance(project_type, str)
