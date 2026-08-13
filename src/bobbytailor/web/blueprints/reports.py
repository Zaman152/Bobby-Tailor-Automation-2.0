"""Report listing, download, and preview routes."""
import json
import logging
import re
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, send_file
from flask_login import login_required

from bobbytailor import config
from bobbytailor.config import MAX_PREVIEW_ROWS

logger = logging.getLogger(__name__)

reports_bp = Blueprint("reports", __name__)

ALLOWED_PREVIEW_EXTENSIONS = {'.csv', '.json', '.txt'}

#: The artifacts a run publishes, and the key each is offered under. ONE list,
#: because there were two — ``list_reports`` and ``get_report`` each carried
#: their own copy and both had to be edited to add a file. ``coverage.json``
#: shows what that cost: it has been written by every run since phase 23 and
#: was in neither list, so the record of what a run did NOT measure was
#: fetchable by URL and reachable from no button on the page.
RUN_ARTIFACTS = (
    ("takeoff.json",        "json"),
    ("takeoff_summary.csv", "takeoff_summary_csv"),
    ("raw_items.csv",       "raw_csv"),
    ("calculations.csv",    "calculated_csv"),
    ("summary.txt",         "summary"),
    ("coverage.json",       "coverage_json"),
)


def _output_root() -> Path:
    """Absolute OUTPUT_DIR — required because Flask resolves relative send_file paths against app.root_path (src/bobbytailor/web/), not cwd."""
    return Path(config.OUTPUT_DIR).resolve()


def _resolve_run_file(run_folder: str, filename: str) -> Optional[Path]:
    """Resolve a run artifact under OUTPUT_DIR; None if invalid or missing."""
    if ".." in run_folder or ".." in filename:
        return None
    if "/" in run_folder or "/" in filename:
        return None
    root = _output_root()
    target = (root / run_folder / filename).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        logger.warning("Run file path escaped output directory: %s/%s", run_folder, filename)
        return None
    if not target.is_file():
        return None
    return target


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
    output_root = _output_root()
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

@reports_bp.route("/api/reports")
def list_reports():
    """List all generated report runs. Each run is its own folder under output/.
    Each folder contains: takeoff.json, raw_items.csv, calculations.csv, summary.txt."""
    output = _output_root()
    runs = []

    # Each subdirectory of output/ that contains takeoff.json is a run
    for sub in sorted(output.iterdir(), reverse=True):
        if not sub.is_dir() or sub.name in ("screenshots",):
            continue

        files = {}
        for filename, key in RUN_ARTIFACTS:
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


@reports_bp.route("/api/reports/<run_folder>")
@login_required
def get_report(run_folder: str):
    """Return metadata for a single report run."""
    if "/" in run_folder or ".." in run_folder:
        return jsonify({"error": "Invalid path"}), 400

    sub = _output_root() / run_folder
    if not sub.is_dir():
        return jsonify({"error": "Not found"}), 404

    files = {}
    for filename, key in RUN_ARTIFACTS:
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


@reports_bp.route("/api/reports/<run_folder>/<filename>")
@login_required
def download_run_file(run_folder, filename):
    """Download a specific file from a run folder."""
    path = _resolve_run_file(run_folder, filename)
    if path is None:
        return jsonify({"error": "Not found"}), 404
    mimetype = {
        ".csv": "text/csv",
        ".json": "application/json",
        ".txt": "text/plain",
    }.get(path.suffix.lower())
    return send_file(path, as_attachment=True, download_name=filename, mimetype=mimetype)


@reports_bp.route("/api/reports/<run_folder>/preview/<filename>")
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


@reports_bp.route("/api/reports/<run_folder>/sheet-image/<path:relpath>")
@login_required
def serve_sheet_image(run_folder: str, relpath: str):
    """Serve a sheet PNG for traceability (path is relative to OUTPUT_DIR)."""
    if ".." in run_folder or ".." in relpath:
        return jsonify({"error": "Invalid path"}), 400
    output_root = _output_root()
    target = (output_root / relpath).resolve()
    try:
        target.relative_to(output_root)
    except ValueError:
        logger.warning(f"Sheet-image path escaped output dir: {relpath}")
        return jsonify({"error": "Invalid path"}), 400
    if not target.is_file() or target.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        return jsonify({"error": "Not found"}), 404
    mime = "image/png" if target.suffix.lower() == ".png" else "image/jpeg"
    return send_file(target, mimetype=mime, max_age=3600)


# NOTE (21-REVIEW WR-03): the legacy flat-output download route
# GET /api/reports/<filename> was removed. Its URL rule was structurally
# identical to get_report's /api/reports/<run_folder> and registered second,
# so Werkzeug could never match it — the endpoint was dead code since the
# blueprint split. No template/JS caller uses a flat report download
# (downloads go through /api/reports/<run_folder>/<filename>).

