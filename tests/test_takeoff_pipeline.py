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
# Phase 22 (Step 1c): explicit tmp-path strings on every dir attribute so a
# SOLO run of this file (bare stub wins the import race) never yields
# os.fspath(mock.SCREENSHOTS_DIR) == literal "MagicMock/..." that
# pdf_analyzer then mkdir -p's at the repo root.
_CONFIG_MOCK.OUTPUT_DIR = "/tmp/bt-tp-out"
_CONFIG_MOCK.SCREENSHOTS_DIR = "/tmp/bt-tp-out/screenshots"

sys.modules.setdefault("bobbytailor.config", _CONFIG_MOCK)
sys.modules.setdefault("anthropic", MagicMock())

import importlib.util, pathlib

# Phase 21 (V3-STRUCT-01): modules live under src/bobbytailor/. Spec-load the
# real sources under isolated names so mocks bind without touching the
# canonical package modules.
_SRC_ROOT = pathlib.Path(__file__).parent.parent / "src" / "bobbytailor"
_SRC_FILES = {
    "claude_analyzer": _SRC_ROOT / "vision" / "claude_analyzer.py",
    "sheet_pass_matrix": _SRC_ROOT / "pipeline" / "sheet_pass_matrix.py",
    "takeoff_pipeline": _SRC_ROOT / "pipeline" / "takeoff_pipeline.py",
}

def _load(name: str):
    path = _SRC_FILES[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Load the real claude_analyzer to get the canonical merge_passes implementation.
# merge_passes does no API calls so it's safe to load with mocked anthropic/config.
_real_ca = _load("claude_analyzer")

# Bind a claude_analyzer mock into the spec-loaded modules: real merge_passes,
# stubbed analyze_drawing (avoid real API calls). The package key is aliased
# ONLY while the spec loads execute, then restored — a permanent substitution
# would leak the mock into every later-collected test module (the 21-08/21-16
# test-order pollution class).
_CA_MOCK = MagicMock()
_CA_MOCK._pick_model.return_value = "claude-haiku-4-5"
_CA_MOCK.analyze_drawing.return_value = {"components": [], "measurements": []}
_CA_MOCK.merge_passes = _real_ca.merge_passes  # real implementation; not a MagicMock
_CA_MOCK._merge_schedule_lists = _real_ca._merge_schedule_lists
_CA_MOCK.apply_accuracy_rules = _real_ca.apply_accuracy_rules

_PKG_CA = "bobbytailor.vision.claude_analyzer"
_prev_real_ca = sys.modules.get(_PKG_CA)
sys.modules[_PKG_CA] = _CA_MOCK
try:
    _spm = _load("sheet_pass_matrix")
    _tp  = _load("takeoff_pipeline")
finally:
    if _prev_real_ca is not None:
        sys.modules[_PKG_CA] = _prev_real_ca
    else:
        sys.modules.pop(_PKG_CA, None)

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
# floor_plan — count, measure, schedule (three passes)
# ---------------------------------------------------------------------------

class TestFloorPlanPasses:
    def test_floor_plan_calls_analyzer_three_times(self):
        mock_analyzer = _make_analyzer(_make_floor_plan_responses())
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        pipeline.run_sheet(
            image_path="A2.1.png",
            sheet_name="A2.1",
            sheet_type="floor_plan",
        )

        assert mock_analyzer.call_count == 3

    def test_floor_plan_passes_run_metadata(self):
        mock_analyzer = _make_analyzer(_make_floor_plan_responses())
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet("A2.1.png", "A2.1", sheet_type="floor_plan")

        assert "count" in result["_passes_run"]
        assert "measure" in result["_passes_run"]
        assert "schedule" in result["_passes_run"]

    def test_floor_plan_pipeline_metadata(self):
        mock_analyzer = _make_analyzer(_make_floor_plan_responses())
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet("A2.1.png", "A2.1", sheet_type="floor_plan")

        assert result["_source_sheet"] == "A2.1.png"
        assert result["_sheet_type"]   == "floor_plan"
        assert result["_sheet_name"]   == "A2.1"

    def test_floor_plan_count_before_measure(self):
        """Count pass must be executed before measure pass."""
        call_order = []

        def mock_analyzer(image_path, sheet_name, **kwargs):
            call_order.append(kwargs.get("pass_type"))
            pt = kwargs.get("pass_type")
            if pt == "count":
                return _make_count_result()
            if pt == "schedule":
                return {"schedules": []}
            return _make_measure_result()

        pipeline = TakeoffPipeline(analyzer=mock_analyzer)
        pipeline.run_sheet("A2.1.png", "A2.1", sheet_type="floor_plan")

        assert call_order == ["count", "measure", "schedule"]


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
        sched_result = {
            "schedules": [{
                "name": "WINDOW SCHEDULE",
                "table_purpose": "takeoff_schedule",
                "rows": [{"MARK": "W-1", "QTY": "4"}],
            }],
        }
        merged = merge_passes({}, {}, sched_result)

        assert "schedules" in merged
        assert merged["schedules"][0]["name"] == "WINDOW SCHEDULE"

    def test_no_schedule_result_leaves_measure_schedules(self):
        measure = {
            "schedules": [{
                "name": "Existing",
                "table_purpose": "takeoff_schedule",
                "rows": [{"ITEM": "Door", "QTY": "2"}],
            }],
            "components": [],
        }
        merged = merge_passes({}, measure, None)

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
        mock_analyzer = _make_analyzer(_make_floor_plan_responses())
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet(
            image_path="A2.1.png",
            sheet_name="A2.1",
            title_block_text="LEVEL 1 FLOOR PLAN",
        )

        assert result["_sheet_type"] == "floor_plan"
        assert mock_analyzer.call_count == 3

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
        from bobbytailor.pipeline.takeoff_pipeline import QuantityVerifier  # type: ignore[attr-defined]
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
    """Three responses: count, measure, schedule passes for a floor_plan."""
    return [_make_count_result(), _make_measure_result(), {"schedules": []}]


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

    def _legend(self):
        return [{
            "name": "Quantity Takeoff (companion document)",
            "table_purpose": "takeoff_legend",
            "use_for_takeoff": True,
            "rows": [{"ITEM": "Fiber Cement Panel", "QTY": "123231.03", "UNIT": "SF"}],
        }]

    def test_companion_legend_injected_into_floor_plan(self):
        pipeline = self._pipeline(_make_floor_plan_responses())
        all_extracted, _, _ = pipeline.run_project(
            [{"image_path": "A2.1.png", "sheet_name": "A2.1", "sheet_type_hint": "floor_plan"}],
            project_legend_schedules=self._legend(),
        )
        assert any(e.get("_companion_legend_injected") for e in all_extracted)

    def test_companion_legend_fallback_when_no_floor_plan(self):
        """A project with no floor_plan sheet must still ingest the companion
        take-off (fallback into the first non-skipped sheet)."""
        pipeline = self._pipeline(_make_floor_plan_responses())
        all_extracted, all_estimates, _ = pipeline.run_project(
            [{"image_path": "A4.1.png", "sheet_name": "A4.1", "sheet_type_hint": "elevation"}],
            project_legend_schedules=self._legend(),
        )
        assert any(e.get("_companion_legend_injected") for e in all_extracted)
        # The authoritative legend value flows through to the estimates verbatim.
        fcp = [e for e in all_estimates
               if "Fiber Cement Panel" in e.get("description", "")]
        assert fcp and abs(fcp[0]["quantity"] - 123231.03) < 0.01
        assert fcp[0]["unit"] == "SF"


# ---------------------------------------------------------------------------
# The skip veto — measurable geometry outranks a classifier keyword
# (23-01 / INV-08 §3.4). Synthetic pages only: no fixture PDF, no API key.
# ---------------------------------------------------------------------------

import os
import tempfile

import fitz

from bobbytailor.pipeline.coverage import (
    MEASURED_PARTIAL,
    NOT_APPLICABLE,
    SKIPPED_CLASSIFIER,
    CoverageLedger,
    SheetCoverage,
)

page_measurable_signal = _tp.page_measurable_signal

# 1/4" = 1'-0" — Moxy's guestroom prototype scale, the sheets this veto recovers.
_SYNTHETIC_SCALE_LABEL = 'SCALE: 1/4" = 1\'-0"'


def _synthetic_sheet(with_title=True, with_scale=True, vector=True) -> str:
    """A one-page PDF shaped like a guestroom prototype sheet. Returns its path.

    *vector* controls whether the page clears is_vector_sheet's path-count
    threshold — a raster page has no deterministic geometry to recover, and the
    veto must refuse to spend vision money on it.
    """
    doc = fitz.open()
    page = doc.new_page(width=800, height=800)
    page.draw_rect(fitz.Rect(150, 150, 500, 400), width=2)   # the "room"
    if vector:
        for i in range(260):                                  # vector density
            y = 152 + (i % 240)
            page.draw_line(fitz.Point(152, y), fitz.Point(160, y), width=0.3)
    if with_title:
        page.insert_text(fitz.Point(200, 470), "KING A - RCP PLAN", fontsize=12)
    if with_scale:
        page.insert_text(fitz.Point(200, 492), _SYNTHETIC_SCALE_LABEL, fontsize=9)
    path = tempfile.mktemp(suffix=".pdf")
    doc.save(path)
    doc.close()
    return path


def _exploding_analyzer(*args, **kwargs):
    """Any vision pass reaching this is unbudgeted API spend — fail loudly."""
    raise AssertionError(
        "a vision pass was invoked on a vetoed sheet — this costs real money"
    )


class TestMeasurableSignal:
    """plan_titles counts titles that ANCHOR A SCALE, not title-shaped strings.

    Moxy page 1 is the lighting cover sheet: its index lists 11 strings matching
    the plan-title pattern and it carries zero printed scales. Counting those as
    measurable signal would report a silent loss of 11 drawings on an index
    page — a false alarm on every drawing set that has an index.
    """

    def test_title_with_a_scale_beneath_it_is_measurable(self):
        path = _synthetic_sheet()
        try:
            doc = fitz.open(path)
            signal = page_measurable_signal(doc[0])
            doc.close()
        finally:
            os.unlink(path)
        assert signal["plan_titles"] == 1
        assert signal["printed_scales"] == 1

    def test_title_without_a_scale_is_not_measurable(self):
        """Measuring it at a borrowed scale would be a squared error."""
        path = _synthetic_sheet(with_scale=False)
        try:
            doc = fitz.open(path)
            signal = page_measurable_signal(doc[0])
            doc.close()
        finally:
            os.unlink(path)
        assert signal["plan_titles"] == 0

    def test_blank_page_has_no_signal(self):
        path = _synthetic_sheet(with_title=False, with_scale=False)
        try:
            doc = fitz.open(path)
            signal = page_measurable_signal(doc[0])
            doc.close()
        finally:
            os.unlink(path)
        assert sum(signal.values()) == 0

    def test_signal_keys_are_stable(self):
        path = _synthetic_sheet()
        try:
            doc = fitz.open(path)
            signal = page_measurable_signal(doc[0])
            doc.close()
        finally:
            os.unlink(path)
        assert set(signal) == {"plan_titles", "printed_scales", "viewports",
                               "schedules"}


class TestSkipVeto:
    def test_scaled_plan_title_overrules_the_classifier(self):
        """THE Gap 8 fix: 16 Moxy guestroom sheets stop being discarded."""
        path = _synthetic_sheet()
        coverage = SheetCoverage(page_index=23)
        try:
            pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
            result = pipeline.run_sheet(
                image_path="ID-407.png",
                sheet_name="ID-407",
                sheet_type="title_sheet",
                pdf_path=path,
                page_index=0,
                coverage=coverage,
            )
        finally:
            os.unlink(path)

        assert not result.get("_skipped"), "a page holding a scaled plan must be measured"
        assert coverage.classifier_overruled is True
        assert coverage.disposition == MEASURED_PARTIAL
        assert coverage.disposition == "measured_partial"
        assert coverage.sheet_type == "floor_plan"
        assert "overruled" in coverage.reason

    def test_the_veto_spends_nothing(self):
        """INV-08 risk 1: recovering sheets must not become an API bill.

        The analyzer raises on any call, so the test passing IS the assertion
        that no vision pass ran.
        """
        path = _synthetic_sheet()
        try:
            pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
            result = pipeline.run_sheet(
                image_path="ID-407.png", sheet_name="ID-407",
                sheet_type="title_sheet", pdf_path=path, page_index=0,
                coverage=SheetCoverage(page_index=23),
            )
        finally:
            os.unlink(path)
        assert result is not None

    def test_a_raster_page_is_never_recovered_onto_the_vision_ensemble(self):
        """A raster page has no deterministic geometry to recover.

        Routing it to _run_sheet_raster would buy an ensemble vision estimate
        for a sheet a keyword had already called worthless — the honest outcome
        is the recorded skip.
        """
        path = _synthetic_sheet(vector=False)
        coverage = SheetCoverage(page_index=23)
        try:
            pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
            result = pipeline.run_sheet(
                image_path="ID-407.png", sheet_name="ID-407",
                sheet_type="title_sheet", pdf_path=path, page_index=0,
                coverage=coverage,
            )
        finally:
            os.unlink(path)
        assert result["_skipped"] is True
        assert result["_classifier_overruled"] is True
        assert coverage.disposition == SKIPPED_CLASSIFIER
        assert "deterministic engine produced nothing" in coverage.reason

    def test_overruled_branch_routes_deterministically(self):
        """The recovered sheet goes through _route_deterministic, not the passes."""
        path = _synthetic_sheet()
        seen = {}
        try:
            pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
            original = pipeline._route_deterministic

            def _spy(**kwargs):
                seen.update(kwargs)
                return original(**kwargs)

            pipeline._route_deterministic = _spy
            pipeline.run_sheet(
                image_path="ID-407.png", sheet_name="ID-407",
                sheet_type="title_sheet", pdf_path=path, page_index=0,
                coverage=SheetCoverage(page_index=23),
            )
        finally:
            os.unlink(path)
        assert seen, "_route_deterministic was never called"
        assert seen["resolved_type"] == "floor_plan"
        assert seen["deterministic_only"] is True, "the raster/vision branch must be refused"


class TestSkipIsRecorded:
    def test_a_genuine_cover_sheet_is_not_applicable(self):
        """Bob's page 0 / Moxy page 0: titles=0 scales=0, a real cover sheet.

        All-zero signal means there was nothing to lose, so the honest label is
        NOT_APPLICABLE — not the alarm-raising SKIPPED_CLASSIFIER.
        """
        path = _synthetic_sheet(with_title=False, with_scale=False)
        coverage = SheetCoverage(page_index=0)
        try:
            pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
            result = pipeline.run_sheet(
                image_path="CS-00.png", sheet_name="CS-00",
                title_block_text="CS-00 COVER SHEET 25-13.01",
                pdf_path=path, page_index=0, coverage=coverage,
            )
        finally:
            os.unlink(path)

        assert result["_skipped"] is True
        assert coverage.disposition == NOT_APPLICABLE
        assert coverage.classifier_keyword == "COVER SHEET"
        assert coverage.is_silent_loss is False

    def test_a_skipped_page_with_signal_is_skipped_classifier(self, monkeypatch):
        """Chelsea page 0's shape: scale callouts, but nothing measurable bound
        to them. Skipped — and flagged, because the page was not empty."""
        path = _synthetic_sheet(with_title=False, with_scale=False)
        coverage = SheetCoverage(page_index=0)
        signal = {"plan_titles": 0, "printed_scales": 2, "viewports": 0,
                  "schedules": 0}
        try:
            pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
            monkeypatch.setattr(
                pipeline, "_skip_veto_signal",
                lambda *a, **k: (signal, False),
            )
            result = pipeline.run_sheet(
                image_path="C0.png", sheet_name="C0",
                title_block_text="C0 COVER SHEET",
                pdf_path=path, page_index=0, coverage=coverage,
            )
        finally:
            os.unlink(path)

        assert result["_skipped"] is True
        assert coverage.disposition == SKIPPED_CLASSIFIER
        assert coverage.disposition == "skipped_classifier"
        assert coverage.classifier_keyword != ""
        assert coverage.is_silent_loss is True

    def test_the_sentinel_carries_the_reason(self):
        """A skipped page states which keyword skipped it and what it matched."""
        path = _synthetic_sheet(with_title=False, with_scale=False)
        try:
            pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
            result = pipeline.run_sheet(
                image_path="x.png", sheet_name="ID-411",
                title_block_text=(
                    "PROVIDE LABEL ON THE LIGHT SWITCH COVER PLATE INDICATING"
                ),
                pdf_path=path, page_index=0,
            )
        finally:
            os.unlink(path)

        assert result["_skipped"] is True
        assert result["_skip_keyword"] == "COVER"
        assert "PLATE" in result["_skip_context"]
        assert result["_skip_reason"]
        assert set(result["_measurable_signal"]) == {
            "plan_titles", "printed_scales", "viewports", "schedules",
        }

    def test_skipping_without_a_ledger_row_still_works(self):
        """coverage=None is the scraper's path — it must stay byte-compatible."""
        pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
        result = pipeline.run_sheet(
            image_path="/path/G0.1.png", sheet_name="G0.1",
            sheet_type="title_sheet",
        )
        assert result["_skipped"] is True
        assert result["sheet_type"] == "title_sheet"
        assert result["sheet_name"] == "G0.1"
        assert result["sheet_source"] == "/path/G0.1.png"

    def test_no_pdf_path_means_no_veto(self):
        """An image-only caller has no page to ask; the verdict stands."""
        pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
        coverage = SheetCoverage(page_index=0)
        result = pipeline.run_sheet(
            image_path="x.png", sheet_name="G0.1", sheet_type="title_sheet",
            coverage=coverage,
        )
        assert result["_skipped"] is True
        assert coverage.classifier_overruled is False

    def test_an_unreadable_pdf_does_not_abort_the_sheet(self):
        """Threat T-23-01: a malformed page must not stop the run."""
        pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
        signal, fires = pipeline._skip_veto_signal("/no/such/file.pdf", 0, "X")
        assert fires is False
        assert sum(signal.values()) == 0


class TestRunSheetSignature:
    def test_coverage_is_keyword_only_with_a_none_default(self):
        """run_sheet has four call sites, three of them in scrape/scraper.py."""
        import inspect
        param = inspect.signature(TakeoffPipeline.run_sheet).parameters["coverage"]
        assert param.default is None
        assert param.kind == inspect.Parameter.KEYWORD_ONLY

    def test_run_project_coverage_is_keyword_only_with_a_none_default(self):
        import inspect
        param = inspect.signature(TakeoffPipeline.run_project).parameters["coverage"]
        assert param.default is None
        assert param.kind == inspect.Parameter.KEYWORD_ONLY

    def test_positional_call_shape_is_unchanged(self):
        """The scraper calls run_sheet positionally — the order must not move."""
        import inspect
        params = list(inspect.signature(TakeoffPipeline.run_sheet).parameters)
        assert params[:9] == [
            "self", "image_path", "sheet_name", "sheet_type", "title_block_text",
            "full_page_text", "pdf_path", "page_index", "budget",
        ]


class TestRunProjectThreadsTheLedger:
    def test_every_page_keeps_its_row_even_when_skipped(self):
        """The sentinel stays out of all_extracted; the page stays in the ledger."""
        ledger = CoverageLedger(pages_in_source=2)
        ledger.register_page(0)
        ledger.register_page(1)
        pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
        pages = [
            {"image_path": "a.png", "sheet_name": "CS-00",
             "sheet_type_hint": "title_sheet", "page_index": 0, "page_num": 1},
            {"image_path": "b.png", "sheet_name": "CS-01",
             "sheet_type_hint": "title_sheet", "page_index": 1, "page_num": 2},
        ]
        all_extracted, _est, _ptype = pipeline.run_project(pages, coverage=ledger)

        assert all_extracted == []                  # both skipped, as today
        assert ledger.assert_accounted() == []      # but neither page vanished
        assert len(ledger.sheets) == 2
        assert ledger.sheet(0).sheet_name == "CS-00"
        assert ledger.sheet(0).disposition == NOT_APPLICABLE
        assert pipeline.coverage_ledger is ledger

    def test_run_project_without_a_ledger_is_unchanged(self):
        pipeline = TakeoffPipeline(analyzer=_exploding_analyzer)
        pages = [{"image_path": "a.png", "sheet_name": "CS-00",
                  "sheet_type_hint": "title_sheet", "page_index": 0}]
        all_extracted, _est, _ptype = pipeline.run_project(pages)
        assert all_extracted == []
        assert pipeline.coverage_ledger is None
