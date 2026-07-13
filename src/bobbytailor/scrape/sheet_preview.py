"""
Match drawing sheets to existing HD screenshots from past takeoff runs.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from config import SCREENSHOTS_DIR

_SHEET_FILE_RE = re.compile(r"^\d{3}_(.+)\.(png|jpg|jpeg)$", re.IGNORECASE)
_DEBUG_PAGE_RE = re.compile(r"^_debug_(\d+)\.(png|jpg|jpeg)$", re.IGNORECASE)


def _normalize_sheet_key(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", str(name).strip().lower())


def _project_name_prefix(project_name: str) -> str:
    return project_name.replace(" ", "_").replace("/", "-")


def _stackct_page_url(project_id: int, page_id: int) -> str:
    return f"https://go.stackct.com/app/#/Takeoff/{project_id}/Page/{page_id}/@0,0,0z"


def _screenshot_dirs_for_project(project_name: str) -> list[Path]:
    """Newest screenshot run folders for this project name prefix."""
    root = Path(SCREENSHOTS_DIR)
    if not root.is_dir():
        return []
    prefix = _project_name_prefix(project_name)
    dirs = [p for p in root.iterdir() if p.is_dir() and p.name.startswith(prefix + "_")]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if dirs:
        return dirs
    # Fallback: any screenshot dir (slower, last resort)
    all_dirs = [p for p in root.iterdir() if p.is_dir()]
    all_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return all_dirs[:5]


def _match_png_to_page_id(
    png: Path,
    name_to_page: dict[str, int],
    preview_map: dict[int, Path],
) -> None:
    debug_m = _DEBUG_PAGE_RE.match(png.name)
    if debug_m:
        pid = int(debug_m.group(1))
        if pid not in preview_map:
            preview_map[pid] = png
        return

    file_m = _SHEET_FILE_RE.match(png.name)
    if not file_m:
        return
    file_sheet_key = _normalize_sheet_key(file_m.group(1))
    for norm_name, page_id in name_to_page.items():
        if page_id in preview_map:
            continue
        if file_sheet_key == norm_name:
            preview_map[page_id] = png
            continue
        # Loose match when StackCT truncates names in filenames
        if norm_name in file_sheet_key or file_sheet_key in norm_name:
            preview_map[page_id] = png


def find_screenshot_paths(
    project_id: int,
    project_name: str,
    plans: list[dict],
) -> dict[int, Path]:
    """
    Return {page_id: absolute_path} for HD PNGs from prior runs (newest first).
    """
    if not plans:
        return {}

    name_to_page: dict[str, int] = {}
    for p in plans:
        pid = p.get("page_id")
        if pid is None:
            continue
        key = _normalize_sheet_key(p.get("sheet_name") or "")
        if key:
            name_to_page[key] = int(pid)

    preview_map: dict[int, Path] = {}

    for sheet_dir in _screenshot_dirs_for_project(project_name):
        for png in sorted(p for p in sheet_dir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")):
            _match_png_to_page_id(png, name_to_page, preview_map)
        if len(preview_map) >= len(name_to_page):
            break

    return preview_map


def build_sheet_preview_payload(
    project_id: int,
    project_name: str,
    plans: list[dict],
    folder_id: Optional[int] = None,
) -> dict[int, dict]:
    """
    Per page_id: preview_url (if PNG exists) and stackct_url (always).
    """
    paths = find_screenshot_paths(project_id, project_name, plans)
    qn = quote(project_name, safe="")
    folder_q = f"&folder_id={int(folder_id)}" if folder_id is not None else ""
    out: dict[int, dict] = {}
    for p in plans:
        pid = p.get("page_id")
        if pid is None:
            continue
        pid = int(pid)
        entry = {"stackct_url": _stackct_page_url(project_id, pid)}
        if pid in paths:
            entry["preview_url"] = (
                f"/api/projects/{project_id}/sheet-preview/{pid}"
                f"?project_name={qn}{folder_q}"
            )
        out[pid] = entry
    return out


def resolve_screenshot_path(
    project_id: int,
    page_id: int,
    project_name: str,
    plans: list[dict],
) -> Optional[Path]:
    """Resolve PNG path for serving; None if not on disk."""
    if not plans:
        return None
    paths = find_screenshot_paths(project_id, project_name, plans)
    path = paths.get(int(page_id))
    if path and path.is_file():
        return path.resolve()
    return None
