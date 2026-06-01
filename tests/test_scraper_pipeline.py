"""
End-to-end integration tests for the full scraper pipeline.

Covers:
- Full pipeline: capture → analyze → report (3 fake pages, Claude mocked)
- Partial failure: one sheet with a slash in its name still produces a report
- analyze_only: re-runs Claude from an existing manifest without a browser
- REUSE_SCREENSHOTS: copies from cache dir instead of downloading
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from capture_manifest import PageEntry, RunManifest, manifest_path


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------

def _fake_download(project_id, page_id, dest_path):
    """Write a plausible-sized fake image so size checks pass."""
    p = Path(dest_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"PNG_DATA" * 300)  # 2 400 bytes > 1 000 threshold
    return True


def _fake_analyze(image_path: str, sheet_name: str) -> dict:
    return {
        "measurements": [{"label": "width", "value": 10, "unit": "ft"}],
        "components": [{"type": "door", "count": 2}],
        "rooms": [],
        "schedules": [],
        "_tokens_in": 120,
        "_tokens_out": 60,
        "_cost_usd": 0.0012,
        "_model_used": "claude-haiku",
    }


def _make_pages(page_ids: list[int], names: list[str] | None = None) -> list[dict]:
    if names is None:
        names = [f"Sheet {pid}" for pid in page_ids]
    return [{"page_id": pid, "sheet_name": name} for pid, name in zip(page_ids, names)]


def _write_fake_screenshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"JPEG_DATA" * 300)  # > 1 000 bytes


def _make_run_manifest(
    tmp_path: Path,
    pages: list[dict],
    *,
    project_name: str = "TestProject",
    analysis_status: str = "pending",
) -> tuple[Path, Path]:
    """Create a run directory with manifest.json + dummy screenshots."""
    run_dir = tmp_path / "run_dir"
    run_dir.mkdir(parents=True, exist_ok=True)
    mpath = manifest_path(run_dir)

    manifest = RunManifest(project_id=1, project_name=project_name, folder_id=None)
    for i, p in enumerate(pages, 1):
        page_id = p["page_id"]
        sheet_name = p.get("sheet_name", f"Sheet {page_id}")
        rel = f"{i:03d}_{sheet_name.replace(' ', '_').replace('/', '-')}.jpg"
        entry = PageEntry(
            page_id=page_id,
            sheet_name=sheet_name,
            screenshot_rel=rel,
            capture_status="ok",
            analysis_status=analysis_status,
        )
        manifest.pages.append(entry)
        _write_fake_screenshot(run_dir / rel)

    manifest.save(mpath)
    return run_dir, mpath


def _common_patches(n_pages: int = 1):
    """Return list of context managers patching all external calls."""
    return [
        patch("scraper.analyze_drawing", side_effect=_fake_analyze),
        patch("scraper.apply_estimation_tables", return_value=[]),
        patch("scraper.resolve_cross_references", return_value={}),
        patch("scraper.resolve_spec_lookups", return_value=[]),
        patch("scraper.generate_report", return_value={
            "sheets_processed": n_pages,
            "total_line_items": 0,
            "total_calculated_items": 0,
        }),
    ]


def _build_mock_browser(pages: list[dict]):
    mock_browser = MagicMock()
    mock_browser.start = AsyncMock(return_value=None)
    mock_browser.login = AsyncMock(return_value=True)
    mock_browser.get_all_page_ids = AsyncMock(return_value=pages)
    mock_browser.get_page_ids_in_folder = AsyncMock(return_value=pages)
    mock_browser.download_drawing_image = AsyncMock(side_effect=_fake_download)
    mock_browser.close = AsyncMock(return_value=None)
    mock_browser.page = None
    return mock_browser


# ---------------------------------------------------------------------------
# TestFullPipeline — capture → analyze → report with 3 fake pages
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """Full run_project_scrape with 3 pages; all Claude calls mocked."""

    def _run(self, pages: list[dict], tmp_path: Path) -> dict:
        mock_browser = _build_mock_browser(pages)
        patches = _common_patches(len(pages))

        with patch("scraper.StackCTBrowser", return_value=mock_browser), \
             patch("scraper.SCREENSHOTS_DIR", str(tmp_path)), \
             patch("scraper.REUSE_SCREENSHOTS", False), \
             patch("scraper.find_screenshot_paths", return_value={}), \
             patches[0], patches[1], patches[2], patches[3], patches[4]:

            from scraper import run_project_scrape
            return asyncio.run(run_project_scrape(
                project_id=1,
                project_name="IntegTest",
            ))

    def test_three_pages_no_error(self, tmp_path: Path):
        """Full pipeline with 3 pages returns a result without an error key."""
        pages = _make_pages([101, 102, 103])
        result = self._run(pages, tmp_path)
        assert "error" not in result, f"Unexpected error: {result.get('error')}"

    def test_three_pages_report_contains_sheets_processed(self, tmp_path: Path):
        """generate_report result is propagated into the scrape return value."""
        pages = _make_pages([101, 102, 103])
        result = self._run(pages, tmp_path)
        assert result.get("sheets_processed") == 3

    def test_manifest_written_to_run_folder(self, tmp_path: Path):
        """manifest.json must be created inside the timestamped run dir."""
        pages = _make_pages([10, 20, 30])
        self._run(pages, tmp_path)
        manifests = list(tmp_path.rglob("manifest.json"))
        assert manifests, "manifest.json was not written to the run folder"

    def test_analyze_called_once_per_page(self, tmp_path: Path):
        """analyze_drawing must be invoked exactly once per successfully captured page."""
        pages = _make_pages([1, 2, 3])
        call_count = {"n": 0}

        def counting_analyze(image_path, sheet_name):
            call_count["n"] += 1
            return _fake_analyze(image_path, sheet_name)

        mock_browser = _build_mock_browser(pages)
        patches = _common_patches(len(pages))

        with patch("scraper.StackCTBrowser", return_value=mock_browser), \
             patch("scraper.SCREENSHOTS_DIR", str(tmp_path)), \
             patch("scraper.REUSE_SCREENSHOTS", False), \
             patch("scraper.find_screenshot_paths", return_value={}), \
             patch("scraper.analyze_drawing", side_effect=counting_analyze), \
             patches[1], patches[2], patches[3], patches[4]:

            from scraper import run_project_scrape
            asyncio.run(run_project_scrape(project_id=1, project_name="IntegTest"))

        assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# TestPartialFailure — 1 bad-filename sheet still produces report
# ---------------------------------------------------------------------------

class TestPartialFailure:
    """One sheet with a slash in its name; scraper must not crash and must report."""

    def test_slash_in_sheet_name_does_not_crash(self, tmp_path: Path):
        """A sheet named 'A/B-Plan' is sanitized and the run completes."""
        pages = _make_pages(
            [201, 202, 203],
            names=["Normal Sheet", "A/B-Plan", "Another Sheet"],
        )
        mock_browser = _build_mock_browser(pages)
        patches = _common_patches(3)

        with patch("scraper.StackCTBrowser", return_value=mock_browser), \
             patch("scraper.SCREENSHOTS_DIR", str(tmp_path)), \
             patch("scraper.REUSE_SCREENSHOTS", False), \
             patch("scraper.find_screenshot_paths", return_value={}), \
             patches[0], patches[1], patches[2], patches[3], patches[4]:

            from scraper import run_project_scrape
            result = asyncio.run(run_project_scrape(
                project_id=2,
                project_name="SlashTest",
            ))

        assert "error" not in result, f"Unexpected error: {result.get('error')}"

    def test_partial_failure_still_produces_report(self, tmp_path: Path):
        """
        3 pages where 1 capture fails via download returning False.
        Report must still be generated from the 2 successful sheets.
        """
        pages = _make_pages([301, 302, 303])

        download_call = {"n": 0}

        def _partial_download(project_id, page_id, dest_path):
            download_call["n"] += 1
            if page_id == 302:
                return False  # simulate capture failure on middle sheet
            return _fake_download(project_id, page_id, dest_path)

        mock_browser = _build_mock_browser(pages)
        mock_browser.download_drawing_image = AsyncMock(side_effect=_partial_download)
        mock_browser.page = None  # prevent navigation-decision fallback

        with patch("scraper.StackCTBrowser", return_value=mock_browser), \
             patch("scraper.SCREENSHOTS_DIR", str(tmp_path)), \
             patch("scraper.REUSE_SCREENSHOTS", False), \
             patch("scraper.find_screenshot_paths", return_value={}), \
             patch("scraper.analyze_drawing", side_effect=_fake_analyze), \
             patch("scraper.apply_estimation_tables", return_value=[]), \
             patch("scraper.resolve_cross_references", return_value={}), \
             patch("scraper.resolve_spec_lookups", return_value=[]), \
             patch("scraper.generate_report", return_value={
                 "sheets_processed": 2,
                 "total_line_items": 0,
                 "total_calculated_items": 0,
             }):

            from scraper import run_project_scrape
            result = asyncio.run(run_project_scrape(
                project_id=3,
                project_name="PartialTest",
            ))

        # Should NOT error with all_sheets_failed since 2 out of 3 succeeded
        assert result.get("error") != "all_sheets_failed", (
            "Partial failure should still produce a report for successful sheets"
        )
        assert result.get("sheets_processed") == 2


# ---------------------------------------------------------------------------
# TestAnalyzeOnly — run_analyze_from_manifest without browser
# ---------------------------------------------------------------------------

class TestAnalyzeOnlyFromManifest:
    """analyze_only path reads manifest, skips browser, calls Claude per page."""

    def _run_analyze(self, run_dir: Path, **kwargs) -> dict:
        patches = _common_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            return asyncio.run(run_analyze_from_manifest(
                screenshots_dir=run_dir, **kwargs
            ))

    def test_analyze_only_produces_report(self, tmp_path: Path):
        """analyze_only from a valid manifest returns no error."""
        pages = _make_pages([10, 20, 30])
        run_dir, _ = _make_run_manifest(tmp_path, pages)
        result = self._run_analyze(run_dir)
        assert "error" not in result, f"Unexpected error: {result.get('error')}"

    def test_analyze_only_does_not_start_browser(self, tmp_path: Path):
        """StackCTBrowser must never be instantiated during analyze-only."""
        pages = _make_pages([10, 20])
        run_dir, _ = _make_run_manifest(tmp_path, pages)

        mock_browser_cls = MagicMock()
        patches = _common_patches(len(pages))

        with patch("scraper.StackCTBrowser", mock_browser_cls), \
             patches[0], patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=run_dir))

        mock_browser_cls.assert_not_called()

    def test_analyze_only_calls_claude_for_pending_pages(self, tmp_path: Path):
        """All pending pages must invoke analyze_drawing exactly once each."""
        pages = _make_pages([10, 20, 30])
        run_dir, _ = _make_run_manifest(tmp_path, pages, analysis_status="pending")

        call_count = {"n": 0}

        def counting_analyze(image_path, sheet_name):
            call_count["n"] += 1
            return _fake_analyze(image_path, sheet_name)

        patches = _common_patches(3)
        with patch("scraper.analyze_drawing", side_effect=counting_analyze), \
             patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=run_dir))

        assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# TestReuseScreenshots — REUSE_SCREENSHOTS copies from cache instead of downloading
# ---------------------------------------------------------------------------

class TestReuseScreenshots:
    """REUSE_SCREENSHOTS=True must copy cached files; browser.download_drawing_image NOT called."""

    def test_reuse_skips_download(self, tmp_path: Path):
        """When cache map has all pages, download_drawing_image is never called."""
        pages = _make_pages([1, 2, 3])

        # Build a fake cache dir with pre-existing screenshots
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cache_map: dict[int, Path] = {}
        for p in pages:
            pid = p["page_id"]
            cached = cache_dir / f"cached_{pid}.jpg"
            cached.write_bytes(b"CACHED_IMAGE" * 300)  # > 1 000 bytes
            cache_map[pid] = cached

        mock_browser = _build_mock_browser(pages)
        patches = _common_patches(len(pages))

        with patch("scraper.StackCTBrowser", return_value=mock_browser), \
             patch("scraper.SCREENSHOTS_DIR", str(tmp_path / "runs")), \
             patch("scraper.REUSE_SCREENSHOTS", True), \
             patch("scraper.find_screenshot_paths", return_value=cache_map), \
             patches[0], patches[1], patches[2], patches[3], patches[4]:

            from scraper import run_project_scrape
            result = asyncio.run(run_project_scrape(
                project_id=1,
                project_name="ReuseTest",
            ))

        # download_drawing_image must NOT have been called for any cached page
        mock_browser.download_drawing_image.assert_not_called()
        assert "error" not in result, f"Unexpected error: {result.get('error')}"

    def test_reuse_false_always_downloads(self, tmp_path: Path):
        """When REUSE_SCREENSHOTS=False, find_screenshot_paths is never called."""
        pages = _make_pages([10, 20])
        mock_browser = _build_mock_browser(pages)
        patches = _common_patches(len(pages))

        with patch("scraper.StackCTBrowser", return_value=mock_browser), \
             patch("scraper.SCREENSHOTS_DIR", str(tmp_path)), \
             patch("scraper.REUSE_SCREENSHOTS", False), \
             patch("scraper.find_screenshot_paths") as mock_find, \
             patches[0], patches[1], patches[2], patches[3], patches[4]:

            from scraper import run_project_scrape
            asyncio.run(run_project_scrape(project_id=1, project_name="NoReuseTest"))

        mock_find.assert_not_called()

    def test_reuse_copies_file_to_run_dir(self, tmp_path: Path):
        """Cached screenshot is physically copied to the run directory."""
        pages = _make_pages([42])
        page_id = 42

        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        cached = cache_dir / f"cached_{page_id}.jpg"
        cached.write_bytes(b"CACHED_CONTENT" * 300)
        cache_map = {page_id: cached}

        mock_browser = _build_mock_browser(pages)
        patches = _common_patches(1)

        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()

        with patch("scraper.StackCTBrowser", return_value=mock_browser), \
             patch("scraper.SCREENSHOTS_DIR", str(runs_dir)), \
             patch("scraper.REUSE_SCREENSHOTS", True), \
             patch("scraper.find_screenshot_paths", return_value=cache_map), \
             patches[0], patches[1], patches[2], patches[3], patches[4]:

            from scraper import run_project_scrape
            asyncio.run(run_project_scrape(project_id=1, project_name="CopyTest"))

        # The run folder should contain a .jpg file (copied from cache)
        copied_files = list(runs_dir.rglob("*.jpg"))
        assert copied_files, "No .jpg file found in run dir — cache copy did not happen"
        content = copied_files[0].read_bytes()
        assert content == b"CACHED_CONTENT" * 300, "Copied file contents do not match source"
