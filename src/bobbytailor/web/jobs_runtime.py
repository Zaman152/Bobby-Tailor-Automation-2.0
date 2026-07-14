"""
In-memory job tracker and background thread launchers.

Job threads receive ONLY primitive payloads (str/int/dict/list), never Flask
request or current_app objects.
"""
import asyncio
import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from bobbytailor.stores import job_store

logger = logging.getLogger(__name__)

# In-memory job tracker
jobs: dict = {}

# PDF uploads awaiting page selection (upload_id -> metadata)
uploads: dict = {}

# Uploaded object manifests awaiting a run (manifest_id -> {path, count, objects})
object_manifests: dict = {}

job_lock = threading.Lock()

#: Job statuses that occupy the single run slot (WR-06).
ACTIVE_JOB_STATUSES = ("queued", "running")


def register_job(job_id: str, job: dict) -> Optional[str]:
    """Atomically register *job* unless another job is active (21-REVIEW WR-06).

    The scraper keeps per-run state on a shared module-level pipeline
    singleton (LearnedContext, object manifest, RunSettings, schedules
    cache). Two overlapping jobs would swap each other's learned context
    mid-run — sheet analysis for project A silently picking up project B's
    prompt hints, scale priors, and re_verify flags. One active job at a
    time is enforced here, under ``job_lock``, at registration time.

    Returns None when the job was registered, else the id of the currently
    active (queued/running) job that holds the slot.
    """
    with job_lock:
        for jid, existing in jobs.items():
            if existing.get("status") in ACTIVE_JOB_STATUSES:
                return jid
        jobs[job_id] = job
        return None

def _run_async(coro):
    """Run an async coroutine from a sync thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# User-facing job error messages (safe for UI — no stack traces)
JOB_ERROR_MESSAGES = {
    "login_failed": "StackCT login failed. Check email and password in Settings.",
    "no_pages_found": "No drawing pages found for this project or plan set.",
    "no_matching_pages": "None of the selected sheets were found in this plan set.",
    "all_sheets_failed": "Every sheet failed during capture or analysis. See the job log for details.",
    "scrape_failed": "The takeoff job failed unexpectedly. Check server logs for details.",
}


def _user_facing_job_error(error_code: str) -> str:
    if isinstance(error_code, str) and error_code.startswith("analysis:"):
        return f"Analysis failed on one or more sheets ({error_code})."
    return JOB_ERROR_MESSAGES.get(str(error_code), "The job failed. Check server logs for details.")


def _persist_job_history(job_id: str, job_type: str) -> None:
    try:
        job_store.save_job_run(jobs[job_id], job_id=job_id, job_type=job_type)
    except (NameError, ImportError, AttributeError):
        # Wiring bugs (missing import / renamed API) must fail loudly —
        # swallowing them silently disabled ALL job-history persistence
        # once before (21-REVIEW CR-02).
        raise
    except Exception:
        logger.exception("Failed to persist job run %s to history", job_id)


def _finalize_stackct_job(job_id: str, result, log):
    """Set job status from scraper result — handles errors, partial success, and full success."""
    jobs[job_id]["finished_at"] = datetime.now().isoformat()

    if not isinstance(result, dict):
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = JOB_ERROR_MESSAGES["scrape_failed"]
        log(jobs[job_id]["error"])
        _persist_job_history(job_id, "stackct")
        return

    # Cancelled: scraper stopped early; preserve "cancelled" status set by endpoint
    if result.get("_cancelled"):
        if result.get("error") == "cancelled":
            # No sheets completed — nothing to save
            log("Job cancelled — no sheets completed.")
        else:
            # Partial report saved
            jobs[job_id]["result"] = result
            sheets_ok = result.get("sheets_succeeded", 0)
            jobs[job_id]["warning"] = f"Job cancelled — partial report from {sheets_ok} sheet(s)."
            log(jobs[job_id]["warning"])
        jobs[job_id]["current_phase"] = "cancelled"
        if jobs[job_id].get("status") != "cancelled":
            jobs[job_id]["status"] = "cancelled"
        _persist_job_history(job_id, "stackct")
        return

    if result.get("error"):
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = _user_facing_job_error(result["error"])
        jobs[job_id]["result"] = result
        log(jobs[job_id]["error"])
        if result.get("sheets_failed"):
            n = len(result["sheets_failed"])
            log(f"{n} sheet(s) failed before report generation.")
        _persist_job_history(job_id, "stackct")
        return

    jobs[job_id]["status"] = "done"
    jobs[job_id]["result"] = result
    jobs[job_id]["progress"] = 100
    jobs[job_id]["error"] = None
    jobs[job_id]["current_phase"] = "done"

    # Phase 18: linked sheet counts for monitor UI
    jobs[job_id]["linked_sheets_count"] = result.get("linked_sheets_added_count", 0)
    jobs[job_id]["linked_sheets_suggested_count"] = result.get("linked_sheets_suggested_count", 0)

    total_items = result.get("total_line_items", 0)
    sheets_ok = result.get("sheets_succeeded") or result.get("sheets_processed", 0)

    if result.get("partial"):
        failed_n = len(result.get("sheets_failed") or [])
        skipped_n = len(result.get("sheets_skipped") or [])
        log(
            f"Complete with warnings — {sheets_ok} sheets OK, "
            f"{failed_n} failed, {skipped_n} skipped · {total_items} takeoff items"
        )
        jobs[job_id]["warning"] = (
            f"Partial report: {failed_n} sheet(s) failed, {skipped_n} skipped."
        )
    else:
        log(
            f"Complete! {result.get('sheets_processed', 0)} sheets · "
            f"{total_items} takeoff items extracted"
        )

    _persist_job_history(job_id, "stackct")


def _resolve_manifest_dir(
    manifest_dir: Optional[str], project_name: str
) -> Optional[Path]:
    """
    Resolve the run folder containing manifest.json for analyze-only mode.

    Tries explicit *manifest_dir* first (absolute or relative to SCREENSHOTS_DIR),
    then auto-discovers the most-recent run folder for *project_name*.
    """
    from bobbytailor.config import SCREENSHOTS_DIR as _SCREENSHOTS_DIR

    base = Path(_SCREENSHOTS_DIR)

    if manifest_dir:
        p = Path(manifest_dir)
        if not p.is_absolute():
            p = base / manifest_dir
        if p.is_dir() and (p / "manifest.json").exists():
            return p
        return None

    # Auto-discover: newest run folder whose manifest.json exists
    if not base.exists():
        return None
    safe_name = project_name.replace(" ", "_").replace("/", "-")
    candidates = sorted(
        [
            d for d in base.iterdir()
            if d.is_dir()
            and d.name.startswith(safe_name)
            and (d / "manifest.json").exists()
        ],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _stackct_job(job_id: str, mode: str, project_id: Optional[int], project_name: str,
                 page_ids: Optional[list] = None, folder_id: Optional[int] = None,
                 analyze_only: bool = False, manifest_dir: Optional[str] = None,
                 object_manifest_path: Optional[str] = None):
    """Background thread for StackCT scraping."""
    from bobbytailor.scrape.scraper import run_all_projects, run_project_scrape, run_analyze_from_manifest

    def log(msg_or_entry):
        """Accept either plain string or structured entry dict."""
        if isinstance(msg_or_entry, dict):
            jobs[job_id]["log"].append(msg_or_entry)
            logger.info(f"[job {job_id}] {msg_or_entry.get('message', str(msg_or_entry))}")
        else:
            jobs[job_id]["log"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "info",
                "message": msg_or_entry
            })
            logger.info(f"[job {job_id}] {msg_or_entry}")
        # Cap log size to prevent unbounded memory growth
        if len(jobs[job_id]["log"]) > 200:
            jobs[job_id]["log"] = jobs[job_id]["log"][-150:]

    def _weighted_pct(current: int, total: int, phase: str) -> int:
        """Weighted progress: capturing 0-40%, analyzing/linking 40-90%, reporting 95%."""
        frac = (current / total) if total else 0.0
        if phase == "capturing":
            return int(frac * 40)
        if phase in ("analyzing", "complete", "linking"):
            return int(40 + frac * 50)
        if phase == "reporting":
            return 95
        return int(frac * 100)

    def progress(current: int, total: int, sheet: str,
                 phase: str = "analyzing", extraction: dict = None):
        pct = _weighted_pct(current, total, phase)
        jobs[job_id]["progress"] = pct
        jobs[job_id]["current_phase"] = phase
        if total > 0:
            jobs[job_id]["total_sheets"] = total
        jobs[job_id]["current_sheet"] = {
            "index": current,
            "total": total,
            "name": sheet,
            "phase": phase
        }
        if phase == "complete" and extraction:
            jobs[job_id]["sheets_completed"].append({
                "name": sheet,
                "extraction": extraction
            })

    def cancel_check() -> bool:
        return bool(jobs[job_id].get("_cancel"))

    if jobs[job_id].get("_cancel"):
        jobs[job_id]["status"] = "cancelled"
        jobs[job_id]["current_phase"] = "cancelled"
        log("Job cancelled before start.")
        _persist_job_history(job_id, "stackct")
        return

    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = datetime.now().isoformat()
    try:
        if analyze_only:
            log("Analyze-only mode — loading manifest, skipping browser...")
            resolved_dir = _resolve_manifest_dir(manifest_dir, project_name)
            if resolved_dir is None:
                jobs[job_id]["finished_at"] = datetime.now().isoformat()
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = (
                    "No manifest directory found for analyze-only mode. "
                    "Run a full capture first or specify manifest_dir."
                )
                log(jobs[job_id]["error"])
                _persist_job_history(job_id, "stackct")
                return
            log(f"Resuming from: {resolved_dir}")
            result = _run_async(run_analyze_from_manifest(
                screenshots_dir=resolved_dir,
                log_callback=log,
                progress_callback=progress,
                cancel_check=cancel_check,
                object_manifest_path=object_manifest_path,
            ))
        else:
            log("Logging into StackCT...")
            if mode == "all":
                result = _run_async(
                    run_all_projects(
                        log_callback=log,
                        progress_callback=progress,
                        cancel_check=cancel_check,
                    )
                )
            else:
                result = _run_async(run_project_scrape(
                    project_id,
                    project_name,
                    page_ids_filter=page_ids,
                    folder_id=folder_id,
                    log_callback=log,
                    progress_callback=progress,
                    cancel_check=cancel_check,
                    object_manifest_path=object_manifest_path,
                ))
        _finalize_stackct_job(job_id, result, log)
    except Exception:
        logger.exception("StackCT job failed")
        jobs[job_id]["finished_at"] = datetime.now().isoformat()
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = JOB_ERROR_MESSAGES["scrape_failed"]
        log(jobs[job_id]["error"])
        _persist_job_history(job_id, "stackct")


def _pdf_job(job_id: str, pdf_path: str, project_name: str,
             selected_pages: Optional[list] = None,
             manifest_path: Optional[str] = None):
    """Background thread for PDF analysis."""
    from bobbytailor.pipeline.pdf_analyzer import run_pdf_analysis

    def log(msg_or_entry):
        if isinstance(msg_or_entry, dict):
            jobs[job_id]["log"].append(msg_or_entry)
        else:
            jobs[job_id]["log"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "info",
                "message": msg_or_entry
            })
        if len(jobs[job_id]["log"]) > 200:
            jobs[job_id]["log"] = jobs[job_id]["log"][-150:]

    def progress(current, total, sheet, phase: str = "analyzing", extraction: dict = None):
        pct = int(current / total * 100) if total else 0
        jobs[job_id]["progress"] = pct
        jobs[job_id]["current_sheet"] = {
            "index": current,
            "total": total,
            "name": sheet,
            "phase": phase
        }
        if phase == "complete" and extraction:
            jobs[job_id]["sheets_completed"].append({
                "name": sheet,
                "extraction": extraction
            })

    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = datetime.now().isoformat()
    pages_desc = f"pages {selected_pages}" if selected_pages else "all pages"
    jobs[job_id]["log"].append({
        "timestamp": datetime.now().isoformat(),
        "type": "info",
        "message": f"Starting PDF analysis: {project_name} ({pages_desc})"
    })
    try:
        result = run_pdf_analysis(
            pdf_path, project_name,
            selected_pages=selected_pages,
            progress_callback=progress,
            manifest_path=manifest_path,
        )
        jobs[job_id]["status"] = "done"
        jobs[job_id]["finished_at"] = datetime.now().isoformat()
        jobs[job_id]["result"] = result
        total = result.get("total_line_items", 0)
        jobs[job_id]["progress"] = 100
        jobs[job_id]["log"].append(f"Done — {result.get('sheets_processed',0)} sheets, {total} takeoff items extracted")
        _persist_job_history(job_id, "pdf")
    except Exception as e:
        logger.exception("PDF job failed")
        jobs[job_id]["finished_at"] = datetime.now().isoformat()
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = "The job failed. Check server logs for details."
        _persist_job_history(job_id, "pdf")


