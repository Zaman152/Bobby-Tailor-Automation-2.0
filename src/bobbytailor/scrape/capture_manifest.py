"""
Manifest file for a scrape run.

Tracks per-page capture and analysis status so demos show all screenshots
landing first (Pass 1 complete) before Claude processing begins (Pass 2).
Written to ``screenshots_dir/manifest.json`` after every page state change,
providing a crash-recovery foundation for 17-03.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class PageEntry:
    """State record for a single drawing page within a run."""

    page_id: int
    sheet_name: str
    screenshot_rel: Optional[str]  # filename relative to screenshots_dir
    capture_status: str            # "pending" | "ok" | "failed" | "skipped"
    analysis_status: str           # "pending" | "ok" | "failed" | "skipped"
    source: Optional[str] = None  # "linked_ref" for auto-added pages; None for user-selected


@dataclass
class RunManifest:
    """Top-level manifest for one project scrape run."""

    project_id: int
    project_name: str
    folder_id: Optional[int]
    pages: List[PageEntry] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def save(self, path: Path) -> None:
        """Atomically write manifest to *path* as pretty-printed JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "project_id": self.project_id,
                    "project_name": self.project_name,
                    "folder_id": self.folder_id,
                    "pages": [asdict(p) for p in self.pages],
                },
                fh,
                indent=2,
            )
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "RunManifest":
        """Load a manifest from JSON at *path*."""
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(
            project_id=data["project_id"],
            project_name=data["project_name"],
            folder_id=data.get("folder_id"),
            pages=[
                PageEntry(
                    page_id=p["page_id"],
                    sheet_name=p["sheet_name"],
                    screenshot_rel=p.get("screenshot_rel"),
                    capture_status=p.get("capture_status", "pending"),
                    analysis_status=p.get("analysis_status", "pending"),
                    source=p.get("source"),
                )
                for p in data.get("pages", [])
            ],
        )


def manifest_path(screenshots_dir: Path) -> Path:
    """Return the canonical manifest path for a run folder."""
    return screenshots_dir / "manifest.json"
