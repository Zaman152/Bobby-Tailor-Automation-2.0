"""Tests for RunManifest / PageEntry round-trip JSON serialisation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from capture_manifest import PageEntry, RunManifest, manifest_path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_entry(page_id: int, sheet_name: str = "S",
                screenshot_rel: str | None = None,
                capture_status: str = "pending",
                analysis_status: str = "pending") -> PageEntry:
    return PageEntry(
        page_id=page_id,
        sheet_name=sheet_name,
        screenshot_rel=screenshot_rel,
        capture_status=capture_status,
        analysis_status=analysis_status,
    )


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

class TestManifestRoundTrip:
    def test_empty_manifest_round_trips(self, tmp_path: Path):
        m = RunManifest(project_id=1, project_name="Empty", folder_id=None)
        path = tmp_path / "manifest.json"
        m.save(path)
        loaded = RunManifest.load(path)

        assert loaded.project_id == 1
        assert loaded.project_name == "Empty"
        assert loaded.folder_id is None
        assert loaded.pages == []

    def test_manifest_with_pages_round_trips(self, tmp_path: Path):
        pages = [
            _make_entry(10, "A-101", "001_A-101.jpg", "ok", "pending"),
            _make_entry(20, "A-102", None, "failed", "skipped"),
        ]
        m = RunManifest(project_id=5, project_name="My Project",
                        folder_id=42, pages=pages)
        path = tmp_path / "manifest.json"
        m.save(path)
        loaded = RunManifest.load(path)

        assert loaded.project_id == 5
        assert loaded.project_name == "My Project"
        assert loaded.folder_id == 42
        assert len(loaded.pages) == 2

        p0 = loaded.pages[0]
        assert p0.page_id == 10
        assert p0.sheet_name == "A-101"
        assert p0.screenshot_rel == "001_A-101.jpg"
        assert p0.capture_status == "ok"
        assert p0.analysis_status == "pending"

        p1 = loaded.pages[1]
        assert p1.page_id == 20
        assert p1.screenshot_rel is None
        assert p1.capture_status == "failed"
        assert p1.analysis_status == "skipped"

    def test_folder_id_none_preserved(self, tmp_path: Path):
        m = RunManifest(project_id=3, project_name="NoFolder", folder_id=None)
        path = tmp_path / "manifest.json"
        m.save(path)
        loaded = RunManifest.load(path)
        assert loaded.folder_id is None

    def test_folder_id_integer_preserved(self, tmp_path: Path):
        m = RunManifest(project_id=7, project_name="WithFolder", folder_id=99)
        path = tmp_path / "manifest.json"
        m.save(path)
        loaded = RunManifest.load(path)
        assert loaded.folder_id == 99

    def test_all_status_values_survive_round_trip(self, tmp_path: Path):
        statuses = ["pending", "ok", "failed", "skipped"]
        pages = [
            _make_entry(i, f"Sheet{i}", f"{i:03d}.jpg", s, s)
            for i, s in enumerate(statuses, 1)
        ]
        m = RunManifest(project_id=0, project_name="Statuses", folder_id=None,
                        pages=pages)
        path = tmp_path / "manifest.json"
        m.save(path)
        loaded = RunManifest.load(path)

        for orig, reloaded in zip(pages, loaded.pages):
            assert reloaded.capture_status == orig.capture_status
            assert reloaded.analysis_status == orig.analysis_status

    def test_json_file_is_valid_and_readable(self, tmp_path: Path):
        m = RunManifest(project_id=99, project_name="JSON Check", folder_id=7)
        m.pages.append(
            _make_entry(1, "S1", "001.jpg", "ok", "ok")
        )
        path = tmp_path / "manifest.json"
        m.save(path)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["project_id"] == 99
        assert data["folder_id"] == 7
        assert len(data["pages"]) == 1
        assert data["pages"][0]["page_id"] == 1

    def test_save_is_atomic_via_tmp_replace(self, tmp_path: Path):
        """Saving should not leave partial JSON if interrupted (tmp + replace)."""
        m = RunManifest(project_id=1, project_name="Atomic", folder_id=None)
        path = tmp_path / "manifest.json"
        m.save(path)
        # File should exist and not leave a .tmp artifact
        assert path.exists()
        assert not path.with_suffix(".tmp").exists()


# ---------------------------------------------------------------------------
# manifest_path helper
# ---------------------------------------------------------------------------

class TestManifestPathHelper:
    def test_returns_manifest_json_inside_dir(self, tmp_path: Path):
        result = manifest_path(tmp_path)
        assert result == tmp_path / "manifest.json"

    def test_result_type_is_path(self, tmp_path: Path):
        result = manifest_path(tmp_path)
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# Mutation tests (state changes survive re-save)
# ---------------------------------------------------------------------------

class TestManifestMutation:
    def test_status_update_persists_on_resave(self, tmp_path: Path):
        """Mutating an entry and re-saving reflects the new status on load."""
        m = RunManifest(project_id=1, project_name="Mutation", folder_id=None)
        m.pages.append(_make_entry(5, "Sheet5", "005.jpg", "pending", "pending"))
        path = tmp_path / "manifest.json"
        m.save(path)

        # Mutate in-place
        m.pages[0].capture_status = "ok"
        m.save(path)

        loaded = RunManifest.load(path)
        assert loaded.pages[0].capture_status == "ok"
        assert loaded.pages[0].analysis_status == "pending"
