"""
Tests for run_analyze_from_manifest() — analyze-only pass from existing manifest.

Verifies:
- Analyze-only run produces a report without calling browser.start()
- Pages with analysis_status='ok' are skipped (loaded from cache)
- Pages with analysis_status='failed'/'pending' are re-analyzed
- force=True re-analyzes all pages regardless of status
- Missing screenshot is handled gracefully (marked failed, run continues)
- Missing manifest returns error dict, no exception
- Analysis cache JSON written beside screenshot on success
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from capture_manifest import PageEntry, RunManifest, manifest_path


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

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


def _write_fake_screenshot(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"JPEG_DATA" * 300)  # >1 000 bytes


def _make_manifest(
    tmp_path: Path,
    pages: list[dict],
    *,
    project_name: str = "TestProject",
) -> tuple[Path, Path]:
    """
    Create a run directory with manifest.json and dummy screenshots.

    Returns (screenshots_dir, mpath).
    Each dict in *pages* may contain:
        page_id, sheet_name, capture_status, analysis_status, write_screenshot
    """
    screenshots_dir = tmp_path / "run_dir"
    screenshots_dir.mkdir()
    mpath = manifest_path(screenshots_dir)

    manifest = RunManifest(
        project_id=1,
        project_name=project_name,
        folder_id=None,
    )
    for i, p in enumerate(pages, 1):
        page_id = p.get("page_id", i * 10)
        sheet_name = p.get("sheet_name", f"Sheet {page_id}")
        rel = f"{i:03d}_{sheet_name.replace(' ', '_')}.jpg"
        entry = PageEntry(
            page_id=page_id,
            sheet_name=sheet_name,
            screenshot_rel=rel,
            capture_status=p.get("capture_status", "ok"),
            analysis_status=p.get("analysis_status", "pending"),
        )
        manifest.pages.append(entry)
        if p.get("write_screenshot", True) and entry.capture_status == "ok":
            _write_fake_screenshot(screenshots_dir / rel)

    manifest.save(mpath)
    return screenshots_dir, mpath


def _common_patches():
    """Return context managers patching all external calls."""
    return [
        patch("scraper._pipeline.run_sheet", side_effect=_fake_analyze),
        patch("scraper.apply_estimation_tables", return_value=[]),
        patch("scraper.resolve_cross_references", return_value={}),
        patch("scraper.resolve_spec_lookups", return_value=[]),
        patch("scraper.generate_report", return_value={
            "sheets_processed": 1,
            "total_line_items": 0,
            "total_calculated_items": 0,
        }),
    ]


# ---------------------------------------------------------------------------
# Core: analyze-only produces report without browser
# ---------------------------------------------------------------------------

class TestRunAnalyzeFromManifest:

    def _run(self, screenshots_dir: Path, **kwargs) -> dict:
        patches = _common_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            return asyncio.run(
                run_analyze_from_manifest(screenshots_dir=screenshots_dir, **kwargs)
            )

    def test_produces_report_without_browser(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(tmp_path, [{"page_id": 10}])
        result = self._run(screenshots_dir)
        assert "error" not in result

    def test_no_browser_start_called(self, tmp_path: Path):
        """StackCTBrowser must never be instantiated."""
        screenshots_dir, _ = _make_manifest(tmp_path, [{"page_id": 10}])
        mock_browser_cls = MagicMock()
        with patch("scraper.StackCTBrowser", mock_browser_cls), \
             patch("scraper._pipeline.run_sheet", side_effect=_fake_analyze), \
             patch("scraper.apply_estimation_tables", return_value=[]), \
             patch("scraper.resolve_cross_references", return_value={}), \
             patch("scraper.resolve_spec_lookups", return_value=[]), \
             patch("scraper.generate_report", return_value={"sheets_processed": 1,
                                                            "total_line_items": 0,
                                                            "total_calculated_items": 0}):
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))

        mock_browser_cls.assert_not_called()

    def test_missing_manifest_returns_error(self, tmp_path: Path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        from scraper import run_analyze_from_manifest
        result = asyncio.run(run_analyze_from_manifest(screenshots_dir=empty_dir))
        assert result.get("error") == "manifest_not_found"

    def test_no_dir_returns_error(self):
        from scraper import run_analyze_from_manifest
        result = asyncio.run(run_analyze_from_manifest())
        assert result.get("error") == "analyze_manifest_no_dir"

    def test_accepts_manifest_path_override(self, tmp_path: Path):
        screenshots_dir, mpath = _make_manifest(tmp_path, [{"page_id": 20}])
        patches = _common_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            result = asyncio.run(
                run_analyze_from_manifest(manifest_path_override=mpath)
            )
        assert "error" not in result


# ---------------------------------------------------------------------------
# Skip logic: analysis_status=ok with valid cache
# ---------------------------------------------------------------------------

class TestSkipAlreadyAnalyzed:

    def test_skips_ok_page_when_cache_exists(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(
            tmp_path,
            [{"page_id": 10, "analysis_status": "ok"}],
        )
        # Write a cache file for page 10
        cache = screenshots_dir / "10_analysis.json"
        cache.write_text(json.dumps(_fake_analyze("", "")), encoding="utf-8")

        call_count = {"n": 0}

        def counting_analyze(image_path, sheet_name):
            call_count["n"] += 1
            return _fake_analyze(image_path, sheet_name)

        patches = _common_patches()
        with patch("scraper._pipeline.run_sheet", side_effect=counting_analyze), \
             patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))

        assert call_count["n"] == 0, "analyze_drawing must NOT be called for cached pages"

    def test_reanalyzes_ok_page_without_cache(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(
            tmp_path,
            [{"page_id": 10, "analysis_status": "ok"}],
        )
        # No cache file → must re-analyze
        call_count = {"n": 0}

        def counting_analyze(image_path, sheet_name):
            call_count["n"] += 1
            return _fake_analyze(image_path, sheet_name)

        patches = _common_patches()
        with patch("scraper._pipeline.run_sheet", side_effect=counting_analyze), \
             patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))

        assert call_count["n"] == 1

    def test_force_reanalyzes_even_with_cache(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(
            tmp_path,
            [{"page_id": 10, "analysis_status": "ok"}],
        )
        cache = screenshots_dir / "10_analysis.json"
        cache.write_text(json.dumps(_fake_analyze("", "")), encoding="utf-8")

        call_count = {"n": 0}

        def counting_analyze(image_path, sheet_name):
            call_count["n"] += 1
            return _fake_analyze(image_path, sheet_name)

        patches = _common_patches()
        with patch("scraper._pipeline.run_sheet", side_effect=counting_analyze), \
             patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            asyncio.run(
                run_analyze_from_manifest(screenshots_dir=screenshots_dir, force=True)
            )

        assert call_count["n"] == 1, "force=True must re-analyze even cached pages"

    def test_retries_failed_page(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(
            tmp_path,
            [{"page_id": 10, "analysis_status": "failed"}],
        )
        call_count = {"n": 0}

        def counting_analyze(image_path, sheet_name):
            call_count["n"] += 1
            return _fake_analyze(image_path, sheet_name)

        patches = _common_patches()
        with patch("scraper._pipeline.run_sheet", side_effect=counting_analyze), \
             patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))

        assert call_count["n"] == 1, "Failed pages must be retried"

    def test_retries_pending_page(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(
            tmp_path,
            [{"page_id": 10, "analysis_status": "pending"}],
        )
        call_count = {"n": 0}

        def counting_analyze(image_path, sheet_name):
            call_count["n"] += 1
            return _fake_analyze(image_path, sheet_name)

        patches = _common_patches()
        with patch("scraper._pipeline.run_sheet", side_effect=counting_analyze), \
             patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))

        assert call_count["n"] == 1


# ---------------------------------------------------------------------------
# Cache file written on successful analysis
# ---------------------------------------------------------------------------

class TestAnalysisCache:

    def test_cache_file_written_after_analysis(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(tmp_path, [{"page_id": 42}])
        cache_file = screenshots_dir / "42_analysis.json"
        assert not cache_file.exists()

        patches = _common_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))

        assert cache_file.exists(), "Analysis cache JSON must be written after success"
        cached = json.loads(cache_file.read_text())
        assert "measurements" in cached

    def test_cache_file_not_written_on_analysis_error(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(tmp_path, [{"page_id": 42}])
        cache_file = screenshots_dir / "42_analysis.json"

        patches = _common_patches()
        with patch("scraper._pipeline.run_sheet", return_value={"error": "bad_response"}), \
             patches[1], patches[2], patches[3], \
             patch("scraper.generate_report", return_value={"sheets_processed": 0,
                                                            "total_line_items": 0,
                                                            "total_calculated_items": 0}):
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))

        assert not cache_file.exists(), "Cache must not be written when analysis errors"


# ---------------------------------------------------------------------------
# Missing screenshot graceful handling
# ---------------------------------------------------------------------------

class TestMissingScreenshot:

    def test_missing_screenshot_does_not_crash(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(
            tmp_path,
            [{"page_id": 10, "write_screenshot": False}],
        )
        # Do NOT write screenshot file
        shot = screenshots_dir / "001_Sheet_10.jpg"
        if shot.exists():
            shot.unlink()

        from scraper import run_analyze_from_manifest
        result = asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))
        # Result should be ERROR_ALL_SHEETS_FAILED (all failed = no successful sheets)
        assert "error" in result

    def test_partial_run_continues_after_missing_screenshot(self, tmp_path: Path):
        screenshots_dir, _ = _make_manifest(
            tmp_path,
            [
                {"page_id": 10, "write_screenshot": False},  # missing
                {"page_id": 20},                              # present
            ],
        )
        shot = screenshots_dir / "001_Sheet_10.jpg"
        if shot.exists():
            shot.unlink()

        patches = _common_patches()
        with patch("scraper.generate_report", return_value={"sheets_processed": 1,
                                                            "total_line_items": 0,
                                                            "total_calculated_items": 0}), \
             patches[0], patches[1], patches[2], patches[3]:
            from scraper import run_analyze_from_manifest
            result = asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))

        # Should complete without crashing, partial=True
        assert "error" not in result or result.get("error") != "scrape_failed"


# ---------------------------------------------------------------------------
# Manifest update after each page
# ---------------------------------------------------------------------------

class TestManifestUpdates:

    def test_manifest_updated_after_analysis(self, tmp_path: Path):
        screenshots_dir, mpath = _make_manifest(
            tmp_path, [{"page_id": 10, "analysis_status": "pending"}]
        )
        patches = _common_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            from scraper import run_analyze_from_manifest
            asyncio.run(run_analyze_from_manifest(screenshots_dir=screenshots_dir))

        from capture_manifest import RunManifest
        updated = RunManifest.load(mpath)
        assert updated.pages[0].analysis_status == "ok"
