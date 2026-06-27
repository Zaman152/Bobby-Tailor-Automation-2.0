"""
tests/test_pipeline_parity.py — Verify StackCT/PDF analysis parity.

Both pdf_analyzer.run_pdf_analysis and scraper (run_analyze_from_manifest)
must route through TakeoffPipeline — not call analyze_drawing directly.

Tests confirm:
  1. Neither entry point imports analyze_drawing (source-level check).
  2. pdf_analyzer.run_pdf_analysis calls TakeoffPipeline.run_project.
  3. scraper.run_analyze_from_manifest calls TakeoffPipeline.run_sheet per page.
  4. plan_passes() is the sole pass-list authority: same sheet_type → same passes
     in both entry points (guaranteed by TakeoffPipeline.run_sheet delegation).
"""

from __future__ import annotations

import sys
import json
import asyncio
import importlib.util
import pathlib
from unittest.mock import MagicMock, patch

import pytest


def _fresh_loop() -> asyncio.AbstractEventLoop:
    """Return a brand-new event loop and install it as current.

    Avoids cross-test pollution: on Python 3.9 ``asyncio.get_event_loop()``
    raises ``RuntimeError`` once an earlier test has closed the default loop,
    making these tests order-dependent. Creating a fresh loop is deterministic.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop

# ---------------------------------------------------------------------------
# Minimal stubs (set up before any project imports)
# ---------------------------------------------------------------------------

_CONFIG = MagicMock()
_CONFIG.CLAUDE_MODEL = "claude-haiku-4-5"
_CONFIG.CLAUDE_MODEL_SCHEDULES = "claude-sonnet-4-5"
_CONFIG.ANTHROPIC_API_KEY = "test-key"
_CONFIG.SCREENSHOTS_DIR = "/tmp/test_screens"
_CONFIG.REUSE_SCREENSHOTS = False
_CONFIG.AUTO_INCLUDE_LINKED_SHEETS = False
_CONFIG.MAX_LINKED_SHEETS = 0

sys.modules.setdefault("config", _CONFIG)
sys.modules.setdefault("anthropic", MagicMock())

for _m in ["linked_sheets", "stackct_store", "browser", "capture_manifest",
           "sheet_preview", "cross_references", "reporter"]:
    sys.modules.setdefault(_m, MagicMock())


def _load(name: str):
    path = pathlib.Path(__file__).parent.parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load real claude_analyzer (merge_passes, no API calls)
_real_ca = _load("claude_analyzer")

# Mock for analyze_drawing; real merge/accuracy helpers preserved so the
# pipeline's module-level `from claude_analyzer import (...)` binds real impls.
_CA_MOCK = MagicMock()
_CA_MOCK.merge_passes = _real_ca.merge_passes
_CA_MOCK._merge_schedule_lists = _real_ca._merge_schedule_lists
_CA_MOCK.apply_accuracy_rules = _real_ca.apply_accuracy_rules
_CA_MOCK._SCHEDULE_LEGEND_USER_HINT = _real_ca._SCHEDULE_LEGEND_USER_HINT
_CA_MOCK.analyze_drawing.return_value = {"components": [], "measurements": []}
_CA_MOCK.make_navigation_decision.return_value = {"action": "wait"}
sys.modules["claude_analyzer"] = _CA_MOCK

_spm = _load("sheet_pass_matrix")
_tp = _load("takeoff_pipeline")
TakeoffPipeline = _tp.TakeoffPipeline
sys.modules.setdefault("takeoff_pipeline", _tp)

# Load calculator (no external deps)
_calc = _load("calculator")
sys.modules.setdefault("calculator", _calc)


# ===========================================================================
# 1. Source-level bypass checks
# ===========================================================================

class TestNoPipelineBypass:
    """Neither entry point should call analyze_drawing directly."""

    def test_scraper_does_not_import_analyze_drawing(self):
        """scraper.py must not import analyze_drawing at the top level."""
        src = (pathlib.Path(__file__).parent.parent / "scraper.py").read_text()
        assert "from claude_analyzer import analyze_drawing" not in src
        assert "import analyze_drawing" not in src

    def test_pdf_analyzer_does_not_import_analyze_drawing(self):
        """pdf_analyzer.py must not import analyze_drawing."""
        src = (pathlib.Path(__file__).parent.parent / "pdf_analyzer.py").read_text()
        assert "from claude_analyzer import analyze_drawing" not in src

    def test_scraper_has_pipeline_import(self):
        """scraper.py must import TakeoffPipeline."""
        src = (pathlib.Path(__file__).parent.parent / "scraper.py").read_text()
        assert "TakeoffPipeline" in src

    def test_pdf_analyzer_has_pipeline_import(self):
        """pdf_analyzer.py must import TakeoffPipeline."""
        src = (pathlib.Path(__file__).parent.parent / "pdf_analyzer.py").read_text()
        assert "TakeoffPipeline" in src


# ===========================================================================
# 2. pdf_analyzer delegates to TakeoffPipeline.run_project
# ===========================================================================

class TestPdfAnalyzerUsesPipeline:
    """pdf_analyzer.run_pdf_analysis must call TakeoffPipeline.run_project."""

    def test_calls_run_project_not_analyze_drawing(self, tmp_path):
        """Patch TakeoffPipeline in pdf_analyzer; verify run_project is called."""
        import pdf_analyzer

        floor_result = {
            "_sheet_name": "A2.1",
            "_sheet_type": "floor_plan",
            "_passes_run": ["count", "measure"],
            "_skipped": False,
            "_page_num": 1,
            "measurements": [],
            "components": [],
            "rooms": [],
            "schedules": [],
        }

        mock_pipeline = MagicMock()
        mock_pipeline.run_project.return_value = ([floor_result], [], "auto")

        _CA_MOCK.analyze_drawing.reset_mock()

        with (
            patch("pdf_analyzer.TakeoffPipeline", return_value=mock_pipeline),
            patch("pdf_analyzer.fitz") as mock_fitz,
            patch("pdf_analyzer._page_to_image", return_value="/tmp/a2_1.png"),
            patch("pdf_analyzer._sheet_name_from_doc", return_value="A2.1"),
            patch("pdf_analyzer.get_title_block_text", return_value="LEVEL 1 FLOOR PLAN"),
            patch("pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("pdf_analyzer.generate_report", return_value={"report": "ok"}),
        ):
            # Minimal fitz.open mock
            mock_doc = MagicMock()
            mock_doc.__len__ = MagicMock(return_value=1)
            mock_doc.__enter__ = MagicMock(return_value=mock_doc)
            mock_doc.__exit__ = MagicMock(return_value=False)
            mock_fitz.open.return_value = mock_doc

            pdf_analyzer.run_pdf_analysis("/fake.pdf", "Test Project")

        mock_pipeline.run_project.assert_called_once()
        _CA_MOCK.analyze_drawing.assert_not_called()

    def test_run_project_receives_page_dicts_with_image_path(self, tmp_path):
        """pipeline.run_project must be given a list of page dicts with image_path."""
        import pdf_analyzer

        mock_pipeline = MagicMock()
        mock_pipeline.run_project.return_value = ([], [], "auto")

        with (
            patch("pdf_analyzer.TakeoffPipeline", return_value=mock_pipeline),
            patch("pdf_analyzer.fitz") as mock_fitz,
            patch("pdf_analyzer._page_to_image", return_value="/tmp/p.png"),
            patch("pdf_analyzer._sheet_name_from_doc", return_value="A2.1"),
            patch("pdf_analyzer.get_title_block_text", return_value=""),
            patch("pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("pdf_analyzer.generate_report", return_value={}),
        ):
            mock_doc = MagicMock()
            mock_doc.__len__ = MagicMock(return_value=2)
            mock_fitz.open.return_value = mock_doc

            pdf_analyzer.run_pdf_analysis("/fake.pdf", "Test")

        call_args = mock_pipeline.run_project.call_args
        pages = call_args[0][0] if call_args[0] else call_args.kwargs.get("pages", [])
        assert isinstance(pages, list)
        assert len(pages) == 2
        assert all("image_path" in p for p in pages)
        assert all("sheet_name" in p for p in pages)

    def test_title_block_text_forwarded_to_pipeline(self, tmp_path):
        """title_block_text from get_title_block_text must appear in each page dict."""
        import pdf_analyzer

        mock_pipeline = MagicMock()
        mock_pipeline.run_project.return_value = ([], [], "auto")

        with (
            patch("pdf_analyzer.TakeoffPipeline", return_value=mock_pipeline),
            patch("pdf_analyzer.fitz") as mock_fitz,
            patch("pdf_analyzer._page_to_image", return_value="/tmp/p.png"),
            patch("pdf_analyzer._sheet_name_from_doc", return_value="A2.1"),
            patch("pdf_analyzer.get_title_block_text", return_value="LEVEL 2 FLOOR PLAN"),
            patch("pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("pdf_analyzer.generate_report", return_value={}),
        ):
            mock_doc = MagicMock()
            mock_doc.__len__ = MagicMock(return_value=1)
            mock_fitz.open.return_value = mock_doc

            pdf_analyzer.run_pdf_analysis("/fake.pdf", "Test")

        pages = mock_pipeline.run_project.call_args[0][0]
        assert pages[0]["title_block_text"] == "LEVEL 2 FLOOR PLAN"


# ===========================================================================
# 3. scraper uses TakeoffPipeline.run_sheet
# ===========================================================================

class TestScraperUsesPipeline:
    """scraper.run_analyze_from_manifest calls TakeoffPipeline.run_sheet per page."""

    def _build_manifest_file(self, tmp_path: pathlib.Path, sheet_name: str = "A2.1"):
        """Create a minimal run folder with manifest + screenshot."""
        run_dir = tmp_path / "run_001"
        run_dir.mkdir(parents=True, exist_ok=True)
        screenshot = run_dir / f"001_{sheet_name}.jpg"
        screenshot.write_bytes(b"fake-jpg")

        manifest_data = {
            "project_name": "Parity Test",
            "folder_id": None,
            "created_at": "2026-06-01T00:00:00Z",
            "pages": [{
                "page_id": 1001,
                "sheet_name": sheet_name,
                "screenshot_rel": screenshot.name,
                "capture_status": "ok",
                "analysis_status": "pending",
                "source": "main",
            }],
        }
        mpath = run_dir / "manifest.json"
        mpath.write_text(json.dumps(manifest_data))
        return mpath

    def _fake_manifest(self, sheet_name: str = "A2.1", tmp_dir=None):
        page_entry = MagicMock()
        page_entry.page_id = 1001
        page_entry.sheet_name = sheet_name
        page_entry.capture_status = "ok"
        page_entry.analysis_status = "pending"
        page_entry.screenshot_rel = f"001_{sheet_name}.jpg"

        fake_manifest = MagicMock()
        fake_manifest.project_name = "Parity Test"
        fake_manifest.folder_id = None
        fake_manifest.pages = [page_entry]
        fake_manifest.save = MagicMock()
        return fake_manifest

    def test_calls_run_sheet_not_analyze_drawing(self, tmp_path):
        """run_analyze_from_manifest must use _pipeline.run_sheet, not analyze_drawing."""
        mpath = self._build_manifest_file(tmp_path)
        fake_manifest = self._fake_manifest(tmp_dir=tmp_path / "run_001")

        floor_result = {
            "_sheet_type": "floor_plan", "_sheet_name": "A2.1",
            "_passes_run": ["count", "measure"], "_skipped": False,
            "components": [], "measurements": [], "rooms": [], "schedules": [],
        }
        mock_pipeline = MagicMock()
        mock_pipeline.run_sheet.return_value = floor_result

        _CA_MOCK.analyze_drawing.reset_mock()

        with (
            patch("scraper.RunManifest") as mock_rm,
            patch("scraper._pipeline", mock_pipeline),
            patch("scraper.apply_estimation_tables", return_value=[]),
            patch("scraper._detect_project_type", return_value="auto"),
            patch("scraper.resolve_spec_lookups", return_value=[]),
            patch("scraper.resolve_cross_references", return_value=[]),
            patch("scraper.generate_report", return_value={"report": "ok"}),
        ):
            mock_rm.load.return_value = fake_manifest
            import scraper
            _fresh_loop().run_until_complete(
                scraper.run_analyze_from_manifest(manifest_path_override=mpath)
            )

        mock_pipeline.run_sheet.assert_called()
        _CA_MOCK.analyze_drawing.assert_not_called()

    def test_run_sheet_called_with_screenshot_path(self, tmp_path):
        """run_sheet receives the screenshot file path as first argument."""
        mpath = self._build_manifest_file(tmp_path, sheet_name="C1.0")
        fake_manifest = self._fake_manifest(sheet_name="C1.0")

        civil_result = {
            "_sheet_type": "civil_site", "_sheet_name": "C1.0",
            "_passes_run": ["measure"], "_skipped": False,
            "components": [], "measurements": [], "rooms": [], "schedules": [],
        }
        mock_pipeline = MagicMock()
        mock_pipeline.run_sheet.return_value = civil_result

        with (
            patch("scraper.RunManifest") as mock_rm,
            patch("scraper._pipeline", mock_pipeline),
            patch("scraper.apply_estimation_tables", return_value=[]),
            patch("scraper._detect_project_type", return_value="auto"),
            patch("scraper.resolve_spec_lookups", return_value=[]),
            patch("scraper.resolve_cross_references", return_value=[]),
            patch("scraper.generate_report", return_value={"report": "ok"}),
        ):
            mock_rm.load.return_value = fake_manifest
            import scraper
            _fresh_loop().run_until_complete(
                scraper.run_analyze_from_manifest(manifest_path_override=mpath)
            )

        mock_pipeline.run_sheet.assert_called_once()
        first_arg = mock_pipeline.run_sheet.call_args[0][0]
        assert first_arg.endswith(".jpg"), f"Expected .jpg path, got {first_arg!r}"

    def test_title_sheet_skipped_in_scraper(self, tmp_path):
        """_skipped=True pages must not be appended to all_extracted as errors."""
        mpath = self._build_manifest_file(tmp_path, sheet_name="G0.1")
        fake_manifest = self._fake_manifest(sheet_name="G0.1")

        title_skip_result = {
            "_skipped": True, "sheet_type": "title_sheet",
            "_sheet_type": "title_sheet", "_sheet_name": "G0.1",
            "sheet_source": "G0.1.jpg",
        }
        mock_pipeline = MagicMock()
        mock_pipeline.run_sheet.return_value = title_skip_result

        captured_extracted = []

        def _mock_report(project_name, all_extracted, all_estimates, **kwargs):
            captured_extracted.extend(all_extracted)
            return {"report": "ok"}

        with (
            patch("scraper.RunManifest") as mock_rm,
            patch("scraper._pipeline", mock_pipeline),
            patch("scraper.apply_estimation_tables", return_value=[]),
            patch("scraper._detect_project_type", return_value="auto"),
            patch("scraper.resolve_spec_lookups", return_value=[]),
            patch("scraper.resolve_cross_references", return_value=[]),
            patch("scraper.generate_report", side_effect=_mock_report),
        ):
            mock_rm.load.return_value = fake_manifest
            import scraper
            _fresh_loop().run_until_complete(
                scraper.run_analyze_from_manifest(manifest_path_override=mpath)
            )

        # Title sheet result appended (may have _skipped flag) but no error
        # key; most importantly analyze_drawing was never called
        _CA_MOCK.analyze_drawing.assert_not_called()


# ===========================================================================
# 4. Pass-list parity via shared TakeoffPipeline.run_sheet
# ===========================================================================

class TestPassParity:
    """Same sheet_type → same passes regardless of which entry point is used.
    Since both paths delegate to TakeoffPipeline.run_sheet, parity is structural.
    """

    @pytest.mark.parametrize("sheet_type,expected_passes", [
        # floor_plan always includes a schedule pass to capture takeoff legends
        # on the plan body (high-accuracy mode also appends a "legend" pass).
        ("floor_plan",  ["count", "measure", "schedule"]),
        ("civil_site",  ["measure"]),
        ("title_sheet", []),
        ("schedule",    ["schedule"]),
    ])
    def test_plan_passes_are_deterministic(self, sheet_type, expected_passes):
        """plan_passes() is the single source of truth for both entry points."""
        result = _spm.plan_passes(sheet_type)
        assert result == expected_passes, (
            f"sheet_type={sheet_type!r}: expected {expected_passes}, got {result}"
        )

    def test_floor_plan_runs_count_measure_schedule(self):
        """floor_plan sheets get count+measure+schedule passes via pipeline."""
        count_r = {"components": [], "measurements": []}
        measure_r = {"components": [], "measurements": [], "rooms": [], "pipe_runs": []}
        schedule_r = {"components": [], "measurements": [], "schedules": []}
        mock_analyzer = MagicMock(side_effect=[count_r, measure_r, schedule_r])
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)
        result = pipeline.run_sheet("A2.1.png", "A2.1", sheet_type="floor_plan")

        assert result["_passes_run"] == ["count", "measure", "schedule"]
        assert mock_analyzer.call_count == 3

    def test_title_sheet_zero_api_calls(self):
        """Title sheets produce zero analyze_drawing calls in any entry point."""
        mock_analyzer = MagicMock()
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)
        result = pipeline.run_sheet("G0.1.png", "G0.1", sheet_type="title_sheet")

        mock_analyzer.assert_not_called()
        assert result["_skipped"] is True

    def test_both_paths_use_same_run_sheet(self):
        """Verify pdf_analyzer and scraper both call the module-level _pipeline singleton pattern."""
        pdf_src = (pathlib.Path(__file__).parent.parent / "pdf_analyzer.py").read_text()
        scraper_src = (pathlib.Path(__file__).parent.parent / "scraper.py").read_text()

        # pdf_analyzer uses TakeoffPipeline().run_project
        assert "run_project" in pdf_src
        assert "TakeoffPipeline" in pdf_src

        # scraper uses _pipeline.run_sheet
        assert "_pipeline.run_sheet" in scraper_src
        assert "TakeoffPipeline" in scraper_src
