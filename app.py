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
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from flask_login import current_user, login_user, logout_user, login_required
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import HTTPException
from config import OUTPUT_DIR, MAX_PREVIEW_ROWS, STACKCT_CACHE_TTL_HOURS
from auth import login_manager, bcrypt, limiter, init_admin, get_admin

app = Flask(__name__)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Security configuration ────────────────────────────────────────────────────

app.config.update(
    SECRET_KEY=os.environ["SECRET_KEY"],
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.getenv("FLASK_ENV") != "development",
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=43200,   # 12 hours
    WTF_CSRF_TIME_LIMIT=3600,
)

csrf = CSRFProtect(app)
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.session_protection = "strong"
bcrypt.init_app(app)
limiter.init_app(app)

init_admin(
    email=os.environ["ADMIN_EMAIL"],
    password_hash=os.environ["ADMIN_PASSWORD_HASH"],
)

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


# ── Auth Guard ───────────────────────────────────────────────────────────────

PUBLIC_ENDPOINTS: frozenset = frozenset({"login", "logout", "static"})


@app.before_request
def require_login():
    """Block unauthenticated access to all routes.

    API routes (/api/*) return 401 JSON; browser routes redirect to /login.
    """
    if not request.endpoint or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if not current_user.is_authenticated:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login", next=request.path))


# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour")
def login():
    """Login page and credential verification endpoint."""
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        admin = get_admin()

        # Always run bcrypt to prevent timing-based user enumeration
        _dummy = bcrypt.generate_password_hash("__dummy__").decode()
        check_hash = admin.password_hash if (admin and email == admin.email) else _dummy
        credentials_valid = (
            admin is not None
            and email == admin.email
            and bcrypt.check_password_hash(check_hash, password)
        )

        if credentials_valid:
            login_user(admin, remember=False)
            nxt = request.args.get("next", "")
            from urllib.parse import urlparse
            parsed = urlparse(nxt)
            if nxt and parsed.scheme == "" and parsed.netloc == "" and nxt.startswith("/"):
                return redirect(nxt)
            return redirect(url_for("index"))

        error = "Invalid credentials"

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    """POST-only logout — prevents logout CSRF via GET requests or embedded images."""
    logout_user()
    return redirect(url_for("login"))


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


def _finalize_stackct_job(job_id: str, result, log):
    """Set job status from scraper result — handles errors, partial success, and full success."""
    if not isinstance(result, dict):
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = JOB_ERROR_MESSAGES["scrape_failed"]
        log(jobs[job_id]["error"])
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
        return

    if result.get("error"):
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = _user_facing_job_error(result["error"])
        jobs[job_id]["result"] = result
        log(jobs[job_id]["error"])
        if result.get("sheets_failed"):
            n = len(result["sheets_failed"])
            log(f"{n} sheet(s) failed before report generation.")
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


def _resolve_manifest_dir(
    manifest_dir: Optional[str], project_name: str
) -> Optional[Path]:
    """
    Resolve the run folder containing manifest.json for analyze-only mode.

    Tries explicit *manifest_dir* first (absolute or relative to SCREENSHOTS_DIR),
    then auto-discovers the most-recent run folder for *project_name*.
    """
    from config import SCREENSHOTS_DIR as _SCREENSHOTS_DIR

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
                 analyze_only: bool = False, manifest_dir: Optional[str] = None):
    """Background thread for StackCT scraping."""
    from scraper import run_all_projects, run_project_scrape, run_analyze_from_manifest

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

    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = datetime.now().isoformat()
    try:
        if analyze_only:
            log("Analyze-only mode — loading manifest, skipping browser...")
            resolved_dir = _resolve_manifest_dir(manifest_dir, project_name)
            if resolved_dir is None:
                jobs[job_id]["status"] = "error"
                jobs[job_id]["error"] = (
                    "No manifest directory found for analyze-only mode. "
                    "Run a full capture first or specify manifest_dir."
                )
                log(jobs[job_id]["error"])
                return
            log(f"Resuming from: {resolved_dir}")
            result = _run_async(run_analyze_from_manifest(
                screenshots_dir=resolved_dir,
                log_callback=log,
                progress_callback=progress,
                cancel_check=cancel_check,
            ))
        else:
            log("Logging into StackCT...")
            if mode == "all":
                result = _run_async(
                    run_all_projects(log_callback=log, progress_callback=progress)
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
                ))
        _finalize_stackct_job(job_id, result, log)
    except Exception:
        logger.exception("StackCT job failed")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = JOB_ERROR_MESSAGES["scrape_failed"]
        log(jobs[job_id]["error"])


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


@app.route("/api/projects/<int:project_id>/sync-plan-sets", methods=["POST"])
def sync_plan_sets_route(project_id):
    """Warm plan-set (folder) index for a project into SQLite."""
    from stackct_sync import sync_project_plan_sets
    force = request.args.get("force") == "1"
    count_sheets = request.args.get("counts") == "1"
    return jsonify(
        sync_project_plan_sets(project_id, force=force, count_sheets=count_sheets)
    )


@app.route("/api/projects/<int:project_id>/plan-sets")
def get_plan_sets_route(project_id):
    """Return plan sets (folders) for a project (DB-first).

    Query: ?refresh=1 — full sync with per-folder sheet counts (slow)
           ?wait=1 — block until fast folder list is ready (Preview Plans)
    """
    from project_cache import get_project_plan_sets as _get
    force = request.args.get("refresh") == "1"
    wait = request.args.get("wait") == "1"
    return jsonify(_get(project_id, force_refresh=force, wait=wait))


@app.route("/api/projects/<int:project_id>/plan-sets/<int:folder_id>/plans")
def get_folder_plans(project_id, folder_id):
    """Return drawing pages for one plan set (DB-first). Query: ?refresh=1"""
    from project_cache import get_project_plans as _get_plans
    force = request.args.get("refresh") == "1"
    background = request.args.get("background") == "1"
    return jsonify(
        _get_plans(
            project_id,
            folder_id,
            force_refresh=force,
            background=background,
        )
    )


def _stackct_project_name(project_id: int) -> str:
    import stackct_store as store

    store.init_db()
    for p in store.list_projects():
        if p.get("id") == project_id:
            return p.get("name") or f"Project_{project_id}"
    return f"Project_{project_id}"


@app.route("/api/projects/<int:project_id>/sheet-previews")
def sheet_previews(project_id):
    """Map page_id → preview_url (if HD screenshot exists) and stackct_url."""
    from project_cache import get_project_plans as _get_plans
    from sheet_preview import build_sheet_preview_payload

    folder_id = request.args.get("folder_id", type=int)
    if folder_id is None:
        return jsonify({"error": "folder_id required"}), 400

    data = _get_plans(project_id, folder_id, force_refresh=False, background=False)
    plans = data.get("plans") or []
    name = (request.args.get("project_name") or "").strip() or _stackct_project_name(project_id)
    previews = build_sheet_preview_payload(
        project_id, name, plans, folder_id=folder_id
    )
    return jsonify({"previews": {str(k): v for k, v in previews.items()}})


@app.route("/api/projects/<int:project_id>/sheet-preview/<int:page_id>")
def serve_sheet_preview(project_id, page_id):
    """Serve an HD drawing image from a prior takeoff run (JPEG or PNG)."""
    from project_cache import get_project_plans as _get_plans
    from sheet_preview import resolve_screenshot_path

    folder_id = request.args.get("folder_id", type=int)
    if folder_id is None:
        return jsonify({"error": "folder_id required"}), 400

    name = (request.args.get("project_name") or "").strip() or _stackct_project_name(project_id)
    data = _get_plans(project_id, folder_id, force_refresh=False, background=False)
    plans = data.get("plans") or []
    path = resolve_screenshot_path(project_id, page_id, name, plans)
    if not path:
        return jsonify({"error": "Screenshot not found"}), 404
    mime = "image/jpeg" if str(path).lower().endswith((".jpg", ".jpeg")) else "image/png"
    return send_file(path, mimetype=mime, max_age=3600)


@app.route("/api/projects/<int:project_id>/sync-plans", methods=["POST"])
def sync_plans(project_id):
    """Warm plan list for one folder into SQLite. Requires folder_id in JSON or query."""
    from stackct_sync import sync_project_plans
    force = request.args.get("force") == "1"
    body = request.get_json(silent=True) or {}
    folder_id = body.get("folder_id")
    if folder_id is None:
        folder_id = request.args.get("folder_id", type=int)
    if folder_id is None:
        return jsonify({
            "error": "folder_id required. Call /plan-sets first, then sync a folder.",
        }), 400
    return jsonify(sync_project_plans(project_id, int(folder_id), force=force))


@app.route("/api/projects/<int:project_id>/plans")
def get_plans(project_id):
    """Legacy plans route — requires folder_id query param."""
    folder_id = request.args.get("folder_id", type=int)
    if folder_id is None:
        return jsonify({
            "error": "folder_id required. Use GET /api/projects/<id>/plan-sets first.",
            "hint": "/api/projects/{}/plan-sets".format(project_id),
        }), 400
    from project_cache import get_project_plans as _get_plans
    force = request.args.get("refresh") == "1"
    background = request.args.get("background") == "1"
    return jsonify(
        _get_plans(
            project_id,
            folder_id,
            force_refresh=force,
            background=background,
        )
    )


@app.route("/api/run/stackct", methods=["POST"])
def run_stackct():
    """
    Start a StackCT scraping job.

    Body parameters:
        mode (str): "all" | "specific" — ignored when analyze_only=true.
        project_id (int): StackCT project ID (required for mode="specific").
        project_name (str): Human-readable project name.
        page_ids (list[int]): Optional subset of page IDs (mode="specific").
        folder_id (int): Optional plan-set folder ID.
        analyze_only (bool): Skip capture; re-run Claude on an existing
            manifest. Requires a prior capture run for project_name.
        manifest_dir (str): Optional explicit run folder path (absolute or
            relative to output/screenshots). Auto-discovers latest run when
            omitted. Only used when analyze_only=true.
    """
    data = request.json or {}
    mode = data.get("mode", "all")           # "all" | "specific"
    project_id = data.get("project_id")
    project_name = data.get("project_name", "Project")
    page_ids = data.get("page_ids")          # Optional list of specific page IDs to analyze
    folder_id = data.get("folder_id")
    analyze_only: bool = bool(data.get("analyze_only", False))
    manifest_dir: Optional[str] = data.get("manifest_dir") or None

    # Validate page_ids belong to folder when both provided
    if not analyze_only and mode == "specific" and project_id and page_ids and folder_id is not None:
        import stackct_store as _store
        _store.init_db()
        allowed = {
            p["page_id"]
            for p in _store.get_plans(int(project_id), int(folder_id))
        }
        if allowed:
            bad = [pid for pid in page_ids if int(pid) not in allowed]
            if bad:
                return jsonify({
                    "error": (
                        f"page_ids {bad[:5]} are not in plan set folder {folder_id}"
                    ),
                }), 400

    mode_detail = "analyze_only" if analyze_only else "full"

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id, "type": "stackct", "status": "queued",
        "progress": 0, "log": [], "result": None, "error": None,
        "project": project_name, "mode": mode, "mode_detail": mode_detail,
        "started_at": None,
        "current_phase": None,
        "current_sheet": {"index": 0, "total": 0, "name": None, "phase": None},
        "sheets_completed": [],
        "linked_sheets_count": 0,
        "linked_sheets_suggested_count": 0,
    }

    t = threading.Thread(
        target=_stackct_job,
        args=(job_id, mode, project_id, project_name, page_ids, folder_id),
        kwargs={"analyze_only": analyze_only, "manifest_dir": manifest_dir},
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
        "current_phase": job.get("current_phase") or (cs.get("phase") if cs else None),
        "sheets_completed": len(completed),
        "total_sheets": cs.get("total", 0),
        "sheet_log": completed[-10:],
        "sheet_log_full": completed,
        "log": job["log"][-50:],
        "project": job["project"],
        "error": job["error"],
        "warning": job.get("warning"),
        "has_result": job["result"] is not None,
        "linked_sheets_count": job.get("linked_sheets_count", 0),
        "linked_sheets_suggested_count": job.get("linked_sheets_suggested_count", 0),
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
            ("takeoff_summary.csv", "takeoff_summary_csv"),
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


@app.route("/api/reports/<run_folder>")
@login_required
def get_report(run_folder: str):
    """Return metadata for a single report run."""
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400

    sub = Path(OUTPUT_DIR) / run_folder
    if not sub.is_dir():
        return jsonify({"error": "Not found"}), 404

    files = {}
    for filename, key in [
        ("takeoff.json",        "json"),
        ("takeoff_summary.csv", "takeoff_summary_csv"),
        ("raw_items.csv",       "raw_csv"),
        ("calculations.csv",    "calculated_csv"),
        ("summary.txt",         "summary"),
    ]:
        f = sub / filename
        if f.exists():
            files[key] = {"filename": filename, "size": f.stat().st_size}

    if not files:
        return jsonify({"error": "Not found"}), 404

    cost_usd = sheets_processed = raw_items_count = calculated_count = None
    json_file = sub / "takeoff.json"
    if json_file.exists():
        try:
            with open(json_file) as jf:
                td = json.load(jf)
            api_usage = td.get("api_usage", {})
            cost_usd = api_usage.get("total_cost_usd")
            sheets_processed = td.get("sheets_processed")
            raw_items_count = td.get("total_line_items")
            calculated_count = td.get("total_calculated_items")
        except (json.JSONDecodeError, OSError):
            pass

    import re as _re
    m = _re.match(r"^(.*)_(\d{8}_\d{6})$", sub.name)
    project_name = m.group(1).replace("_", " ") if m else sub.name
    timestamp = m.group(2) if m else ""

    return jsonify({
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
