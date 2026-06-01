"""
Main orchestrator: scrapes all drawing pages, runs Claude vision, applies
estimation tables, and generates a structured takeoff report with source tracing.
"""
import asyncio
import logging
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any
from config import SCREENSHOTS_DIR, REUSE_SCREENSHOTS
from browser import StackCTBrowser
from sheet_preview import find_screenshot_paths
from claude_analyzer import analyze_drawing, make_navigation_decision
from calculator import apply_estimation_tables, resolve_spec_lookups
from cross_references import resolve_cross_references
from reporter import generate_report

logger = logging.getLogger(__name__)

# User-facing error codes returned in result dict (mapped to messages in app.py)
ERROR_LOGIN_FAILED = "login_failed"
ERROR_NO_PAGES = "no_pages_found"
ERROR_NO_MATCHING_PAGES = "no_matching_pages"
ERROR_ALL_SHEETS_FAILED = "all_sheets_failed"


def _make_log_entry(msg: str, entry_type: str = "info",
                    sheet_index: int = None, sheet_total: int = None,
                    sheet_name: str = None, extraction: dict = None) -> dict:
    """Create a structured log entry for the job log."""
    from datetime import datetime as _dt
    entry = {
        "timestamp": _dt.now().isoformat(),
        "type": entry_type,
        "message": msg
    }
    if sheet_index is not None:
        entry["sheet_index"] = sheet_index
        entry["sheet_total"] = sheet_total
        entry["sheet_name"] = sheet_name
    if extraction:
        entry["extraction"] = extraction
    return entry


def _safe_sheet_filename(sheet_name: str) -> str:
    """Make sheet name safe for use in a single path segment (no / or \\)."""
    safe = sheet_name.replace("/", "-").replace("\\", "-")
    safe = re.sub(r'[<>:"|?*]', "-", safe)
    return safe.strip() or "sheet"


def _failed_extraction(page_id: int, sheet_name: str, reason: str) -> dict:
    return {
        "error": reason,
        "_page_id": page_id,
        "_source_sheet": sheet_name,
        "_tokens_in": 0,
        "_tokens_out": 0,
        "_cost_usd": 0.0,
    }


async def _capture_sheet_screenshot(
    browser: StackCTBrowser,
    project_id: int,
    page_id: int,
    sheet_name: str,
    screenshot_path: Path,
    screenshots_dir: Path,
    log: Callable,
) -> tuple[bool, Optional[str]]:
    """
    Download or screenshot a drawing page. Returns (success, skip_reason).
    skip_reason is set when the sheet is intentionally skipped (not a crash).
    """
    try:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        success = await browser.download_drawing_image(
            project_id, page_id, str(screenshot_path)
        )

        if not success and browser.page:
            temp = screenshots_dir / f"_debug_{page_id}.png"
            try:
                temp.parent.mkdir(parents=True, exist_ok=True)
                await browser.page.screenshot(path=str(temp))
                decision = make_navigation_decision(str(temp), {"page_id": page_id})
                if decision.get("action") == "skip":
                    return False, "navigation_skip"
            except Exception as nav_err:
                logger.warning("Navigation decision failed for %s: %s", sheet_name, nav_err)

            await asyncio.sleep(5)
            success = await browser.download_drawing_image(
                project_id, page_id, str(screenshot_path)
            )

        if not success:
            return False, "capture_failed"

        if not screenshot_path.is_file() or screenshot_path.stat().st_size < 1000:
            return False, "capture_empty"

        return True, None

    except Exception as exc:
        logger.exception("Screenshot capture failed for %s", sheet_name)
        return False, f"capture_error:{type(exc).__name__}"


async def run_project_scrape(project_id: int, project_name: str,
                             page_ids_filter: Optional[List[int]] = None,
                             folder_id: Optional[int] = None,
                             log_callback: Optional[Callable] = None,
                             progress_callback: Optional[Callable] = None) -> dict:
    def log(msg: str, entry: dict = None):
        logger.info(msg)
        if log_callback:
            log_callback(entry if entry else msg)

    log(f"Starting: {project_name} (ID: {project_id})")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = project_name.replace(" ", "_").replace("/", "-")
    screenshots_dir = Path(SCREENSHOTS_DIR) / f"{safe_name}_{ts}"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    browser = StackCTBrowser()
    all_extracted: List[dict] = []
    all_estimates: List[dict] = []
    sheets_failed: List[Dict[str, Any]] = []
    sheets_skipped: List[Dict[str, Any]] = []

    try:
        await browser.start()
        log("Browser started, logging in...")
        if not await browser.login():
            log("Login failed — check StackCT credentials in Settings")
            return {"error": ERROR_LOGIN_FAILED}

        log("Logged in. Discovering drawing pages...")
        if folder_id is not None:
            pages = await browser.get_page_ids_in_folder(project_id, folder_id)
            log(f"Using plan set folder_id={folder_id}")
        else:
            pages = await browser.get_all_page_ids(project_id)
        if not pages:
            log("No drawing pages found for this project/plan set")
            return {"error": ERROR_NO_PAGES}

        log(f"Found {len(pages)} drawing pages — starting analysis...")

        if page_ids_filter:
            pages = [p for p in pages if p["page_id"] in page_ids_filter]
            log(f"Filtered to {len(pages)} selected pages (from {page_ids_filter})")
            if not pages:
                log("No matching pages found for the selected IDs")
                return {"error": ERROR_NO_MATCHING_PAGES}

        total = len(pages)

        # Build cache map once for the whole run when reuse is enabled
        cached_screenshots: dict[int, Path] = {}
        if REUSE_SCREENSHOTS:
            cached_screenshots = find_screenshot_paths(project_id, project_name, pages)
            if cached_screenshots:
                log(f"Screenshot cache: {len(cached_screenshots)} prior files found for reuse")

        for idx, page_info in enumerate(pages, 1):
            page_id = page_info["page_id"]
            sheet_name = page_info["sheet_name"] or f"Page_{idx}"

            try:
                if progress_callback:
                    progress_callback(idx, total, sheet_name, phase="screenshotting")

                screenshot_path = (
                    screenshots_dir / f"{idx:03d}_{_safe_sheet_filename(sheet_name)}.jpg"
                )

                # --- screenshot reuse ---
                cached_path = cached_screenshots.get(page_id)
                if cached_path and cached_path.is_file() and cached_path.stat().st_size > 1000:
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(cached_path, screenshot_path)
                    msg = f"[{idx}/{total}] Using cached screenshot for {sheet_name}"
                    log(
                        msg,
                        _make_log_entry(msg, "sheet_progress", idx, total, sheet_name),
                    )
                    captured, skip_reason = True, None
                else:
                    log(
                        f"[{idx}/{total}] Screenshotting {sheet_name}...",
                        _make_log_entry(
                            f"[{idx}/{total}] Screenshotting {sheet_name}",
                            "sheet_progress", idx, total, sheet_name,
                        ),
                    )
                    captured, skip_reason = await _capture_sheet_screenshot(
                        browser, project_id, page_id, sheet_name,
                        screenshot_path, screenshots_dir, log,
                    )

                if not captured:
                    if skip_reason == "navigation_skip":
                        log(f"  Skipping {sheet_name} (navigation decision)")
                        sheets_skipped.append({
                            "page_id": page_id,
                            "sheet_name": sheet_name,
                            "reason": skip_reason,
                        })
                    else:
                        msg = f"  Could not capture {sheet_name} ({skip_reason or 'unknown'})"
                        log(msg, _make_log_entry(msg, "sheet_error", idx, total, sheet_name))
                        sheets_failed.append({
                            "page_id": page_id,
                            "sheet_name": sheet_name,
                            "reason": skip_reason or "capture_failed",
                        })
                        all_extracted.append(
                            _failed_extraction(page_id, sheet_name, skip_reason or "capture_failed")
                        )
                    continue

                if progress_callback:
                    progress_callback(idx, total, sheet_name, phase="analyzing")
                log(
                    f"[{idx}/{total}] Analyzing {sheet_name} with Claude...",
                    _make_log_entry(
                        f"[{idx}/{total}] Analyzing {sheet_name}",
                        "sheet_progress", idx, total, sheet_name,
                    ),
                )

                extracted = analyze_drawing(str(screenshot_path), sheet_name)
                extracted["_page_id"] = page_id
                extracted["_source_sheet"] = sheet_name

                if "error" in extracted:
                    err = extracted.get("error", "analysis_failed")
                    log(f"  Warning: analysis error on {sheet_name}: {err}")
                    sheets_failed.append({
                        "page_id": page_id,
                        "sheet_name": sheet_name,
                        "reason": f"analysis:{err}",
                    })
                else:
                    n_meas = len(extracted.get("measurements", []))
                    n_comp = len(extracted.get("components", []))
                    n_rooms = len(extracted.get("rooms", []))
                    n_sched = len(extracted.get("schedules", []))
                    extraction_counts = {
                        "measurements": n_meas,
                        "components": n_comp,
                        "rooms": n_rooms,
                        "schedules": n_sched,
                    }
                    msg = (
                        f"  {sheet_name}: {n_meas} measurements, "
                        f"{n_comp} components extracted"
                    )
                    log(
                        msg,
                        _make_log_entry(
                            msg, "sheet_complete", idx, total, sheet_name, extraction_counts
                        ),
                    )
                    if progress_callback:
                        progress_callback(
                            idx, total, sheet_name,
                            phase="complete", extraction=extraction_counts,
                        )
                    estimates = apply_estimation_tables(extracted)
                    if estimates:
                        log(f"  {sheet_name}: {len(estimates)} calculated takeoff items")
                    all_estimates.extend(estimates)

                all_extracted.append(extracted)

            except Exception as exc:
                logger.exception("Unhandled error on sheet %s", sheet_name)
                reason = type(exc).__name__
                msg = f"  Error on {sheet_name}: {reason} — continuing with remaining sheets"
                log(msg, _make_log_entry(msg, "sheet_error", idx, total, sheet_name))
                sheets_failed.append({
                    "page_id": page_id,
                    "sheet_name": sheet_name,
                    "reason": reason,
                })
                all_extracted.append(_failed_extraction(page_id, sheet_name, reason))

        successful = [d for d in all_extracted if "error" not in d]
        if not successful:
            log(
                f"All {total} sheet(s) failed — no report generated. "
                f"See sheet errors above."
            )
            return {
                "error": ERROR_ALL_SHEETS_FAILED,
                "sheets_failed": sheets_failed,
                "sheets_skipped": sheets_skipped,
                "screenshots_dir": str(screenshots_dir),
            }

        log("Resolving cross-references and spec lookups...")
        cross_refs = resolve_cross_references(all_extracted)
        all_estimates = resolve_spec_lookups(all_extracted, all_estimates)

        log("Generating report (raw CSV + calculated CSV + summary + JSON)...")
        report = generate_report(
            project_name,
            all_extracted,
            all_estimates,
            folder_id=folder_id,
            cross_references=cross_refs,
        )

        if sheets_failed or sheets_skipped:
            report["partial"] = True
            report["sheets_failed"] = sheets_failed
            report["sheets_skipped"] = sheets_skipped
            report["sheets_succeeded"] = len(successful)
            log(
                f"Report saved (partial) — {len(successful)}/{total} sheets OK, "
                f"{len(sheets_failed)} failed, {len(sheets_skipped)} skipped"
            )
        else:
            log(
                f"Report saved — {report.get('sheets_processed', 0)} sheets, "
                f"{report.get('total_line_items', 0)} raw items, "
                f"{report.get('total_calculated_items', 0)} calculated takeoff items"
            )

        files = report.get("_files", {})
        if files:
            log(f"  Files: raw items → {Path(files.get('raw_csv', '')).name}")
            log(f"         calculations → {Path(files.get('calculated_csv', '')).name}")
            log(f"         summary → {Path(files.get('summary_txt', '')).name}")

        report["screenshots_dir"] = str(screenshots_dir)
        return report

    except Exception as exc:
        logger.exception("Project scrape failed")
        return {
            "error": "scrape_failed",
            "message": type(exc).__name__,
            "sheets_failed": sheets_failed,
            "sheets_skipped": sheets_skipped,
        }

    finally:
        await browser.close()
        log("Browser closed")


async def run_all_projects(log_callback: Optional[Callable] = None,
                           progress_callback: Optional[Callable] = None) -> dict:
    def log(msg: str):
        logger.info(msg)
        if log_callback:
            log_callback(msg)

    browser = StackCTBrowser()
    results = {}
    try:
        await browser.start()
        log("Logging in to fetch project list...")
        if not await browser.login():
            return {"error": ERROR_LOGIN_FAILED}
        projects = await browser.get_all_projects()
        log(f"Found {len(projects)} projects — running each in sequence...")
    finally:
        await browser.close()

    for i, p in enumerate(projects, 1):
        log(f"[{i}/{len(projects)}] Starting project: {p['name']}")
        results[p["name"]] = await run_project_scrape(
            p["id"], p["name"],
            log_callback=log_callback,
            progress_callback=progress_callback
        )

    return results
