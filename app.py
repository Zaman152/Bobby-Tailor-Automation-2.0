"""
Flask web app — project selector UI + job runner.
"""
import asyncio
import threading
import uuid
import logging
import os
from typing import Optional
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.exceptions import HTTPException
from config import OUTPUT_DIR

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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run_async(coro):
    """Run an async coroutine from a sync thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _stackct_job(job_id: str, mode: str, project_id: Optional[int], project_name: str):
    """Background thread for StackCT scraping."""
    from scraper import run_all_projects, run_project_scrape

    def log(msg: str):
        jobs[job_id]["log"].append(msg)
        logger.info(f"[job {job_id}] {msg}")

    def progress(current: int, total: int, sheet: str):
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
                                                   log_callback=log, progress_callback=progress))
        jobs[job_id]["status"] = "done"
        jobs[job_id]["result"] = result
        jobs[job_id]["progress"] = 100
        total = result.get("total_line_items", 0) if isinstance(result, dict) else 0
        log(f"Complete! {result.get('sheets_processed', 0)} sheets · {total} takeoff items extracted")
    except Exception as e:
        logger.exception("StackCT job failed")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
        log(f"Error: {e}")


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
        jobs[job_id]["error"] = str(e)


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


@app.route("/api/run/stackct", methods=["POST"])
def run_stackct():
    """Start a StackCT scraping job."""
    data = request.json or {}
    mode = data.get("mode", "all")           # "all" | "specific"
    project_id = data.get("project_id")
    project_name = data.get("project_name", "Project")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "stackct", "status": "queued",
        "progress": 0, "log": [], "result": None, "error": None,
        "project": project_name, "mode": mode
    }

    t = threading.Thread(
        target=_stackct_job,
        args=(job_id, mode, project_id, project_name),
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


@app.route("/api/reports/<filename>")
def download_report_legacy(filename):
    """Legacy flat-output download — kept for old reports still in the root output dir."""
    path = Path(OUTPUT_DIR) / filename
    if not path.exists() or not path.is_file():
        return jsonify({"error": "Not found"}), 404
    return send_file(str(path), as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5050, use_reloader=False)
