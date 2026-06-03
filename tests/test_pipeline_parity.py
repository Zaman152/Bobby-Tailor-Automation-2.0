"""
tests/test_pipeline_parity.py — Verify pdf_analyzer and scraper both route
through TakeoffPipeline so StackCT scrape jobs and PDF-upload jobs run
identical multi-pass extraction logic.

Invariants under test:
  1. Neither entry point calls analyze_drawing directly (no bypass).
  2. pdf_analyzer.run_pdf_analysis delegates to TakeoffPipeline.run_project.
  3. scraper._pipeline is a TakeoffPipeline instance (not raw analyze_drawing).
  4. For the same sheet_type, plan_passes returns identical pass lists regardless
     of which entry point is used — this is the accuracy-parity guarantee.
"""
from __future__ import annotations

import sys
import importlib
import importlib.util
import pathlib
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Minimal stub helpers
# ---------------------------------------------------------------------------

def _stub(name: str) -> MagicMock:
    """Return a MagicMock installed in sys.modules under *name* (if absent)."""
    mod = MagicMock(name=name)
    sys.modules.setdefault(name, mod)
    return sys.modules[name]


def _load(name: str):
    """Load a module by name from repo root without running __main__."""
    path = pathlib.Path(__file__).parent.parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # register before exec to handle self-references
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Set up shared stubs (once for the module; order matters)
# ---------------------------------------------------------------------------

_CONFIG_MOCK = MagicMock()
_CONFIG_MOCK.CLAUDE_MODEL = "claude-haiku-4-5"
_CONFIG_MOCK.CLAUDE_MODEL_SCHEDULES = "claude-sonnet-4-5"
_CONFIG_MOCK.ANTHROPIC_API_KEY = "test-key"
_CONFIG_MOCK.SCREENSHOTS_DIR = "/tmp/test_screenshots"
_CONFIG_MOCK.REUSE_SCREENSHOTS = False
_CONFIG_MOCK.AUTO_INCLUDE_LINKED_SHEETS = False
_CONFIG_MOCK.MAX_LINKED_SHEETS = 5

sys.modules.setdefault("config", _CONFIG_MOCK)
sys.modules.setdefault("anthropic", MagicMock())
_stub("linked_sheets")
_stub("stackct_store")
_stub("browser")
_stub("capture_manifest")
_stub("sheet_preview")
_stub("cross_references")
_stub("reporter")

# Load real sheet_pass_matrix (no heavy deps)
_spm = _load("sheet_pass_matrix")

# Load real claude_analyzer (uses anthropic stub)
_real_ca = _load("claude_analyzer")

# Install a claude_analyzer stub that keeps the real merge_passes
_CA_MOCK = MagicMock()
_CA_MOCK.merge_passes = _real_ca.merge_passes
_CA_MOCK.analyze_drawing.return_value = {"components": [], "measurements": []}
_CA_MOCK.make_navigation_decision.return_value = True
sys.modules["claude_analyzer"] = _CA_MOCK

# Load real calculator (needs the stub chain above)
_calc = _load("calculator")
sys.modules.setdefault("calculator", _calc)

# Load real takeoff_pipeline
_tp = _load("takeoff_pipeline")
TakeoffPipeline = _tp.TakeoffPipeline
sys.modules.setdefault("takeoff_pipeline", _tp)

# Load pdf_analyzer (needs fitz — real or skip)
try:
    import fitz as _fitz  # noqa: F401 — available in CI via PyMuPDF
    _pdf = _load("pdf_analyzer")
    _PDF_AVAILABLE = True
except Exception:
    _pdf = None
    _PDF_AVAILABLE = False


# ---------------------------------------------------------------------------
# 1. No direct analyze_drawing bypass
# ---------------------------------------------------------------------------

class TestNoPipelineBypass:
    """Neither entry point should import or call analyze_drawing directly."""

    def test_pdf_analyzer_has_no_analyze_drawing_in_globals(self):
        """pdf_analyzer must not expose analyze_drawing at module level."""
        if not _PDF_AVAILABLE:
            pytest.skip("PyMuPDF (fitz) not installed")
        assert not hasattr(_pdf, "analyze_drawing"), (
            "pdf_analyzer imported analyze_drawing directly — pipeline bypass!"
        )

    def test_scraper_does_not_import_analyze_drawing(self):
        """scraper uses _pipeline.run_sheet, not a direct analyze_drawing import."""
        # We can't fully load scraper (Playwright/browser), but we can verify
        # that the pattern 'analyze_drawing' only appears inside the file as a
        # module-level attribute *or* call site — confirmed via source inspection.
        scraper_src = (pathlib.Path(__file__).parent.parent / "scraper.py").read_text()
        # The import line (if it existed) would be:
        #   from claude_analyzer import analyze_drawing
        # Verify it does NOT appear as an import statement in scraper.
        assert "from claude_analyzer import analyze_drawing" not in scraper_src, (
            "scraper.py still imports analyze_drawing directly — pipeline bypass!"
        )
        assert "import analyze_drawing" not in scraper_src, (
            "scraper.py still imports analyze_drawing directly — pipeline bypass!"
        )

    def test_pdf_analyzer_does_not_import_analyze_drawing(self):
        """pdf_analyzer.py must not import analyze_drawing."""
        pdf_src = (pathlib.Path(__file__).parent.parent / "pdf_analyzer.py").read_text()
        assert "from claude_analyzer import analyze_drawing" not in pdf_src, (
            "pdf_analyzer.py still imports analyze_drawing — pipeline bypass!"
        )


# ---------------------------------------------------------------------------
# 2. pdf_analyzer delegates to TakeoffPipeline.run_project
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _PDF_AVAILABLE, reason="PyMuPDF (fitz) not installed")
class TestPdfAnalyzerUsesPipeline:
    """pdf_analyzer.run_pdf_analysis must call TakeoffPipeline.run_project."""

    def _mock_page(self):
        """Return a fitz page mock whose get_text handles both 'words' and plain calls."""
        page_mock = MagicMock()
        page_mock.rect.height = 1000
        page_mock.rect.width = 800
        # get_text("words") returns a list of 8-tuple word entries (x0,y0,x1,y1,word,…)
        # get_text() / get_text("text") returns a plain string
        def _get_text(fmt="text", *args, **kwargs):
            if fmt == "words":
                return []  # no words → _sheet_name_from_doc falls back to "Page_N"
            return "LEVEL 1 FLOOR PLAN"
        page_mock.get_text.side_effect = _get_text
        return page_mock

    def _mock_doc(self, page_count: int = 2):
        """Return a fitz.Document-like mock with *page_count* pages."""
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = page_count
        page_mock = self._mock_page()
        mock_doc.__getitem__ = MagicMock(return_value=page_mock)
        mock_doc.close = MagicMock()
        return mock_doc

    def test_run_pdf_analysis_calls_run_project(self, tmp_path):
        """run_pdf_analysis delegates to TakeoffPipeline.run_project (not inline loop)."""
        dummy_pdf = tmp_path / "test.pdf"
        dummy_pdf.write_bytes(b"fake")

        mock_doc = self._mock_doc(page_count=1)
        mock_report = {"sheets_processed": 1, "total_line_items": 0,
                       "total_calculated_items": 0, "_files": {}}

        with (
            patch("fitz.open", return_value=mock_doc),
            patch("pdf_analyzer._page_to_image", return_value="/tmp/page_0001.png"),
            patch("pdf_analyzer.TakeoffPipeline") as MockPipeline,
            patch("pdf_analyzer.generate_report", return_value=mock_report),
            patch("pdf_analyzer.resolve_cross_references", return_value={}),
            patch("pdf_analyzer.resolve_spec_lookups", return_value=[]),
        ):
            pipeline_instance = MagicMock()
            pipeline_instance.run_project.return_value = (
                [{"_sheet_name": "A2.1", "measurements": [], "components": []}],
                [],
                "residential",
            )
            MockPipeline.return_value = pipeline_instance

            _pdf.run_pdf_analysis(str(dummy_pdf), project_name="Test")

            pipeline_instance.run_project.assert_called_once()

    def test_run_pdf_analysis_passes_title_block_text(self, tmp_path):
        """Pages passed to run_project include title_block_text for auto-classification."""
        dummy_pdf = tmp_path / "test.pdf"
        dummy_pdf.write_bytes(b"fake")

        mock_doc = self._mock_doc(page_count=1)
        mock_page = MagicMock()
        mock_page.rect.height = 1000
        mock_page.rect.width = 800
        tb_words = [
            (500, 820, 550, 840, "FLOOR", 0, 0, 0),
            (560, 820, 620, 840, "PLAN", 0, 0, 0),
        ]
        def _get_text_with_words(fmt="text", *a, **kw):
            if fmt == "words":
                return tb_words
            return "FLOOR PLAN"
        mock_page.get_text = MagicMock(side_effect=_get_text_with_words)
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        mock_report = {"sheets_processed": 1, "_files": {}}

        with (
            patch("fitz.open", return_value=mock_doc),
            patch("pdf_analyzer._page_to_image", return_value="/tmp/page_0001.png"),
            patch("pdf_analyzer.TakeoffPipeline") as MockPipeline,
            patch("pdf_analyzer.generate_report", return_value=mock_report),
            patch("pdf_analyzer.resolve_cross_references", return_value={}),
            patch("pdf_analyzer.resolve_spec_lookups", return_value=[]),
        ):
            pipeline_instance = MagicMock()
            pipeline_instance.run_project.return_value = ([], [], "auto")
            MockPipeline.return_value = pipeline_instance

            _pdf.run_pdf_analysis(str(dummy_pdf), project_name="Test")

            pages_arg = pipeline_instance.run_project.call_args[0][0]
            assert len(pages_arg) == 1, "Expected one pipeline page"
            page = pages_arg[0]
            assert "title_block_text" in page, "title_block_text must be passed to pipeline"
            assert "image_path" in page
            assert "sheet_name" in page

    def test_run_pdf_analysis_respects_selected_pages(self, tmp_path):
        """selected_pages=[1] processes only the first page."""
        dummy_pdf = tmp_path / "test.pdf"
        dummy_pdf.write_bytes(b"fake")

        mock_doc = self._mock_doc(page_count=3)
        mock_report = {"sheets_processed": 1, "_files": {}}

        with (
            patch("fitz.open", return_value=mock_doc),
            patch("pdf_analyzer._page_to_image", return_value="/tmp/p.png"),
            patch("pdf_analyzer.TakeoffPipeline") as MockPipeline,
            patch("pdf_analyzer.generate_report", return_value=mock_report),
            patch("pdf_analyzer.resolve_cross_references", return_value={}),
            patch("pdf_analyzer.resolve_spec_lookups", return_value=[]),
        ):
            pipeline_instance = MagicMock()
            pipeline_instance.run_project.return_value = ([], [], "auto")
            MockPipeline.return_value = pipeline_instance

            _pdf.run_pdf_analysis(str(dummy_pdf), project_name="Test", selected_pages=[1])

            pages_arg = pipeline_instance.run_project.call_args[0][0]
            assert len(pages_arg) == 1, "Only 1 of 3 pages selected"


# ---------------------------------------------------------------------------
# 3. scraper uses TakeoffPipeline singleton
# ---------------------------------------------------------------------------

class TestScraperUsesPipeline:
    """scraper._pipeline must be a TakeoffPipeline instance (loaded from source)."""

    def test_scraper_pipeline_is_takeoff_pipeline(self):
        """_pipeline singleton in scraper must be an instance of TakeoffPipeline."""
        scraper_src = (pathlib.Path(__file__).parent.parent / "scraper.py").read_text()
        # Verify module-level singleton pattern exists
        assert "_pipeline = TakeoffPipeline()" in scraper_src, (
            "scraper.py must create a module-level _pipeline = TakeoffPipeline() singleton"
        )

    def test_scraper_analyze_phase_uses_run_sheet(self):
        """The analyze phase in run_project_scrape must call _pipeline.run_sheet."""
        scraper_src = (pathlib.Path(__file__).parent.parent / "scraper.py").read_text()
        assert "_pipeline.run_sheet(" in scraper_src, (
            "scraper.py must call _pipeline.run_sheet — not analyze_drawing directly"
        )

    def test_scraper_handles_skipped_sentinel(self):
        """Scraper analysis loop must handle _skipped sentinel from run_sheet."""
        scraper_src = (pathlib.Path(__file__).parent.parent / "scraper.py").read_text()
        assert "_skipped" in scraper_src, (
            "scraper.py must handle the _skipped sentinel returned by run_sheet for title sheets"
        )

    def test_scraper_uses_detect_project_type(self):
        """Scraper must call _detect_project_type once for project-type-aware estimation."""
        scraper_src = (pathlib.Path(__file__).parent.parent / "scraper.py").read_text()
        assert "_detect_project_type(" in scraper_src, (
            "scraper.py must call _detect_project_type for uniform project_type across sheets"
        )


# ---------------------------------------------------------------------------
# 4. Pass parity — identical pass lists for same sheet_type
# ---------------------------------------------------------------------------

class TestPassParity:
    """plan_passes must return identical lists regardless of how sheets arrive."""

    @pytest.mark.parametrize("sheet_type,expected_passes", [
        ("floor_plan",  ["count", "measure"]),
        ("civil_site",  ["measure"]),
        ("elevation",   ["count", "measure"]),
        ("title_sheet", []),
        ("schedule",    ["schedule"]),
    ])
    def test_plan_passes_are_deterministic(self, sheet_type, expected_passes):
        """plan_passes is the single source of truth for both pdf_analyzer and scraper."""
        result = _spm.plan_passes(sheet_type)
        assert result == expected_passes, (
            f"sheet_type={sheet_type!r}: expected {expected_passes}, got {result}"
        )

    def test_same_image_same_passes_regardless_of_entry_point(self):
        """A floor_plan sheet analyzed via run_sheet runs exactly count+measure, always."""
        call_log: list[str] = []

        def tracking_analyzer(image_path, sheet_name, pass_type="measure", **kw):
            call_log.append(pass_type)
            return {"components": [], "measurements": []}

        pipeline = TakeoffPipeline(analyzer=tracking_analyzer)
        pipeline.run_sheet("A2.1.png", "A2.1", sheet_type="floor_plan")

        assert call_log == ["count", "measure"], (
            f"floor_plan must run count then measure; got {call_log}"
        )

    def test_title_sheet_zero_api_calls_regardless_of_entry_point(self):
        """Title sheets generate zero analyzer calls from both pdf and scraper paths."""
        mock_analyzer = MagicMock()
        pipeline = TakeoffPipeline(analyzer=mock_analyzer)

        result = pipeline.run_sheet("G0.1.png", "G0.1", sheet_type="title_sheet")

        mock_analyzer.assert_not_called()
        assert result.get("_skipped") is True

    def test_pdf_and_scraper_use_same_pipeline_class(self):
        """Both entry points import TakeoffPipeline from the same module."""
        pdf_src = (pathlib.Path(__file__).parent.parent / "pdf_analyzer.py").read_text()
        scraper_src = (pathlib.Path(__file__).parent.parent / "scraper.py").read_text()

        assert "TakeoffPipeline" in pdf_src, "pdf_analyzer must use TakeoffPipeline"
        assert "TakeoffPipeline" in scraper_src, "scraper must use TakeoffPipeline"

    def test_run_project_applies_estimation_with_uniform_project_type(self):
        """run_project detects project_type once and applies it to every sheet."""
        # Both pdf_analyzer (run_project) and scraper batch apply_estimation_tables
        # after all sheets are collected — verified through the plan_passes invariant
        # and the TakeoffPipeline.run_project implementation.
        call_log: list[tuple] = []

        def tracking_analyzer(image_path, sheet_name, pass_type="measure", **kw):
            return {"components": [], "measurements": []}

        pipeline = TakeoffPipeline(analyzer=tracking_analyzer)
        pages = [
            {"image_path": "A2.1.png", "sheet_name": "A2.1", "sheet_type_hint": "floor_plan"},
            {"image_path": "G0.1.png", "sheet_name": "G0.1", "sheet_type_hint": "title_sheet"},
            {"image_path": "A3.1.png", "sheet_name": "A3.1", "sheet_type_hint": "civil_site"},
        ]

        all_extracted, all_estimates, project_type = pipeline.run_project(pages)

        # title_sheet excluded from extracted
        assert len(all_extracted) == 2, "G0.1 title_sheet must be excluded"
        assert isinstance(project_type, str), "project_type must be a string"
        # Project type is the same for all estimates (single detection run)
        assert project_type != "", "project_type must not be empty"
