"""
Main orchestrator: scrapes all drawing pages, runs Claude vision, applies
estimation tables, and generates a structured takeoff report with source tracing.

Two-phase execution model:
  Pass 1 (Capture)  — browser required; screenshots all pages into run folder;
                      writes manifest.json after each page; closes browser.
  Pass 2 (Analyze)  — no browser; Claude processes every captured screenshot;
                      updates manifest.json after each page.
  Pass 3 (Report)   — aggregation, cross-refs, CSV/summary output.
"""
import asyncio
import logging
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any
from config import SCREENSHOTS_DIR, REUSE_SCREENSHOTS, AUTO_INCLUDE_LINKED_SHEETS, MAX_LINKED_SHEETS
from linked_sheets import collect_unresolved_refs, match_ref_to_page
import stackct_store
from browser import StackCTBrowser
from capture_manifest import PageEntry, RunManifest, manifest_path
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


def _weighted_progress(idx: int, total: int, phase: str) -> int:
    """Return a weighted progress percentage that reflects the true job phase.

    Capturing: 0–40%, Analyzing: 40–90%, Reporting: 95–100%.
    This prevents the bar from appearing stuck at <10% while Claude processes
    sheet 1 of many during the analyze pass.
    """
    frac = (idx / total) if total else 0.0
    if phase == "capturing":
        return int(frac * 40)
    if phase in ("analyzing", "complete"):
        return int(40 + frac * 50)
    if phase == "reporting":
        return 95
    return int(frac * 100)


async def _discover_and_add_linked_sheets(
    browser: "StackCTBrowser",
    project_id: int,
    project_name: str,
    folder_id: Optional[int],
    all_extracted: List[dict],
    manifest: "RunManifest",
    mpath: Path,
    screenshots_dir: Path,
    cached_screenshots: "dict[int, Path]",
    log: Callable,
    progress_callback: Optional[Callable],
    cancel_check: Optional[Callable[[], bool]],
) -> "tuple[List[dict], List[dict], List[dict]]":
    """Pass 2a–2c: discover linked pages, capture them, analyze them.

    Returns (new_extracted, new_estimates, linked_meta) where:
      new_extracted: extraction dicts for linked pages
      new_estimates: calculator results for linked pages
      linked_meta: list of {page_id, sheet_name, ref_from} for report metadata
    """
    # ----------------------------------------------------------------
    # Pass 2a — Discover unresolved cross-reference targets
    # ----------------------------------------------------------------
    already_in_run: set[int] = {e.page_id for e in manifest.pages}
    refs = collect_unresolved_refs(all_extracted, already_in_run)

    if not refs:
        log("Linked sheets: no cross-references found — skipping linked pass")
        return [], [], []

    catalog = stackct_store.get_plans(project_id, folder_id)
    if not catalog:
        logger.warning(
            "Linked sheet discovery: catalog empty for project %s folder %s — "
            "sync the plan set first",
            project_id,
            folder_id,
        )
        log(
            "WARNING: Linked sheet catalog empty — sync plan set to enable linked capture"
        )
        return [], [], []

    # Match refs to catalog page_ids and build the capture queue
    linked_queue: list[dict] = []
    seen_page_ids: set[int] = set()

    for ref in refs:
        match = match_ref_to_page(ref["ref_sheet"], catalog)
        if match is None:
            continue
        page_id = match["page_id"]
        if page_id in already_in_run or page_id in seen_page_ids:
            continue
        seen_page_ids.add(page_id)
        linked_queue.append(
            {
                "page_id": page_id,
                "sheet_name": match["sheet_name"],
                "ref_from": ref.get("from_sheet", ""),
            }
        )

    if len(linked_queue) > MAX_LINKED_SHEETS:
        dropped = len(linked_queue) - MAX_LINKED_SHEETS
        log(
            f"Linked sheets: capped at {MAX_LINKED_SHEETS} "
            f"(dropped {dropped} low-priority entries)"
        )
        linked_queue = linked_queue[:MAX_LINKED_SHEETS]

    if not AUTO_INCLUDE_LINKED_SHEETS:
        log("AUTO_INCLUDE_LINKED_SHEETS=false — skipping linked capture")
        return (
            [],
            [],
            [
                {
                    "page_id": x["page_id"],
                    "sheet_name": x["sheet_name"],
                    "ref_from": x["ref_from"],
                    "suggested_only": True,
                }
                for x in linked_queue
            ],
        )

    if not linked_queue:
        log("Linked sheets: no new linked sheets to capture")
        return [], [], []

    log(f"Linked sheets: queued {len(linked_queue)} page(s) for capture and analysis")

    # ----------------------------------------------------------------
    # Pass 2b — Capture linked pages (browser required)
    # ----------------------------------------------------------------
    newly_captured: list[tuple[dict, PageEntry]] = []

    try:
        await browser.start()
        if not await browser.login():
            log("ERROR: Linked sheet capture — browser login failed")
            return [], [], [{"error": "login_failed"}]

        for entry_info in linked_queue:
            if cancel_check and cancel_check():
                log("Cancelled by user during linked capture pass")
                break

            page_id = entry_info["page_id"]
            sheet_name = entry_info["sheet_name"]
            screenshot_path = (
                screenshots_dir
                / f"linked_{page_id}_{_safe_sheet_filename(sheet_name)}.jpg"
            )

            page_entry = PageEntry(
                page_id=page_id,
                sheet_name=sheet_name,
                screenshot_rel=screenshot_path.name,
                capture_status="pending",
                analysis_status="pending",
                source="linked_ref",
            )
            manifest.pages.append(page_entry)

            # Reuse cached screenshot if available
            cached_path = cached_screenshots.get(page_id)
            if cached_path and cached_path.is_file() and cached_path.stat().st_size > 1000:
                screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cached_path, screenshot_path)
                log(f"  [linked] Using cached screenshot for {sheet_name}")
                page_entry.capture_status = "ok"
            else:
                log(f"  [linked] Capturing {sheet_name} (page_id={page_id})...")
                captured, skip_reason = await _capture_sheet_screenshot(
                    browser, project_id, page_id, sheet_name,
                    screenshot_path, screenshots_dir, log,
                )
                if captured:
                    page_entry.capture_status = "ok"
                else:
                    reason = skip_reason or "capture_failed"
                    log(f"  [linked] Could not capture {sheet_name} ({reason})")
                    page_entry.capture_status = "failed"

            manifest.save(mpath)

            if page_entry.capture_status == "ok":
                newly_captured.append((entry_info, page_entry))

    finally:
        await browser.close()

    # ----------------------------------------------------------------
    # Pass 2c — Analyze linked pages (no browser)
    # ----------------------------------------------------------------
    new_extracted: list[dict] = []
    new_estimates: list[dict] = []
    linked_meta: list[dict] = []

    for entry_info, page_entry in newly_captured:
        if cancel_check and cancel_check():
            log("Cancelled by user during linked analysis pass")
            break

        page_id = page_entry.page_id
        sheet_name = page_entry.sheet_name
        screenshot_path = screenshots_dir / page_entry.screenshot_rel

        try:
            log(f"  [linked] Analyzing {sheet_name} with Claude...")
            extracted = analyze_drawing(str(screenshot_path), sheet_name)
            extracted["_page_id"] = page_id
            extracted["_source_sheet"] = sheet_name

            if "error" in extracted:
                err = extracted.get("error", "analysis_failed")
                log(f"  [linked] Warning: analysis error on {sheet_name}: {err}")
                page_entry.analysis_status = "failed"
                new_extracted.append(extracted)
            else:
                estimates = apply_estimation_tables(extracted)
                if estimates:
                    log(f"  [linked] {sheet_name}: {len(estimates)} takeoff items")
                new_estimates.extend(estimates)
                new_extracted.append(extracted)
                page_entry.analysis_status = "ok"
                linked_meta.append(
                    {
                        "page_id": page_id,
                        "sheet_name": sheet_name,
                        "ref_from": entry_info["ref_from"],
                    }
                )

        except Exception as exc:
            logger.exception("Linked analysis error on sheet %s", sheet_name)
            reason = type(exc).__name__
            log(f"  [linked] Analysis error on {sheet_name}: {reason} — continuing")
            page_entry.analysis_status = "failed"
            new_extracted.append(_failed_extraction(page_id, sheet_name, reason))

        manifest.save(mpath)

    return new_extracted, new_estimates, linked_meta


async def run_project_scrape(project_id: int, project_name: str,
                             page_ids_filter: Optional[List[int]] = None,
                             folder_id: Optional[int] = None,
                             log_callback: Optional[Callable] = None,
                             progress_callback: Optional[Callable] = None,
                             cancel_check: Optional[Callable[[], bool]] = None) -> dict:
    def log(msg: str, entry: dict = None):
        logger.info(msg)
        if log_callback:
            log_callback(entry if entry else msg)

    log(f"Starting: {project_name} (ID: {project_id})")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = project_name.replace(" ", "_").replace("/", "-")
    screenshots_dir = Path(SCREENSHOTS_DIR) / f"{safe_name}_{ts}"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    manifest = RunManifest(
        project_id=project_id,
        project_name=project_name,
        folder_id=folder_id,
    )
    mpath = manifest_path(screenshots_dir)

    browser = StackCTBrowser()
    browser_closed = False
    all_extracted: List[dict] = []
    all_estimates: List[dict] = []
    sheets_failed: List[Dict[str, Any]] = []
    sheets_skipped: List[Dict[str, Any]] = []

    try:
        # ----------------------------------------------------------------
        # Login + page discovery
        # ----------------------------------------------------------------
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

        log(f"Found {len(pages)} drawing pages — starting capture pass...")

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

        # Populate manifest with all pages in pending state
        for idx, page_info in enumerate(pages, 1):
            sheet_name = page_info["sheet_name"] or f"Page_{idx}"
            manifest.pages.append(PageEntry(
                page_id=page_info["page_id"],
                sheet_name=sheet_name,
                screenshot_rel=None,
                capture_status="pending",
                analysis_status="pending",
            ))
        manifest.save(mpath)

        # ================================================================
        # PASS 1 — Capture (browser required)
        # All screenshots are taken before any Claude API call.
        # ================================================================
        log("Pass 1 — Capturing all screenshots...")
        for idx, (page_info, entry) in enumerate(zip(pages, manifest.pages), 1):
            page_id = page_info["page_id"]
            sheet_name = entry.sheet_name

            screenshot_path = (
                screenshots_dir / f"{idx:03d}_{_safe_sheet_filename(sheet_name)}.jpg"
            )
            entry.screenshot_rel = screenshot_path.name

            try:
                if progress_callback:
                    progress_callback(idx, total, sheet_name, phase="capturing")

                # --- screenshot reuse ---
                cached_path = cached_screenshots.get(page_id)
                if cached_path and cached_path.is_file() and cached_path.stat().st_size > 1000:
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(cached_path, screenshot_path)
                    msg = f"[{idx}/{total}] Using cached screenshot for {sheet_name}"
                    log(msg, _make_log_entry(msg, "sheet_progress", idx, total, sheet_name))
                    entry.capture_status = "ok"
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
                            entry.capture_status = "skipped"
                            sheets_skipped.append({
                                "page_id": page_id,
                                "sheet_name": sheet_name,
                                "reason": skip_reason,
                            })
                        else:
                            reason = skip_reason or "capture_failed"
                            msg = f"  Could not capture {sheet_name} ({reason})"
                            log(msg, _make_log_entry(msg, "sheet_error", idx, total, sheet_name))
                            entry.capture_status = "failed"
                            sheets_failed.append({
                                "page_id": page_id,
                                "sheet_name": sheet_name,
                                "reason": reason,
                            })
                    else:
                        entry.capture_status = "ok"

            except Exception as exc:
                logger.exception("Unhandled capture error on sheet %s", sheet_name)
                reason = type(exc).__name__
                msg = f"  Capture error on {sheet_name}: {reason} — continuing"
                log(msg, _make_log_entry(msg, "sheet_error", idx, total, sheet_name))
                entry.capture_status = "failed"
                sheets_failed.append({
                    "page_id": page_id,
                    "sheet_name": sheet_name,
                    "reason": reason,
                })

            manifest.save(mpath)

            # Cooperative cancellation — checked between sheets
            if cancel_check and cancel_check():
                log("Cancelled by user during capture pass")
                break

        # Close browser before Claude phase — releases browser resources
        await browser.close()
        browser_closed = True
        log("Browser closed after capture pass")

        captured_ok = sum(1 for e in manifest.pages if e.capture_status == "ok")
        log(
            f"Pass 1 complete — {captured_ok}/{total} pages captured"
            + (f", {total - captured_ok} failed/skipped" if captured_ok < total else "")
        )

        # Cooperative cancellation — between capture and analyze passes
        _cancelled = cancel_check and cancel_check()
        if _cancelled:
            log("Cancelled by user between capture and analyze passes")

        # ================================================================
        # PASS 2 — Analyze (no browser; Claude processes each screenshot)
        # ================================================================
        log("Pass 2 — Analyzing captured screenshots with Claude...")
        for idx, (page_info, entry) in enumerate(zip(pages, manifest.pages), 1):
            if _cancelled:
                break
            page_id = page_info["page_id"]
            sheet_name = entry.sheet_name

            if entry.capture_status != "ok":
                # Propagate capture failures into the extracted list
                if entry.capture_status == "failed":
                    capture_reason = next(
                        (f["reason"] for f in sheets_failed if f["page_id"] == page_id),
                        "capture_failed",
                    )
                    entry.analysis_status = "skipped"
                    all_extracted.append(
                        _failed_extraction(page_id, sheet_name, capture_reason)
                    )
                else:
                    entry.analysis_status = "skipped"
                manifest.save(mpath)
                continue

            screenshot_path = screenshots_dir / entry.screenshot_rel

            try:
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
                    entry.analysis_status = "failed"
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
                    entry.analysis_status = "ok"

                all_extracted.append(extracted)

            except Exception as exc:
                logger.exception("Unhandled analysis error on sheet %s", sheet_name)
                reason = type(exc).__name__
                msg = f"  Analysis error on {sheet_name}: {reason} — continuing"
                log(msg, _make_log_entry(msg, "sheet_error", idx, total, sheet_name))
                entry.analysis_status = "failed"
                sheets_failed.append({
                    "page_id": page_id,
                    "sheet_name": sheet_name,
                    "reason": reason,
                })
                all_extracted.append(_failed_extraction(page_id, sheet_name, reason))

            manifest.save(mpath)

            # Cooperative cancellation — checked between sheets
            if not _cancelled and cancel_check and cancel_check():
                log("Cancelled by user during analyze pass")
                _cancelled = True

        # ================================================================
        # PASS 3 — Report
        # ================================================================
        successful = [d for d in all_extracted if "error" not in d]
        if not successful:
            if _cancelled:
                return {
                    "_cancelled": True,
                    "error": "cancelled",
                    "sheets_failed": sheets_failed,
                    "sheets_skipped": sheets_skipped,
                    "screenshots_dir": str(screenshots_dir),
                }
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

        if _cancelled:
            log(f"Cancelled — generating partial report from {len(successful)} completed sheet(s)...")

        if progress_callback:
            progress_callback(total, total, "Generating report", phase="reporting")
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

        if sheets_failed or sheets_skipped or _cancelled:
            report["partial"] = True
            report["sheets_failed"] = sheets_failed
            report["sheets_skipped"] = sheets_skipped
            report["sheets_succeeded"] = len(successful)
            if _cancelled:
                report["_cancelled"] = True
            log(
                f"Report saved (partial) — {len(successful)}/{total} sheets OK, "
                f"{len(sheets_failed)} failed, {len(sheets_skipped)} skipped"
                + (" (cancelled)" if _cancelled else "")
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
        if not browser_closed:
            await browser.close()
            log("Browser closed")


async def run_analyze_from_manifest(
    screenshots_dir: Optional[Path] = None,
    manifest_path_override: Optional[Path] = None,
    force: bool = False,
    log_callback: Optional[Callable] = None,
    progress_callback: Optional[Callable] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> dict:
    """
    Analyze-only pass using an existing run manifest.

    Recovers from mid-run crashes: loads manifest.json from a previous run,
    skips pages with analysis_status='ok' (unless force=True), re-runs Claude
    on pending/failed pages, writes report.  No browser required.

    Args:
        screenshots_dir: Run folder containing manifest.json and screenshots.
        manifest_path_override: Explicit path to manifest.json (overrides screenshots_dir).
        force: Re-analyze all pages regardless of existing analysis_status.
        log_callback: Optional callable for structured log entries.
        progress_callback: Optional callable for progress updates.

    Returns:
        Report dict (same shape as run_project_scrape) or error dict.
    """
    import json as _json

    def log(msg: str, entry: dict = None):
        logger.info(msg)
        if log_callback:
            log_callback(entry if entry else msg)

    # Resolve manifest path ---------------------------------------------------
    if manifest_path_override:
        mpath = Path(manifest_path_override)
        if screenshots_dir is None:
            screenshots_dir = mpath.parent
    elif screenshots_dir is not None:
        screenshots_dir = Path(screenshots_dir)
        mpath = manifest_path(screenshots_dir)
    else:
        return {"error": "analyze_manifest_no_dir"}

    if not mpath.exists():
        log(f"Manifest not found: {mpath}")
        return {"error": "manifest_not_found", "path": str(mpath)}

    log(f"Loading manifest: {mpath}")
    try:
        run_manifest = RunManifest.load(mpath)
    except Exception as exc:
        log(f"Failed to load manifest: {exc}")
        return {"error": "manifest_load_failed", "message": str(exc)}

    project_name = run_manifest.project_name
    folder_id = run_manifest.folder_id
    pages = run_manifest.pages
    total = len(pages)

    log(f"Analyze-only: {project_name} — {total} page(s) in manifest")

    all_extracted: List[dict] = []
    all_estimates: List[dict] = []
    sheets_failed: List[Dict[str, Any]] = []
    sheets_skipped: List[Dict[str, Any]] = []
    _cancelled = False

    for idx, entry in enumerate(pages, 1):
        if _cancelled:
            break
        page_id = entry.page_id
        sheet_name = entry.sheet_name

        # Skip pages that were never captured ----------------------------------
        if entry.capture_status != "ok":
            if entry.capture_status == "failed":
                entry.analysis_status = "skipped"
                all_extracted.append(
                    _failed_extraction(page_id, sheet_name, "capture_failed")
                )
                sheets_failed.append({
                    "page_id": page_id,
                    "sheet_name": sheet_name,
                    "reason": "capture_failed",
                })
            else:
                entry.analysis_status = "skipped"
                sheets_skipped.append({
                    "page_id": page_id,
                    "sheet_name": sheet_name,
                    "reason": entry.capture_status,
                })
            run_manifest.save(mpath)
            continue

        if not entry.screenshot_rel:
            log(f"  [{sheet_name}] manifest entry has no screenshot filename — skipping")
            entry.analysis_status = "failed"
            sheets_failed.append({
                "page_id": page_id,
                "sheet_name": sheet_name,
                "reason": "no_screenshot_rel",
            })
            run_manifest.save(mpath)
            continue

        screenshot_path = screenshots_dir / entry.screenshot_rel
        if not screenshot_path.exists():
            log(f"  [{sheet_name}] screenshot missing on disk: {entry.screenshot_rel}")
            entry.analysis_status = "failed"
            sheets_failed.append({
                "page_id": page_id,
                "sheet_name": sheet_name,
                "reason": "screenshot_missing",
            })
            run_manifest.save(mpath)
            continue

        # Per-page analysis cache: {page_id}_analysis.json beside screenshot --
        cache_file = screenshots_dir / f"{page_id}_analysis.json"

        if entry.analysis_status == "ok" and not force:
            if cache_file.exists():
                try:
                    cached = _json.loads(cache_file.read_text(encoding="utf-8"))
                    all_extracted.append(cached)
                    estimates = apply_estimation_tables(cached)
                    all_estimates.extend(estimates)
                    log(
                        f"[{idx}/{total}] {sheet_name}: loaded from analysis cache",
                        _make_log_entry(
                            f"[{idx}/{total}] {sheet_name}: from cache",
                            "sheet_progress", idx, total, sheet_name,
                        ),
                    )
                    if progress_callback:
                        progress_callback(
                            idx, total, sheet_name, phase="complete",
                            extraction={"cached": True},
                        )
                    continue
                except Exception:
                    pass  # Cache corrupted → fall through to re-analyze
            # No valid cache file but status=ok → re-analyze to rebuild cache
            log(f"[{idx}/{total}] {sheet_name}: no cache file, re-analyzing")

        # Run analysis --------------------------------------------------------
        try:
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
                entry.analysis_status = "failed"
                sheets_failed.append({
                    "page_id": page_id,
                    "sheet_name": sheet_name,
                    "reason": f"analysis:{err}",
                })
            else:
                # Save analysis JSON cache beside screenshot
                try:
                    cache_file.write_text(
                        _json.dumps(extracted, indent=2), encoding="utf-8"
                    )
                except Exception as cache_err:
                    logger.warning(
                        "Could not write analysis cache for %s: %s", sheet_name, cache_err
                    )

                n_meas = len(extracted.get("measurements", []))
                n_comp = len(extracted.get("components", []))
                extraction_counts = {
                    "measurements": n_meas,
                    "components": n_comp,
                    "rooms": len(extracted.get("rooms", [])),
                    "schedules": len(extracted.get("schedules", [])),
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
                entry.analysis_status = "ok"

            all_extracted.append(extracted)

        except Exception as exc:
            logger.exception("Unhandled analysis error on sheet %s", sheet_name)
            reason = type(exc).__name__
            msg = f"  Analysis error on {sheet_name}: {reason} — continuing"
            log(msg, _make_log_entry(msg, "sheet_error", idx, total, sheet_name))
            entry.analysis_status = "failed"
            sheets_failed.append({
                "page_id": page_id,
                "sheet_name": sheet_name,
                "reason": reason,
            })
            all_extracted.append(_failed_extraction(page_id, sheet_name, reason))

        run_manifest.save(mpath)

        # Cooperative cancellation — checked between sheets
        if not _cancelled and cancel_check and cancel_check():
            log("Cancelled by user during analyze pass")
            _cancelled = True

    # Report ------------------------------------------------------------------
    successful = [d for d in all_extracted if "error" not in d]
    if not successful:
        if _cancelled:
            return {
                "_cancelled": True,
                "error": "cancelled",
                "sheets_failed": sheets_failed,
                "sheets_skipped": sheets_skipped,
                "screenshots_dir": str(screenshots_dir),
            }
        log(
            f"All {total} sheet(s) failed — no report generated. "
            "Check capture statuses and re-run with force=True if needed."
        )
        return {
            "error": ERROR_ALL_SHEETS_FAILED,
            "sheets_failed": sheets_failed,
            "sheets_skipped": sheets_skipped,
            "screenshots_dir": str(screenshots_dir),
        }

    if _cancelled:
        log(f"Cancelled — generating partial report from {len(successful)} completed sheet(s)...")

    if progress_callback:
        progress_callback(total, total, "Generating report", phase="reporting")
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

    if sheets_failed or sheets_skipped or _cancelled:
        report["partial"] = True
        report["sheets_failed"] = sheets_failed
        report["sheets_skipped"] = sheets_skipped
        report["sheets_succeeded"] = len(successful)
        if _cancelled:
            report["_cancelled"] = True
        log(
            f"Report saved (partial) — {len(successful)}/{total} sheets OK, "
            f"{len(sheets_failed)} failed, {len(sheets_skipped)} skipped"
            + (" (cancelled)" if _cancelled else "")
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
