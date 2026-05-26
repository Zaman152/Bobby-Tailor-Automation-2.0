"""
Main orchestrator: scrapes all drawing pages, runs Claude vision, applies
estimation tables, and generates a structured takeoff report with source tracing.
"""
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List
from config import SCREENSHOTS_DIR
from browser import StackCTBrowser
from claude_analyzer import analyze_drawing, make_navigation_decision
from calculator import apply_estimation_tables
from reporter import generate_report

logger = logging.getLogger(__name__)


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
    all_extracted = []
    all_estimates = []   # calculated takeoff items (from estimation tables)

    try:
        await browser.start()
        log("Browser started, logging in...")
        if not await browser.login():
            log("Login failed")
            return {"error": "login_failed"}

        log("Logged in. Discovering drawing pages...")
        if folder_id is not None:
            pages = await browser.get_page_ids_in_folder(project_id, folder_id)
            log(f"Using plan set folder_id={folder_id}")
        else:
            pages = await browser.get_all_page_ids(project_id)
        if not pages:
            log("No drawing pages found for this project/plan set")
            return {"error": "no_pages_found"}

        log(f"Found {len(pages)} drawing pages — starting analysis...")

        # Filter to specific pages if requested
        if page_ids_filter:
            pages = [p for p in pages if p["page_id"] in page_ids_filter]
            log(f"Filtered to {len(pages)} selected pages (from {page_ids_filter})")
            if not pages:
                log("No matching pages found for the selected IDs")
                return {"error": "no_matching_pages"}

        total = len(pages)

        for idx, page_info in enumerate(pages, 1):
            page_id = page_info["page_id"]
            sheet_name = page_info["sheet_name"] or f"Page_{idx}"

            if progress_callback:
                progress_callback(idx, total, sheet_name, phase="screenshotting")
            log(f"[{idx}/{total}] Screenshotting {sheet_name}...",
                _make_log_entry(f"[{idx}/{total}] Screenshotting {sheet_name}",
                                "sheet_progress", idx, total, sheet_name))

            screenshot_path = screenshots_dir / f"{idx:03d}_{sheet_name}.png"
            success = await browser.screenshot_full_drawing(project_id, page_id, str(screenshot_path))

            if not success:
                temp = screenshots_dir / f"_debug_{page_id}.png"
                await browser.page.screenshot(path=str(temp))
                decision = make_navigation_decision(str(temp), {"page_id": page_id})
                if decision.get("action") == "skip":
                    log(f"  Skipping {sheet_name} (navigation decision)")
                    continue
                await asyncio.sleep(5)
                success = await browser.screenshot_full_drawing(project_id, page_id, str(screenshot_path))
                if not success:
                    log(f"  Could not capture {sheet_name}, skipping")
                    continue

            if progress_callback:
                progress_callback(idx, total, sheet_name, phase="analyzing")
            log(f"[{idx}/{total}] Analyzing {sheet_name} with Claude...",
                _make_log_entry(f"[{idx}/{total}] Analyzing {sheet_name}",
                                "sheet_progress", idx, total, sheet_name))

            extracted = analyze_drawing(str(screenshot_path), sheet_name)
            extracted["_page_id"] = page_id

            if "error" in extracted:
                log(f"  Warning: analysis error on {sheet_name}: {extracted['error']}")
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
                msg = f"  {sheet_name}: {n_meas} measurements, {n_comp} components extracted"
                log(msg, _make_log_entry(msg, "sheet_complete",
                                         idx, total, sheet_name, extraction_counts))

                if progress_callback:
                    progress_callback(idx, total, sheet_name,
                                      phase="complete", extraction=extraction_counts)

                # STEP 6: Apply estimation tables to compute final takeoff quantities
                estimates = apply_estimation_tables(extracted)
                if estimates:
                    log(f"  {sheet_name}: {len(estimates)} calculated takeoff items")
                all_estimates.extend(estimates)

            all_extracted.append(extracted)

        log("Generating report (raw CSV + calculated CSV + summary + JSON)...")
        report = generate_report(
            project_name,
            all_extracted,
            all_estimates,
            folder_id=folder_id,
        )
        log(f"Report saved — {report.get('sheets_processed', 0)} sheets, "
            f"{report.get('total_line_items', 0)} raw items, "
            f"{report.get('total_calculated_items', 0)} calculated takeoff items")
        files = report.get("_files", {})
        if files:
            log(f"  Files: raw items → {Path(files.get('raw_csv','')).name}")
            log(f"         calculations → {Path(files.get('calculated_csv','')).name}")
            log(f"         summary → {Path(files.get('summary_txt','')).name}")
        return report

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
            return {"error": "login_failed"}
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
