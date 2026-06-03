"""
Integration test: verifies that run_project_scrape completes all screenshot
captures (phase="capturing") before issuing any Claude analyze calls
(phase="analyzing"), and that manifest.json is written to the run folder.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pages(page_ids: list[int]) -> list[dict]:
    return [{"page_id": pid, "sheet_name": f"Sheet {pid}"} for pid in page_ids]


def _fake_download(project_id, page_id, dest_path):
    """Write a plausible-sized PNG to dest_path so size checks pass."""
    p = Path(dest_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"PNG_DATA" * 250)  # 2000 bytes > 1000 threshold
    return True


def _fake_analyze(image_path: str, sheet_name: str) -> dict:
    return {
        "measurements": [{"label": "m1", "value": 1, "unit": "ft"}],
        "components": [],
        "rooms": [],
        "schedules": [],
        "_tokens_in": 100,
        "_tokens_out": 50,
        "_cost_usd": 0.001,
        "_model_used": "claude-haiku",
    }


# ---------------------------------------------------------------------------
# Two-phase ordering test
# ---------------------------------------------------------------------------

class TestTwoPhaseOrdering:
    """
    Verifies that all progress_callback(phase="capturing") calls fire
    before any progress_callback(phase="analyzing") call.
    """

    def _run(self, pages: list[dict], tmp_path: Path) -> list[str]:
        """Run scraper with mocked browser and external calls; return phase log."""
        phases: list[str] = []

        def progress_callback(idx, total, sheet_name, phase=None, **kw):
            if phase:
                phases.append(phase)

        # Build a mock browser
        mock_browser = MagicMock()
        mock_browser.start = AsyncMock(return_value=None)
        mock_browser.login = AsyncMock(return_value=True)
        mock_browser.get_all_page_ids = AsyncMock(return_value=pages)
        mock_browser.get_page_ids_in_folder = AsyncMock(return_value=pages)
        mock_browser.download_drawing_image = AsyncMock(side_effect=_fake_download)
        mock_browser.close = AsyncMock(return_value=None)
        mock_browser.page = None

        with patch("scraper.StackCTBrowser", return_value=mock_browser), \
             patch("scraper.SCREENSHOTS_DIR", str(tmp_path)), \
             patch("scraper.REUSE_SCREENSHOTS", False), \
             patch("scraper.find_screenshot_paths", return_value={}), \
             patch("scraper._pipeline.run_sheet", side_effect=_fake_analyze), \
             patch("scraper.apply_estimation_tables", return_value=[]), \
             patch("scraper.resolve_cross_references", return_value={}), \
             patch("scraper.resolve_spec_lookups", return_value=[]), \
             patch("scraper.generate_report", return_value={
                 "sheets_processed": len(pages),
                 "total_line_items": 0,
                 "total_calculated_items": 0,
             }):
            from scraper import run_project_scrape
            asyncio.run(run_project_scrape(
                project_id=1,
                project_name="TestProject",
                progress_callback=progress_callback,
            ))

        return phases

    def test_all_capturing_before_analyzing_single_page(self, tmp_path: Path):
        pages = _make_pages([101])
        phases = self._run(pages, tmp_path)

        capturing = [i for i, p in enumerate(phases) if p == "capturing"]
        analyzing = [i for i, p in enumerate(phases) if p == "analyzing"]

        assert capturing, "Expected at least one 'capturing' phase callback"
        assert analyzing, "Expected at least one 'analyzing' phase callback"
        assert max(capturing) < min(analyzing), (
            "All 'capturing' phases must finish before any 'analyzing' phase. "
            f"Got phases: {phases}"
        )

    def test_all_capturing_before_analyzing_multi_page(self, tmp_path: Path):
        """Three-sheet run: all captures land before Claude starts."""
        pages = _make_pages([10, 20, 30])
        phases = self._run(pages, tmp_path)

        capturing = [i for i, p in enumerate(phases) if p == "capturing"]
        analyzing = [i for i, p in enumerate(phases) if p == "analyzing"]

        # Setup steps (browser/login/discover/start) also emit phase="capturing"
        assert len(capturing) >= 3, f"Expected ≥3 capturing callbacks, got: {capturing}"
        assert len(analyzing) >= 3, f"Expected ≥3 analyzing callbacks, got: {analyzing}"
        assert max(capturing) < min(analyzing), (
            f"Phases out of order: {phases}"
        )

    def test_manifest_json_created_in_run_folder(self, tmp_path: Path):
        """manifest.json must exist inside the run folder after completion."""
        pages = _make_pages([55, 66])
        self._run(pages, tmp_path)

        run_dirs = [d for d in tmp_path.iterdir() if d.is_dir()]
        assert run_dirs, "Expected a run folder to be created"
        manifests = list(tmp_path.rglob("manifest.json"))
        assert manifests, "manifest.json was not written to run folder"

    def test_capturing_phase_count_matches_page_count(self, tmp_path: Path):
        """One 'capturing' callback per page."""
        pages = _make_pages([1, 2, 3, 4])
        phases = self._run(pages, tmp_path)

        capturing_count = phases.count("capturing")
        assert capturing_count >= len(pages), (
            f"Expected ≥{len(pages)} capturing callbacks (incl. setup), got {capturing_count}"
        )
