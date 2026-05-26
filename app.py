"""
Flask web app — project selector UI + job runner.
"""
import asyncio
import json
import threading
import uuid
import logging
import os
from datetime import datetime
from typing import Optional
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.exceptions import HTTPException
from config import OUTPUT_DIR, MAX_PREVIEW_ROWS, STACKCT_CACHE_TTL_HOURS

app = Flask(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("output/screenshots", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# SQLite catalog + background StackCT sync on startup
import stackct_store
stackct_store.init_db()

from project_cache import prefetch_in_background
prefetch_in_background()

# Periodic stale catalog refresh (single browser lock — may queue with preview)
try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from stackct_sync import sync_projects_if_stale

    _catalog_scheduler = BackgroundScheduler(daemon=True)
    _catalog_scheduler.add_job(
        sync_projects_if_stale,
        "interval",
        hours=STACKCT_CACHE_TTL_HOURS,
        id="stackct_projects_sync",
        replace_existing=True,
    )
    _catalog_scheduler.start()
    logger.info("StackCT catalog scheduler started (interval=%sh)", STACKCT_CACHE_TTL_HOURS)
except Exception as e:
    logger.warning("APScheduler catalog sync not started: %s", e)

# In-memory job tracker
jobs: dict = {}

# PDF uploads awaiting page selection (upload_id -> metadata)
uploads: dict = {}


# ── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(HTTPException)
def handle_http_exception(e: HTTPException):
    """Handle all HTTP exceptions (404, etc.) with JSON response."""
    return jsonify({"error": e.name, "message": e.description}), e.code


@app.errorhandler(Exception)
def handle_exception(e: Exception):
    """Catch-all handler for unhandled exceptions — returns generic 500."""
    logger.error("Unhandled exception in route", exc_info=True)
    return jsonify({
        "error": "Internal server error",
        "message": "An unexpected error occurred"
    }), 500


# ── Preview Helpers ───────────────────────────────────────────────────────────

ALLOWED_PREVIEW_EXTENSIONS = {'.csv', '.json', '.txt'}


def _validate_preview_path(run_folder: str, filename: str) -> Optional[Path]:
    """Validate and resolve preview file path.

    Returns resolved Path if valid, None if path traversal or invalid.
    Security: Uses Path.resolve() + relative_to() to prevent traversal attacks.
    Logs security-relevant rejections for monitoring.
    """
    # Fast-fail obvious traversal attempts (defense in depth)
    if ".." in run_folder or ".." in filename:
        logger.warning(f"Preview path traversal attempt blocked: {run_folder}/{filename}")
        return None
    if "/" in run_folder or "/" in filename:
        logger.warning(f"Preview path slash attempt blocked: {run_folder}/{filename}")
        return None

    # Check extension is previewable
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_PREVIEW_EXTENSIONS:
        logger.debug(f"Preview extension not allowed: {ext}")
        return None

    # Resolve and validate containment
    output_root = Path(OUTPUT_DIR).resolve()
    target = (output_root / run_folder / filename).resolve()

    try:
        target.relative_to(output_root)
    except ValueError:
        # Path escaped output directory (symlink attack, URL encoding, etc.)
        logger.warning(f"Preview path escaped output directory: {run_folder}/{filename}")
        return None

    if not target.is_file():
        return None

    return target


def _preview_csv(path: Path) -> dict:
    """Read CSV with row cap and pagination metadata.

    Returns dict with type, headers, rows, count, total, capped, cap_limit.
    Memory-efficient: only loads MAX_PREVIEW_ROWS rows, counts rest without storing.
    """
    import csv as csv_module

    total = 0
    rows = []
    headers = []

    with open(path, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv_module.DictReader(f)
        headers = list(reader.fieldnames or [])
        for row in reader:
            total += 1
            if len(rows) < MAX_PREVIEW_ROWS:
                rows.append(row)

    return {
        "type": "csv",
        "headers": headers,
        "rows": rows,
        "count": len(rows),
        "total": total,
        "capped": total > MAX_PREVIEW_ROWS,
        "cap_limit": MAX_PREVIEW_ROWS
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine from a sync thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _stackct_job(job_id: str, mode: str, project_id: Optional[int], project_name: str,
                 page_ids: Optional[list] = None):
    """Background thread for StackCT scraping."""
    from scraper import run_all_projects, run_project_scrape

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

    def progress(current: int, total: int, sheet: str,
                 phase: str = "analyzing", extraction: dict = None):
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
    log("Logging into StackCT...")
    try:
        if mode == "all":
            result = _run_async(run_all_projects(log_callback=log, progress_callback=progress))
        else:
            result = _run_async(run_project_scrape(project_id, project_name,
                                                   page_ids_filter=page_ids,
                                                   log_callback=log, progress_callback=progress))
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
        jobs[job_id]["progress"] = 100
        total = result.get("total_line_items", 0) if isinstance(result, dict) else 0
        log(f"Complete! {result.get('sheets_processed', 0)} sheets · {total} takeoff items extracted")
    except Exception as e:
        logger.exception("StackCT job failed")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = "The job failed. Check server logs for details."
        log("Job failed — see server logs")


def _pdf_job(job_id: str, pdf_path: str, project_name: str,
             selected_pages: Optional[list] = None):
    """Background thread for PDF analysis."""
    from pdf_analyzer import run_pdf_analysis

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
        )
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
        total = result.get("total_line_items", 0)
        jobs[job_id]["progress"] = 100
        jobs[job_id]["log"].append(f"Done — {result.get('sheets_processed',0)} sheets, {total} takeoff items extracted")
    except Exception as e:
        logger.exception("PDF job failed")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = "The job failed. Check server logs for details."


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/projects")
def get_projects():
    """Return project list from SQLite (DB-first).

    Query: ?refresh=1 forces live StackCT sync.
    Response may include from_cache, stale, syncing.
    Legacy projects_cache.json is no longer read on this path.
    """
    from project_cache import get_projects as _get
    force = request.args.get("refresh") == "1"
    result = _get(force_refresh=force)
    return jsonify(result)


@app.route("/api/projects/refresh", methods=["POST"])
def refresh_projects():
    """Force StackCT project catalog sync into SQLite."""
    from stackct_sync import sync_projects
    result = sync_projects(force=True)
    return jsonify(result)


@app.route("/api/projects/sheet-counts")
def get_sheet_counts():
    """Return sheet counts per project_id from SQLite (no browser when DB warm)."""
    from project_cache import get_all_sheet_counts as _counts
    return jsonify(_counts())


@app.route("/api/projects/<int:project_id>/sync-plans", methods=["POST"])
def sync_plans(project_id):
    """Warm plan list for a project into SQLite (serialized browser login)."""
    from stackct_sync import sync_project_plans
    force = request.args.get("force") == "1"
    result = sync_project_plans(project_id, force=force)
    return jsonify(result)


@app.route("/api/projects/<int:project_id>/plans")
def get_plans(project_id):
    """Return drawing page list for plan selection (DB-first).

    Query: ?refresh=1 force live sync; ?background=1 non-blocking empty response.
    """
    from project_cache import get_project_plans as _get_plans
    force = request.args.get("refresh") == "1"
    background = request.args.get("background") == "1"
    result = _get_plans(
        project_id, force_refresh=force, background=background
    )
    return jsonify(result)


@app.route("/api/run/stackct", methods=["POST"])
def run_stackct():
    """Start a StackCT scraping job."""
    data = request.json or {}
    mode = data.get("mode", "all")           # "all" | "specific"
    project_id = data.get("project_id")
    project_name = data.get("project_name", "Project")
    page_ids = data.get("page_ids")          # Optional list of specific page IDs to analyze

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "stackct", "status": "queued",
        "progress": 0, "log": [], "result": None, "error": None,
        "project": project_name, "mode": mode,
        "started_at": None,
        "current_sheet": {"index": 0, "total": 0, "name": None, "phase": None},
        "sheets_completed": []
    }

    t = threading.Thread(
        target=_stackct_job,
        args=(job_id, mode, project_id, project_name, page_ids),
        daemon=True
    )
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/pdf/upload", methods=["POST"])
def upload_pdf():
    """Upload a PDF and return metadata for page selection (no analysis)."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename or not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files accepted"}), 400

    upload_id = str(uuid.uuid4())[:8]
    save_path = os.path.join("uploads", f"{upload_id}_{f.filename}")
    f.save(save_path)

    from pdf_analyzer import get_pdf_metadata
    meta = get_pdf_metadata(save_path)

    uploads[upload_id] = {
        "save_path": save_path,
        "filename": f.filename,
        **meta,
    }

    return jsonify({
        "upload_id": upload_id,
        "filename": f.filename,
        "page_count": meta["page_count"],
        "file_size_bytes": meta["file_size_bytes"],
        "pages": meta["pages"],
    })


@app.route("/api/pdf/run", methods=["POST"])
def run_pdf_from_upload():
    """Start PDF analysis from a previous upload with optional page selection."""
    data = request.json or {}
    upload_id = data.get("upload_id")
    project_name = data.get("project_name")
    selected_pages = data.get("selected_pages")

    if not upload_id:
        return jsonify({"error": "upload_id required"}), 400

    upload = uploads.get(upload_id)
    if not upload:
        return jsonify({"error": "Upload not found or expired"}), 404

    pdf_path = upload["save_path"]
    if not os.path.isfile(pdf_path):
        return jsonify({"error": "Upload file missing on server"}), 404

    if not project_name:
        project_name = Path(upload.get("filename", "PDF Project")).stem

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "pdf", "status": "queued",
        "progress": 0, "log": [], "result": None, "error": None,
        "project": project_name,
        "file": upload.get("filename"),
        "started_at": None,
        "current_sheet": {"index": 0, "total": 0, "name": None, "phase": None},
        "sheets_completed": [],
        "selected_pages": selected_pages,
    }

    t = threading.Thread(
        target=_pdf_job,
        args=(job_id, pdf_path, project_name, selected_pages),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/run/pdf", methods=["POST"])
def run_pdf():
    """Upload a PDF and start analysis job (legacy — all pages, single step)."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename.endswith(".pdf"):
        return jsonify({"error": "Only PDF files accepted"}), 400

    project_name = request.form.get("project_name") or Path(f.filename).stem
    save_path = os.path.join("uploads", f"{str(uuid.uuid4())[:8]}_{f.filename}")
    f.save(save_path)

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "pdf", "status": "queued",
        "progress": 0, "log": [], "result": None, "error": None,
        "project": project_name, "file": f.filename,
        "started_at": None,
        "current_sheet": {"index": 0, "total": 0, "name": None, "phase": None},
        "sheets_completed": []
    }

    t = threading.Thread(
        target=_pdf_job, args=(job_id, save_path, project_name), daemon=True
    )
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    # Don't return full result in status poll — too large
    cs = job.get("current_sheet", {})
    completed = job.get("sheets_completed", [])
    return jsonify({
        "id": job["id"],
        "type": job["type"],
        "status": job["status"],
        "progress": job["progress"],
        "started_at": job.get("started_at"),
        "current_sheet": cs,
        "sheets_completed": len(completed),
        "total_sheets": cs.get("total", 0),
        "sheet_log": completed[-10:],
        "sheet_log_full": completed,
        "log": job["log"][-50:],
        "project": job["project"],
        "error": job["error"],
        "has_result": job["result"] is not None,
    })


@app.route("/api/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id):
    """Request cancellation of a running or queued job."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] not in ("running", "queued"):
        return jsonify({"error": "Job is not running"}), 400
    job["status"] = "cancelled"
    job["_cancel"] = True
    job["log"].append({
        "timestamp": datetime.now().isoformat(),
        "type": "info",
        "message": "Job cancelled by user",
    })
    return jsonify({"success": True})


@app.route("/api/jobs/active")
def get_active_job():
    """Return the currently running job, if any. Used by sidebar mini-card (JOB-04)."""
    for job in jobs.values():
        if job["status"] == "running":
            return jsonify({
                "active": True,
                "job": {
                    "id": job["id"],
                    "type": job["type"],
                    "project": job["project"],
                    "progress": job["progress"],
                    "started_at": job.get("started_at"),
                    "current_sheet": job.get("current_sheet", {}),
                    "sheets_completed": len(job.get("sheets_completed", []))
                }
            })
    return jsonify({"active": False, "job": None})


@app.route("/api/reports")
def list_reports():
    """List all generated report runs. Each run is its own folder under output/.
    Each folder contains: takeoff.json, raw_items.csv, calculations.csv, summary.txt."""
    output = Path(OUTPUT_DIR)
    runs = []

    # Each subdirectory of output/ that contains takeoff.json is a run
    for sub in sorted(output.iterdir(), reverse=True):
        if not sub.is_dir() or sub.name in ("screenshots",):
            continue

        files = {}
        for filename, key in [
            ("takeoff.json",     "json"),
            ("raw_items.csv",    "raw_csv"),
            ("calculations.csv", "calculated_csv"),
            ("summary.txt",      "summary"),
        ]:
            f = sub / filename
            if f.exists():
                files[key] = {"filename": filename, "size": f.stat().st_size}

        cost_usd = None
        sheets_processed = None
        raw_items_count = None
        calculated_count = None
        json_file = sub / "takeoff.json"
        if json_file.exists():
            try:
                with open(json_file) as jf:
                    takeoff_data = json.load(jf)
                api_usage = takeoff_data.get("api_usage", {})
                cost_usd = api_usage.get("total_cost_usd")
                sheets_processed = takeoff_data.get("sheets_processed")
                raw_items_count = takeoff_data.get("total_line_items")
                calculated_count = takeoff_data.get("total_calculated_items")
            except (json.JSONDecodeError, OSError):
                pass

        if not files:
            continue

        # Pretty project name + timestamp from folder name "Project_Name_20260525_203144"
        import re as _re
        m = _re.match(r"^(.*)_(\d{8}_\d{6})$", sub.name)
        if m:
            project_name = m.group(1).replace("_", " ")
            timestamp = m.group(2)
        else:
            project_name = sub.name
            timestamp = ""

        runs.append({
            "run_folder": sub.name,
            "project_name": project_name,
            "timestamp": timestamp,
            "created": sub.stat().st_ctime,
            "files": files,
            "total_cost_usd": cost_usd,
            "sheets_processed": sheets_processed,
            "raw_items_count": raw_items_count,
            "calculated_count": calculated_count,
        })

    # Newest first by created time
    runs.sort(key=lambda r: r["created"], reverse=True)
    return jsonify({"reports": runs})


@app.route("/api/reports/<run_folder>/<filename>")
def download_run_file(run_folder, filename):
    """Download a specific file from a run folder."""
    # Sanitize: only allow simple folder/file names
    if "/" in run_folder or ".." in run_folder or "/" in filename or ".." in filename:
        return jsonify({"error": "Invalid path"}), 400
    path = Path(OUTPUT_DIR) / run_folder / filename
    if not path.exists() or not path.is_file():
        return jsonify({"error": "Not found"}), 404
    return send_file(str(path), as_attachment=True)


@app.route("/api/reports/<run_folder>/preview/<filename>")
def preview_report(run_folder: str, filename: str):
    """Preview report file content for in-browser rendering.

    Returns type-appropriate JSON:
    - .csv → {"type": "csv", "headers": [...], "rows": [...], "total": N, "capped": bool}
    - .json → {"type": "json", "data": {...}}
    - .txt → {"type": "text", "content": "..."}
    """
    path = _validate_preview_path(run_folder, filename)
    if path is None:
        return jsonify({"error": "Invalid path"}), 400

    ext = path.suffix.lower()

    try:
        if ext == '.csv':
            return jsonify(_preview_csv(path))
        elif ext == '.json':
            data = json.loads(path.read_text(encoding='utf-8'))
            return jsonify({"type": "json", "data": data})
        elif ext == '.txt':
            content = path.read_text(encoding='utf-8', errors='replace')
            return jsonify({"type": "text", "content": content})
        else:
            return jsonify({"error": "Unsupported format"}), 400
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in preview: {path.name} - {e}")
        return jsonify({"error": "Invalid JSON file"}), 400
    except UnicodeDecodeError as e:
        logger.warning(f"Encoding error in preview: {path.name} - {e}")
        return jsonify({"error": "File encoding error"}), 400
    except Exception as e:
        logger.error(f"Preview failed for {path.name}", exc_info=True)
        raise


@app.route("/api/reports/<filename>")
def download_report_legacy(filename):
    """Legacy flat-output download — kept for old reports still in the root output dir."""
    path = Path(OUTPUT_DIR) / filename
    if not path.exists() or not path.is_file():
        return jsonify({"error": "Not found"}), 404
    return send_file(str(path), as_attachment=True)


@app.route("/settings")
def settings_page():
    """Settings management page."""
    return render_template("settings.html")


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Return current settings with secrets redacted."""
    from settings import get_settings
    return jsonify(get_settings())


@app.route("/api/settings", methods=["PUT"])
def api_update_settings():
    """Update settings — partial updates supported."""
    from settings import get_settings, update_settings
    data = request.get_json() or {}
    if not data:
        return jsonify({"error": "No settings provided"}), 400

    success, message, restart_required = update_settings(data)
    if not success:
        return jsonify({"error": message}), 400

    return jsonify({
        "success": True,
        "message": message,
        "restart_required": restart_required,
        "settings": get_settings()
    })


if __name__ == "__main__":
    app.run(debug=True, port=5050, use_reloader=False)
