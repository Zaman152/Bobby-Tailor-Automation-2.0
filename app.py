"""
Flask web app — project selector UI + job runner.
"""
import asyncio
import json
import threading
import uuid
import logging
import os
from typing import Optional
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.exceptions import HTTPException
from config import OUTPUT_DIR, MAX_PREVIEW_ROWS

app = Flask(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("output/screenshots", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# Kick off background project cache refresh on startup
from project_cache import prefetch_in_background
prefetch_in_background()

# In-memory job tracker
jobs: dict = {}


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

    def log(msg: str):
        jobs[job_id]["log"].append(msg)
        logger.info(f"[job {job_id}] {msg}")

    def progress(current: int, total: int, sheet: str, **kwargs):
        pct = int(current / total * 100) if total else 0
        jobs[job_id]["progress"] = pct
        log(f"[{current}/{total}] Analyzing {sheet}...")

    jobs[job_id]["status"] = "running"
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


def _pdf_job(job_id: str, pdf_path: str, project_name: str):
    """Background thread for PDF analysis."""
    from pdf_analyzer import run_pdf_analysis

    def progress(current, total, sheet):
        pct = int(current / total * 100)
        jobs[job_id]["progress"] = pct
        jobs[job_id]["log"].append(f"[{current}/{total}] Analyzing {sheet}...")

    jobs[job_id]["status"] = "running"
    jobs[job_id]["log"].append(f"Starting PDF analysis: {project_name}")
    try:
        result = run_pdf_analysis(pdf_path, project_name, progress_callback=progress)
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
    """Return project list from cache (instant). Browser only used if cache is missing/stale."""
    from project_cache import get_projects as _get
    force = request.args.get("refresh") == "1"
    result = _get(force_refresh=force)
    return jsonify(result)


@app.route("/api/projects/refresh", methods=["POST"])
def refresh_projects():
    """Force a fresh browser fetch of projects and update cache."""
    from project_cache import get_projects as _get
    result = _get(force_refresh=True)
    return jsonify(result)


@app.route("/api/projects/<int:project_id>/plans")
def get_plans(project_id):
    """Return drawing page list for plan selection UI.

    Returns list of {page_id, sheet_name} for each drawing sheet in the project.
    Allows users to preview available sheets before starting analysis.
    """
    from project_cache import get_project_plans as _get_plans
    result = _get_plans(project_id)
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
        "project": project_name, "mode": mode
    }

    t = threading.Thread(
        target=_stackct_job,
        args=(job_id, mode, project_id, project_name, page_ids),
        daemon=True
    )
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/run/pdf", methods=["POST"])
def run_pdf():
    """Upload a PDF and start analysis job."""
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
        "project": project_name, "file": f.filename
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
    return jsonify({
        "id": job["id"],
        "type": job["type"],
        "status": job["status"],
        "progress": job["progress"],
        "log": job["log"][-10:],  # last 10 log lines
        "project": job["project"],
        "error": job["error"],
        "has_result": job["result"] is not None,
    })


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
