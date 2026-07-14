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

21-15 (V3-STRUCT-02 + V3-LEARN-04) extensions:
  5. RunSettings parity — both entry points construct RunSettings.from_env()
     and hand the identical settings to the pipeline.
  6. Deterministic call-site parity — a vector page reaches
     extract_dimension_samples + fuse_sheet from BOTH entry-point flows.
  7. Learning call-site parity — the learning seam (RunSettings.learning_enabled;
     retrieval hook once 21-16 lands) is shared identically by both paths.
  8. Companion isolation — a sibling `*Take offs.pdf` beside the plans PDF is
     NEVER opened by the production path, and find_companion_takeoff_pdf is
     absent from production module namespaces (plans-only LOCKED contract).
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

sys.modules.setdefault("bobbytailor.config", _CONFIG)
sys.modules.setdefault("anthropic", MagicMock())

# Solo-run hermeticity: stub heavy/env-dependent dependencies so this file can
# run without playwright/.env. Under full-suite collection the real modules are
# pre-registered by conftest.py, so every setdefault below is a no-op.
for _m in [
    "bobbytailor.scrape.linked_sheets",
    "bobbytailor.stores.stackct_store",
    "bobbytailor.scrape.browser",
    "bobbytailor.scrape.capture_manifest",
    "bobbytailor.scrape.sheet_preview",
    "bobbytailor.pipeline.cross_references",
    "bobbytailor.pipeline.reporter",
]:
    sys.modules.setdefault(_m, MagicMock())


# Phase 21 (V3-STRUCT-01): real modules live under src/bobbytailor/. Load and
# inspect the real sources directly under isolated spec names.
_SRC_ROOT = pathlib.Path(__file__).parent.parent / "src" / "bobbytailor"
_SRC_FILES = {
    "claude_analyzer": _SRC_ROOT / "vision" / "claude_analyzer.py",
    "sheet_pass_matrix": _SRC_ROOT / "pipeline" / "sheet_pass_matrix.py",
    "takeoff_pipeline": _SRC_ROOT / "pipeline" / "takeoff_pipeline.py",
    "calculator": _SRC_ROOT / "pipeline" / "calculator.py",
    "scraper": _SRC_ROOT / "scrape" / "scraper.py",
    "pdf_analyzer": _SRC_ROOT / "pipeline" / "pdf_analyzer.py",
}


def _load(name: str):
    path = _SRC_FILES[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load real claude_analyzer (merge_passes, no API calls)
_real_ca = _load("claude_analyzer")

# Mock for analyze_drawing; real merge/accuracy helpers preserved so the
# pipeline's module-level `from bobbytailor.vision.claude_analyzer import (...)`
# binds real impls.
_CA_MOCK = MagicMock()
_CA_MOCK.merge_passes = _real_ca.merge_passes
_CA_MOCK._merge_schedule_lists = _real_ca._merge_schedule_lists
_CA_MOCK.apply_accuracy_rules = _real_ca.apply_accuracy_rules
_CA_MOCK._SCHEDULE_LEGEND_USER_HINT = _real_ca._SCHEDULE_LEGEND_USER_HINT
_CA_MOCK.analyze_drawing.return_value = {"components": [], "measurements": []}
_CA_MOCK.make_navigation_decision.return_value = {"action": "wait"}

# Bind _CA_MOCK into the spec-loaded pipeline modules ONLY: temporarily alias
# the package key while executing the spec loads, then restore. This keeps the
# session-wide sys.modules clean (the historical permanent substitution leaked
# the mock into every test module collected after this one — the 21-08/21-16
# test-order pollution class).
_PKG_CA = "bobbytailor.vision.claude_analyzer"
_prev_real_ca = sys.modules.get(_PKG_CA)
sys.modules[_PKG_CA] = _CA_MOCK
try:
    _spm = _load("sheet_pass_matrix")
    _tp = _load("takeoff_pipeline")
finally:
    if _prev_real_ca is not None:
        sys.modules[_PKG_CA] = _prev_real_ca
    else:
        sys.modules.pop(_PKG_CA, None)
TakeoffPipeline = _tp.TakeoffPipeline
sys.modules.setdefault("bobbytailor.pipeline.takeoff_pipeline", _tp)

# Load calculator (no external deps)
_calc = _load("calculator")
sys.modules.setdefault("bobbytailor.pipeline.calculator", _calc)


# ===========================================================================
# 1. Source-level bypass checks
# ===========================================================================

class TestNoPipelineBypass:
    """Neither entry point should call analyze_drawing directly."""

    def test_scraper_does_not_import_analyze_drawing(self):
        """scraper.py must not import analyze_drawing at the top level."""
        src = _SRC_FILES["scraper"].read_text()
        # Substring matches both the legacy flat form and the 21-18 package
        # form ("from bobbytailor.vision.claude_analyzer import analyze_drawing").
        assert "claude_analyzer import analyze_drawing" not in src
        assert "import analyze_drawing" not in src

    def test_pdf_analyzer_does_not_import_analyze_drawing(self):
        """pdf_analyzer.py must not import analyze_drawing."""
        src = _SRC_FILES["pdf_analyzer"].read_text()
        assert "claude_analyzer import analyze_drawing" not in src
        assert "import analyze_drawing" not in src

    def test_scraper_has_pipeline_import(self):
        """scraper.py must import TakeoffPipeline."""
        src = _SRC_FILES["scraper"].read_text()
        assert "TakeoffPipeline" in src

    def test_pdf_analyzer_has_pipeline_import(self):
        """pdf_analyzer.py must import TakeoffPipeline."""
        src = _SRC_FILES["pdf_analyzer"].read_text()
        assert "TakeoffPipeline" in src


# ===========================================================================
# 2. pdf_analyzer delegates to TakeoffPipeline.run_project
# ===========================================================================

class TestPdfAnalyzerUsesPipeline:
    """pdf_analyzer.run_pdf_analysis must call TakeoffPipeline.run_project."""

    def test_calls_run_project_not_analyze_drawing(self, tmp_path):
        """Patch TakeoffPipeline in pdf_analyzer; verify run_project is called."""
        from bobbytailor.pipeline import pdf_analyzer

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
            patch("bobbytailor.pipeline.pdf_analyzer.TakeoffPipeline", return_value=mock_pipeline),
            patch("bobbytailor.pipeline.pdf_analyzer.fitz") as mock_fitz,
            patch("bobbytailor.pipeline.pdf_analyzer._page_to_image", return_value="/tmp/a2_1.png"),
            patch("bobbytailor.pipeline.pdf_analyzer._sheet_name_from_doc", return_value="A2.1"),
            patch("bobbytailor.pipeline.pdf_analyzer.get_title_block_text", return_value="LEVEL 1 FLOOR PLAN"),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.generate_report", return_value={"report": "ok"}),
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
        from bobbytailor.pipeline import pdf_analyzer

        mock_pipeline = MagicMock()
        mock_pipeline.run_project.return_value = ([], [], "auto")

        with (
            patch("bobbytailor.pipeline.pdf_analyzer.TakeoffPipeline", return_value=mock_pipeline),
            patch("bobbytailor.pipeline.pdf_analyzer.fitz") as mock_fitz,
            patch("bobbytailor.pipeline.pdf_analyzer._page_to_image", return_value="/tmp/p.png"),
            patch("bobbytailor.pipeline.pdf_analyzer._sheet_name_from_doc", return_value="A2.1"),
            patch("bobbytailor.pipeline.pdf_analyzer.get_title_block_text", return_value=""),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.generate_report", return_value={}),
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
        from bobbytailor.pipeline import pdf_analyzer

        mock_pipeline = MagicMock()
        mock_pipeline.run_project.return_value = ([], [], "auto")

        with (
            patch("bobbytailor.pipeline.pdf_analyzer.TakeoffPipeline", return_value=mock_pipeline),
            patch("bobbytailor.pipeline.pdf_analyzer.fitz") as mock_fitz,
            patch("bobbytailor.pipeline.pdf_analyzer._page_to_image", return_value="/tmp/p.png"),
            patch("bobbytailor.pipeline.pdf_analyzer._sheet_name_from_doc", return_value="A2.1"),
            patch("bobbytailor.pipeline.pdf_analyzer.get_title_block_text", return_value="LEVEL 2 FLOOR PLAN"),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.generate_report", return_value={}),
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
            patch("bobbytailor.scrape.scraper.RunManifest") as mock_rm,
            patch("bobbytailor.scrape.scraper._pipeline", mock_pipeline),
            patch("bobbytailor.scrape.scraper.apply_estimation_tables", return_value=[]),
            patch("bobbytailor.scrape.scraper._detect_project_type", return_value="auto"),
            patch("bobbytailor.scrape.scraper.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.scrape.scraper.resolve_cross_references", return_value=[]),
            patch("bobbytailor.scrape.scraper.generate_report", return_value={"report": "ok"}),
        ):
            mock_rm.load.return_value = fake_manifest
            from bobbytailor.scrape import scraper
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
            patch("bobbytailor.scrape.scraper.RunManifest") as mock_rm,
            patch("bobbytailor.scrape.scraper._pipeline", mock_pipeline),
            patch("bobbytailor.scrape.scraper.apply_estimation_tables", return_value=[]),
            patch("bobbytailor.scrape.scraper._detect_project_type", return_value="auto"),
            patch("bobbytailor.scrape.scraper.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.scrape.scraper.resolve_cross_references", return_value=[]),
            patch("bobbytailor.scrape.scraper.generate_report", return_value={"report": "ok"}),
        ):
            mock_rm.load.return_value = fake_manifest
            from bobbytailor.scrape import scraper
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
            patch("bobbytailor.scrape.scraper.RunManifest") as mock_rm,
            patch("bobbytailor.scrape.scraper._pipeline", mock_pipeline),
            patch("bobbytailor.scrape.scraper.apply_estimation_tables", return_value=[]),
            patch("bobbytailor.scrape.scraper._detect_project_type", return_value="auto"),
            patch("bobbytailor.scrape.scraper.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.scrape.scraper.resolve_cross_references", return_value=[]),
            patch("bobbytailor.scrape.scraper.generate_report", side_effect=_mock_report),
        ):
            mock_rm.load.return_value = fake_manifest
            from bobbytailor.scrape import scraper
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
        pdf_src = _SRC_FILES["pdf_analyzer"].read_text()
        scraper_src = _SRC_FILES["scraper"].read_text()

        # pdf_analyzer uses TakeoffPipeline().run_project
        assert "run_project" in pdf_src
        assert "TakeoffPipeline" in pdf_src

        # scraper uses _pipeline.run_sheet
        assert "_pipeline.run_sheet" in scraper_src
        assert "TakeoffPipeline" in scraper_src


# ===========================================================================
# 5–8. 21-15 extensions: RunSettings / deterministic / learning parity +
#      plans-only companion isolation
# ===========================================================================

def _make_vector_pdf(path, n_lines: int = 220) -> str:
    """Write a synthetic VECTOR plan page (≥200 drawing paths → is_vector)."""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=1224, height=792)
    page.insert_text((40, 40), "FLOOR PLAN LEVEL 1")
    for i in range(n_lines):
        y = 60.0 + (i % 300) * 2.0
        page.draw_line((40, y), (1100, y))
    doc.save(str(path))
    doc.close()
    return str(path)


def _parity_settings(RunSettingsCls, **overrides):
    """A distinctive, fully explicit RunSettings for parity assertions."""
    values = dict(
        deterministic_enabled=True,
        ensemble_n=2,
        learning_enabled=True,
        budget_usd=7.77,
        verify_retry_enabled=False,
        raster_force=False,
    )
    values.update(overrides)
    return RunSettingsCls(**values)


def _fused_stub() -> dict:
    """Minimal fuse_sheet-shaped result the fusion/merge layer accepts."""
    return {
        "components": [],
        "measurements": [],
        "rooms": [],
        "schedules": [],
        "_tokens_in": 0,
        "_tokens_out": 0,
        "_cost_usd": 0.0,
    }


def _fake_scraper_manifest(sheet_name: str = "A1.1", page_id: int = 1001):
    """MagicMock RunManifest with one captured page (scraper test double)."""
    page_entry = MagicMock()
    page_entry.page_id = page_id
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


def _build_scraper_run_dir(tmp_path, sheet_name: str = "A1.1",
                           page_id: int = 1001, with_blob: bool = True):
    """Run folder with manifest.json, screenshot, and (optionally) a vector blob."""
    run_dir = tmp_path / "run_001"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"001_{sheet_name}.jpg").write_bytes(b"fake-jpg" * 200)
    if with_blob:
        blob_dir = run_dir / "blobs"
        blob_dir.mkdir(parents=True, exist_ok=True)
        _make_vector_pdf(blob_dir / f"{page_id}.pdf")
    manifest_data = {
        "project_id": 1,
        "project_name": "Parity Test",
        "folder_id": None,
        "pages": [{
            "page_id": page_id,
            "sheet_name": sheet_name,
            "screenshot_rel": f"001_{sheet_name}.jpg",
            "capture_status": "ok",
            "analysis_status": "pending",
            "source": "main",
        }],
    }
    mpath = run_dir / "manifest.json"
    mpath.write_text(json.dumps(manifest_data))
    return run_dir, mpath


class TestRunSettingsParity:
    """Both entry points construct identical RunSettings via from_env()."""

    def test_both_entry_points_receive_identical_settings(self, tmp_path):
        from bobbytailor.pipeline import pdf_analyzer
        from bobbytailor.scrape import scraper

        sentinel = _parity_settings(pdf_analyzer.RunSettings)

        # ── PDF entry point: TakeoffPipeline(settings=from_env()) ──────────
        mock_pipeline = MagicMock()
        mock_pipeline.run_project.return_value = ([], [], "auto")

        with (
            patch.object(pdf_analyzer.RunSettings, "from_env",
                         MagicMock(return_value=sentinel)),
            patch("bobbytailor.pipeline.pdf_analyzer.TakeoffPipeline",
                  return_value=mock_pipeline) as tp_ctor,
            patch("bobbytailor.pipeline.pdf_analyzer.fitz") as mock_fitz,
            patch("bobbytailor.pipeline.pdf_analyzer._page_to_image", return_value="/tmp/p.png"),
            patch("bobbytailor.pipeline.pdf_analyzer._sheet_name_from_doc", return_value="A1.1"),
            patch("bobbytailor.pipeline.pdf_analyzer.get_title_block_text", return_value="FLOOR PLAN"),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.generate_report", return_value={}),
            patch("bobbytailor.devtools.object_manifest.resolve_project_manifest", return_value=None),
            patch("bobbytailor.deterministic.plan_deterministic_legends.build_deterministic_legends",
                  return_value=[]),
        ):
            mock_doc = MagicMock()
            mock_doc.__len__ = MagicMock(return_value=1)
            mock_fitz.open.return_value = mock_doc
            pdf_analyzer.run_pdf_analysis("/fake.pdf", "Settings Parity")

        assert tp_ctor.call_args is not None
        pdf_settings = tp_ctor.call_args.kwargs.get("settings")
        assert pdf_settings is sentinel

        # ── StackCT entry point: singleton refreshed via from_env() ────────
        run_dir, mpath = _build_scraper_run_dir(tmp_path, with_blob=False)
        floor_result = {
            "_sheet_type": "floor_plan", "_sheet_name": "A1.1",
            "_passes_run": ["count", "measure"], "_skipped": False,
            "components": [], "measurements": [], "rooms": [], "schedules": [],
        }
        mock_sc_pipeline = MagicMock()
        mock_sc_pipeline.run_sheet.return_value = floor_result

        with (
            patch.object(scraper.RunSettings, "from_env",
                         MagicMock(return_value=sentinel)),
            patch("bobbytailor.scrape.scraper.RunManifest") as mock_rm,
            patch("bobbytailor.scrape.scraper._pipeline", mock_sc_pipeline),
            patch("bobbytailor.scrape.scraper.apply_estimation_tables", return_value=[]),
            patch("bobbytailor.scrape.scraper._detect_project_type", return_value="auto"),
            patch("bobbytailor.scrape.scraper.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.scrape.scraper.resolve_cross_references", return_value=[]),
            patch("bobbytailor.scrape.scraper.generate_report", return_value={"report": "ok"}),
            patch("bobbytailor.devtools.object_manifest.resolve_project_manifest", return_value=None),
            patch("bobbytailor.deterministic.plan_deterministic_legends.build_deterministic_legends_from_run_dir",
                  return_value=[]),
        ):
            mock_rm.load.return_value = _fake_scraper_manifest()
            _fresh_loop().run_until_complete(
                scraper.run_analyze_from_manifest(manifest_path_override=mpath)
            )

        # The scraper run assigned the SAME settings object to its pipeline.
        assert mock_sc_pipeline.settings is sentinel
        assert pdf_settings is mock_sc_pipeline.settings

    def test_settings_construction_is_from_env_in_both_sources(self):
        """Source-level: both entry points contain RunSettings.from_env()."""
        assert "RunSettings.from_env()" in _SRC_FILES["pdf_analyzer"].read_text()
        assert "RunSettings.from_env()" in _SRC_FILES["scraper"].read_text()


class TestDeterministicCallSiteParity:
    """A vector page fires extract_dimension_samples + fuse_sheet on BOTH paths."""

    def test_pdf_path_reaches_deterministic_call_sites(self, tmp_path):
        from bobbytailor.pipeline import pdf_analyzer

        vector_pdf = _make_vector_pdf(tmp_path / "plans.pdf")
        sentinel = _parity_settings(pdf_analyzer.RunSettings)

        dim_spy = MagicMock(return_value=[])
        fuse_spy = MagicMock(return_value=_fused_stub())
        run_sheet_globals = pdf_analyzer.TakeoffPipeline.run_sheet.__globals__

        with (
            patch.object(pdf_analyzer.RunSettings, "from_env",
                         MagicMock(return_value=sentinel)),
            patch.dict(run_sheet_globals, {
                "extract_dimension_samples": dim_spy,
                "fuse_sheet": fuse_spy,
            }),
            patch("bobbytailor.pipeline.pdf_analyzer._page_to_image",
                  return_value=str(tmp_path / "sheet.png")),
            patch("bobbytailor.pipeline.pdf_analyzer._sheet_name_from_doc", return_value="A1.1"),
            patch("bobbytailor.pipeline.pdf_analyzer.get_title_block_text",
                  return_value="FLOOR PLAN LEVEL 1"),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.generate_report", return_value={"report": "ok"}),
            patch("bobbytailor.devtools.object_manifest.resolve_project_manifest", return_value=None),
            patch("bobbytailor.deterministic.plan_deterministic_legends.build_deterministic_legends",
                  return_value=[]),
        ):
            pdf_analyzer.run_pdf_analysis(vector_pdf, "Determinism PDF")

        assert dim_spy.called, "PDF path never reached extract_dimension_samples"
        assert fuse_spy.called, "PDF path never reached fuse_sheet"

    def test_stackct_path_reaches_deterministic_call_sites(self, tmp_path):
        from bobbytailor.scrape import scraper

        run_dir, mpath = _build_scraper_run_dir(tmp_path, with_blob=True)
        sentinel = _parity_settings(scraper.RunSettings)

        dim_spy = MagicMock(return_value=[])
        fuse_spy = MagicMock(return_value=_fused_stub())
        pipeline = scraper._pipeline  # real TakeoffPipeline singleton
        run_sheet_globals = type(pipeline).run_sheet.__globals__
        prior_settings = pipeline.settings

        try:
            with (
                patch.object(scraper.RunSettings, "from_env",
                             MagicMock(return_value=sentinel)),
                patch.dict(run_sheet_globals, {
                    "extract_dimension_samples": dim_spy,
                    "fuse_sheet": fuse_spy,
                }),
                patch("bobbytailor.scrape.scraper.RunManifest") as mock_rm,
                patch("bobbytailor.scrape.scraper.apply_estimation_tables", return_value=[]),
                patch("bobbytailor.scrape.scraper._detect_project_type", return_value="auto"),
                patch("bobbytailor.scrape.scraper.resolve_spec_lookups", return_value=[]),
                patch("bobbytailor.scrape.scraper.resolve_cross_references", return_value=[]),
                patch("bobbytailor.scrape.scraper.generate_report", return_value={"report": "ok"}),
                patch("bobbytailor.devtools.object_manifest.resolve_project_manifest",
                      return_value=None),
                patch("bobbytailor.deterministic.plan_deterministic_legends."
                      "build_deterministic_legends_from_run_dir",
                      return_value=[]),
            ):
                mock_rm.load.return_value = _fake_scraper_manifest()
                _fresh_loop().run_until_complete(
                    scraper.run_analyze_from_manifest(
                        manifest_path_override=mpath
                    )
                )
        finally:
            pipeline.settings = prior_settings

        assert dim_spy.called, "StackCT path never reached extract_dimension_samples"
        assert fuse_spy.called, "StackCT path never reached fuse_sheet"

    def test_stackct_blob_threads_pdf_kwargs_into_run_sheet(self, tmp_path):
        """A retained blob makes the scraper pass pdf_path/page_index to run_sheet."""
        from bobbytailor.scrape import scraper

        run_dir, mpath = _build_scraper_run_dir(tmp_path, with_blob=True)
        floor_result = {
            "_sheet_type": "floor_plan", "_sheet_name": "A1.1",
            "_passes_run": ["count", "measure"], "_skipped": False,
            "components": [], "measurements": [], "rooms": [], "schedules": [],
        }
        mock_pipeline = MagicMock()
        mock_pipeline.run_sheet.return_value = floor_result

        with (
            patch("bobbytailor.scrape.scraper.RunManifest") as mock_rm,
            patch("bobbytailor.scrape.scraper._pipeline", mock_pipeline),
            patch("bobbytailor.scrape.scraper.apply_estimation_tables", return_value=[]),
            patch("bobbytailor.scrape.scraper._detect_project_type", return_value="auto"),
            patch("bobbytailor.scrape.scraper.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.scrape.scraper.resolve_cross_references", return_value=[]),
            patch("bobbytailor.scrape.scraper.generate_report", return_value={"report": "ok"}),
            patch("bobbytailor.devtools.object_manifest.resolve_project_manifest", return_value=None),
            patch("bobbytailor.deterministic.plan_deterministic_legends."
                  "build_deterministic_legends_from_run_dir", return_value=[]),
        ):
            mock_rm.load.return_value = _fake_scraper_manifest()
            _fresh_loop().run_until_complete(
                scraper.run_analyze_from_manifest(manifest_path_override=mpath)
            )

        kwargs = mock_pipeline.run_sheet.call_args.kwargs
        assert kwargs.get("pdf_path", "").endswith("blobs/1001.pdf")
        assert kwargs.get("page_index") == 0

    def test_pdf_path_threads_pdf_kwargs_into_run_project_pages(self):
        """pdf_analyzer page dicts carry pdf_path/page_index (deterministic input)."""
        src = _SRC_FILES["pdf_analyzer"].read_text()
        assert '"pdf_path": pdf_path' in src
        assert '"page_index": i' in src


class TestBudgetParity:
    """21-REVIEW WR-05: ONE run-level BudgetGuard across every sheet on the
    StackCT path — never a fresh per-sheet guard (V3-PROD-02 hard cap)."""

    def _two_page_run(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir(parents=True, exist_ok=True)
        pages = []
        page_json = []
        for i, name in enumerate(("A1.1", "A1.2"), start=1):
            rel = f"00{i}_{name}.jpg"
            (run_dir / rel).write_bytes(b"fake-jpg" * 200)
            entry = MagicMock()
            entry.page_id = 1000 + i
            entry.sheet_name = name
            entry.capture_status = "ok"
            entry.analysis_status = "pending"
            entry.screenshot_rel = rel
            pages.append(entry)
            page_json.append({
                "page_id": 1000 + i, "sheet_name": name,
                "screenshot_rel": rel, "capture_status": "ok",
                "analysis_status": "pending", "source": "main",
            })
        mpath = run_dir / "manifest.json"
        mpath.write_text(json.dumps({
            "project_id": 1, "project_name": "Budget Parity",
            "folder_id": None, "pages": page_json,
        }))
        fake_manifest = MagicMock()
        fake_manifest.project_name = "Budget Parity"
        fake_manifest.folder_id = None
        fake_manifest.pages = pages
        fake_manifest.save = MagicMock()
        return mpath, fake_manifest

    def test_analyze_from_manifest_threads_one_run_budget(self, tmp_path):
        from bobbytailor.pipeline.takeoff_pipeline import BudgetGuard
        from bobbytailor.scrape import scraper

        mpath, fake_manifest = self._two_page_run(tmp_path)

        def fresh_result(*args, **kwargs):
            return {
                "_sheet_type": "floor_plan",
                "_sheet_name": kwargs.get("sheet_name") or (args[1] if len(args) > 1 else "?"),
                "_passes_run": ["count", "measure"], "_skipped": False,
                "components": [], "measurements": [], "rooms": [], "schedules": [],
            }

        mock_pipeline = MagicMock()
        mock_pipeline.run_sheet.side_effect = fresh_result

        with (
            patch("bobbytailor.scrape.scraper.RunManifest") as mock_rm,
            patch("bobbytailor.scrape.scraper._pipeline", mock_pipeline),
            patch("bobbytailor.scrape.scraper.apply_estimation_tables", return_value=[]),
            patch("bobbytailor.scrape.scraper._detect_project_type", return_value="auto"),
            patch("bobbytailor.scrape.scraper.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.scrape.scraper.resolve_cross_references", return_value=[]),
            patch("bobbytailor.scrape.scraper.generate_report", return_value={"report": "ok"}),
            patch("bobbytailor.devtools.object_manifest.resolve_project_manifest", return_value=None),
            patch("bobbytailor.deterministic.plan_deterministic_legends."
                  "build_deterministic_legends_from_run_dir", return_value=[]),
        ):
            mock_rm.load.return_value = fake_manifest
            _fresh_loop().run_until_complete(
                scraper.run_analyze_from_manifest(manifest_path_override=mpath)
            )

        calls = mock_pipeline.run_sheet.call_args_list
        assert len(calls) == 2, f"expected 2 run_sheet calls, got {len(calls)}"
        budgets = [c.kwargs.get("budget") for c in calls]
        assert all(isinstance(b, BudgetGuard) for b in budgets), (
            f"every run_sheet call must receive the run-level BudgetGuard, got {budgets}"
        )
        assert budgets[0] is budgets[1], (
            "each sheet received a DIFFERENT BudgetGuard — the per-run cap "
            "multiplies by sheet count (WR-05 regression)"
        )

    def test_run_project_scrape_source_threads_run_budget(self):
        """Source-level: both scraper entry functions construct one run-level
        guard and pass budget=run_budget into run_sheet (incl. linked pass)."""
        src = _SRC_FILES["scraper"].read_text()
        assert src.count("run_budget = BudgetGuard(") == 2, (
            "run_project_scrape AND run_analyze_from_manifest must each "
            "construct one run-level BudgetGuard"
        )
        assert src.count("budget=run_budget") >= 3, (
            "main pass, analyze-only pass, and linked-sheet pass must all "
            "charge the run-level guard"
        )


class TestLearningCallSiteParity:
    """The learning seam is shared identically by both entry points (21-16)."""

    def test_learning_seam_exists_and_is_shared(self):
        from bobbytailor.pipeline import pdf_analyzer
        from bobbytailor.scrape import scraper

        # RunSettings — the seam both paths construct — carries the learning
        # toggle for the 21-16 runtime retrieval.
        for mod in (pdf_analyzer, scraper):
            settings = mod.RunSettings.from_env()
            assert hasattr(settings, "learning_enabled"), mod.__name__

        # Once the retrieval hook lands on the shared pipeline module (21-16),
        # both entry points MUST resolve the exact same callable — the shared
        # TakeoffPipeline.run_sheet is the single call site. hasattr-guarded so
        # this test strengthens automatically after 21-16.
        pdf_tp_mod = sys.modules[pdf_analyzer.TakeoffPipeline.__module__]
        scr_tp_mod = sys.modules[type(scraper._pipeline).__module__]
        for hook in (
            "retrieve_learning_hints",
            "apply_learning_hints",
            "learning_retrieval",
        ):
            assert hasattr(pdf_tp_mod, hook) == hasattr(scr_tp_mod, hook), hook
            if hasattr(pdf_tp_mod, hook):
                assert getattr(pdf_tp_mod, hook) is getattr(scr_tp_mod, hook), hook


class TestCompanionIsolation:
    """LOCKED: the production path can never see a sibling take-off PDF."""

    def test_sibling_takeoff_pdf_never_opened(self, tmp_path):
        import fitz as real_fitz
        from bobbytailor.pipeline import pdf_analyzer
        import bobbytailor.devtools.companion_takeoff as devtools_companion

        # Plans PDF (the ONLY legitimate pipeline input)
        plans = tmp_path / "Isolation Project-Plans.pdf"
        _make_vector_pdf(plans, n_lines=10)

        # Ground-truth sibling the production path must NEVER read
        takeoff = tmp_path / "Isolation Project-Take offs.pdf"
        doc = real_fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((30, 40), "Bollards")
        page.insert_text((30, 60), "28 EA")
        doc.save(str(takeoff))
        doc.close()

        opened: list = []
        real_open = real_fitz.open

        def spying_open(*args, **kwargs):
            if args:
                opened.append(str(args[0]))
            return real_open(*args, **kwargs)

        mock_pipeline = MagicMock()
        mock_pipeline.run_project.return_value = ([], [], "auto")

        discovery_spy = MagicMock(
            wraps=devtools_companion.find_companion_takeoff_pdf
        )

        with (
            # Global fitz.open spy — catches ANY module reading the sibling.
            patch.object(real_fitz, "open", spying_open),
            patch.object(devtools_companion, "find_companion_takeoff_pdf",
                         discovery_spy),
            patch("bobbytailor.pipeline.pdf_analyzer.TakeoffPipeline", return_value=mock_pipeline),
            patch("bobbytailor.pipeline.pdf_analyzer._page_to_image",
                  return_value=str(tmp_path / "p.png")),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.generate_report", return_value={"report": "ok"}),
            patch("bobbytailor.devtools.object_manifest.resolve_project_manifest", return_value=None),
        ):
            # NOTE: plan_deterministic_legends stays REAL — the full plans-only
            # legends flow runs and must still never touch the sibling.
            pdf_analyzer.run_pdf_analysis(str(plans), "Isolation Project")

        assert opened, "expected the plans PDF to be opened via fitz"
        assert all("Take offs" not in p for p in opened), (
            f"PRODUCTION PATH READ THE GROUND-TRUTH TAKE-OFF: {opened}"
        )
        discovery_spy.assert_not_called()

    def test_manifest_discovery_never_runs_on_pdf_path(self, tmp_path, monkeypatch):
        """21-REVIEW WR-08: a discoverable manifests/default.json (catch-all)
        must never join a production PDF run — explicit manifest_path is the
        only manifest input (plans-only LOCKED contract)."""
        import bobbytailor.devtools.object_manifest as om
        from bobbytailor.pipeline import pdf_analyzer

        plans = tmp_path / "Isolation Project-Plans.pdf"
        _make_vector_pdf(plans, n_lines=10)

        # Plant a catch-all default manifest discoverable relative to CWD.
        monkeypatch.chdir(tmp_path)
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "default.json").write_text(
            json.dumps([{"name": "Decoy Manifest Item", "unit": "EA"}])
        )
        # Sanity: the devtools finder WOULD discover it.
        assert om.discover_manifest_path("Isolation Project") is not None

        discovery_spy = MagicMock(wraps=om.discover_manifest_path)
        mock_pipeline = MagicMock()
        mock_pipeline.run_project.return_value = ([], [], "auto")

        with (
            patch.object(om, "discover_manifest_path", discovery_spy),
            patch("bobbytailor.pipeline.pdf_analyzer.TakeoffPipeline",
                  return_value=mock_pipeline),
            patch("bobbytailor.pipeline.pdf_analyzer._page_to_image",
                  return_value=str(tmp_path / "p.png")),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_cross_references", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.pipeline.pdf_analyzer.generate_report", return_value={"report": "ok"}),
            patch("bobbytailor.deterministic.plan_deterministic_legends."
                  "build_deterministic_legends", return_value=[]),
        ):
            # NOTE: resolve_project_manifest stays REAL — the production
            # call site itself must refuse discovery.
            pdf_analyzer.run_pdf_analysis(str(plans), "Isolation Project")

        discovery_spy.assert_not_called()
        assert mock_pipeline.run_project.call_args.kwargs.get("manifest") is None

    def test_manifest_discovery_never_runs_on_scraper_path(self, tmp_path, monkeypatch):
        """WR-08 parity: the StackCT analyze path is production too — no
        manifests/-dir discovery there either."""
        import bobbytailor.devtools.object_manifest as om
        from bobbytailor.scrape import scraper

        run_dir, mpath = _build_scraper_run_dir(tmp_path, with_blob=False)

        monkeypatch.chdir(tmp_path)
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        (manifests_dir / "default.json").write_text(
            json.dumps([{"name": "Decoy Manifest Item", "unit": "EA"}])
        )
        assert om.discover_manifest_path("Parity Test") is not None

        discovery_spy = MagicMock(wraps=om.discover_manifest_path)
        floor_result = {
            "_sheet_type": "floor_plan", "_sheet_name": "A1.1",
            "_passes_run": ["count", "measure"], "_skipped": False,
            "components": [], "measurements": [], "rooms": [], "schedules": [],
        }
        mock_pipeline = MagicMock()
        mock_pipeline.run_sheet.return_value = floor_result

        with (
            patch.object(om, "discover_manifest_path", discovery_spy),
            patch("bobbytailor.scrape.scraper.RunManifest") as mock_rm,
            patch("bobbytailor.scrape.scraper._pipeline", mock_pipeline),
            patch("bobbytailor.scrape.scraper.apply_estimation_tables", return_value=[]),
            patch("bobbytailor.scrape.scraper._detect_project_type", return_value="auto"),
            patch("bobbytailor.scrape.scraper.resolve_spec_lookups", return_value=[]),
            patch("bobbytailor.scrape.scraper.resolve_cross_references", return_value=[]),
            patch("bobbytailor.scrape.scraper.generate_report", return_value={"report": "ok"}),
            patch("bobbytailor.deterministic.plan_deterministic_legends."
                  "build_deterministic_legends_from_run_dir", return_value=[]),
        ):
            mock_rm.load.return_value = _fake_scraper_manifest()
            _fresh_loop().run_until_complete(
                scraper.run_analyze_from_manifest(manifest_path_override=mpath)
            )

        discovery_spy.assert_not_called()

    def test_companion_discovery_absent_from_production_namespaces(self):
        from bobbytailor.pipeline import pdf_analyzer
        from bobbytailor.scrape import scraper

        assert not hasattr(pdf_analyzer, "find_companion_takeoff_pdf")
        assert not hasattr(scraper, "find_companion_takeoff_pdf")
        assert not hasattr(pdf_analyzer, "extract_legend_schedules")

        # Source-level: companion discovery is confined to devtools/ + scripts/.
        for name in ("pdf_analyzer", "scraper"):
            src = _SRC_FILES[name].read_text()
            assert "find_companion_takeoff_pdf" not in src, name
            assert "companion_takeoff" not in src.replace(
                "companion_takeoff_legend", ""
            ), name
