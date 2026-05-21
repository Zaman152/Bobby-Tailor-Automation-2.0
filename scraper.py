"""
Main orchestrator: scrapes all drawing pages, runs Claude vision, generates report.
No estimation tables needed — Claude extracts quantities directly from drawings.
"""
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
from config import SCREENSHOTS_DIR
from browser import StackCTBrowser
from claude_analyzer import analyze_drawing, make_navigation_decision
from reporter import generate_report

logger = logging.getLogger(__name__)


async def run_project_scrape(project_id: int, project_name: str,
                             log_callback: Optional[Callable] = None,
                             progress_callback: Optional[Callable] = None) -> dict:
    def log(msg: str):
        logger.info(msg)
        if log_callback:
            log_callback(msg)

    log(f"Starting: {project_name} (ID: {project_id})")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = project_name.replace(" ", "_").replace("/", "-")
    screenshots_dir = Path(SCREENSHOTS_DIR) / f"{safe_name}_{ts}"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    browser = StackCTBrowser()
    all_extracted = []

    try:
        await browser.start()
        log("Browser started, logging in...")
        if not await browser.login():
            log("Login failed")
            return {"error": "login_failed"}

        log("Logged in. Discovering drawing pages...")
        pages = await browser.get_all_page_ids(project_id)
        if not pages:
            log("No drawing pages found for this project")
            return {"error": "no_pages_found"}

        log(f"Found {len(pages)} drawing pages — starting analysis...")
        total = len(pages)

        for idx, page_info in enumerate(pages, 1):
            page_id = page_info["page_id"]
            sheet_name = page_info["sheet_name"] or f"Page_{idx}"
            log(f"[{idx}/{total}] Screenshotting {sheet_name}...")

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

            log(f"[{idx}/{total}] Analyzing {sheet_name} with Claude...")
            if progress_callback:
                progress_callback(idx, total, sheet_name)

            extracted = analyze_drawing(str(screenshot_path), sheet_name)
            extracted["_page_id"] = page_id

            if "error" in extracted:
                log(f"  Warning: analysis error on {sheet_name}: {extracted['error']}")
            else:
                n_meas = len(extracted.get("measurements", []))
                n_comp = len(extracted.get("components", []))
                log(f"  {sheet_name}: {n_meas} measurements, {n_comp} components extracted")

            all_extracted.append(extracted)

        log("Generating report...")
        report = generate_report(project_name, all_extracted)
        log(f"Report saved — {report.get('sheets_processed', 0)} sheets, "
            f"{report.get('total_line_items', 0)} takeoff items")
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
